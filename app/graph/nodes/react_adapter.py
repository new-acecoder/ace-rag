from __future__ import annotations

import json
from collections.abc import Mapping

from langchain_core.messages import AIMessage, SystemMessage, ToolMessage

from app.agents.react_agent import ReactAnswer
from app.graph.nodes.common import evidence_text, merge_chunks
from app.graph.services import WorkflowServices
from app.graph.state import AceRagState
from app.rag.agentic.schemas import EvidenceGrade, KnowledgeSearchResult
from app.rag.schemas import DocumentInfo, RetrievedChunk
from app.streaming.events import emit_event, forward_stream_events


async def run_react_agent(state: AceRagState, services: WorkflowServices) -> AceRagState:
    thinking_enabled = services.thinking_enabled(state)
    capabilities = tuple(state.get("required_capabilities", []))
    registry = services.tool_registry(thinking_enabled)
    context = await services.context_manager.build_context(
        state.get("messages", []),
        state.get("conversation_summary"),
        thinking_enabled,
    )
    private_messages = [
        SystemMessage(
            content="\n".join(
                [
                    f"必须回答的原始问题：{state.get('user_query', '')}",
                    f"本次优先检索词：{state.get('current_query', '')}",
                    f"本轮必需能力：{list(capabilities)}",
                    (
                        "本轮必须成功调用 search_knowledge_base 获取结构化证据，"
                        "否则只能明确说明知识证据不足。"
                        if "knowledge" in capabilities
                        else "仅在确实需要时使用已注入 Tool。"
                    ),
                    "已认可证据可用作上下文，但不得编造新的 chunk_id。",
                    evidence_text(state.get("retrieved_chunks", [])),
                ]
            )
        ),
        *context.messages,
    ]
    knowledge_results: list[KnowledgeSearchResult] = []
    response: ReactAnswer | None = None

    with forward_stream_events():
        async for event in services.react_agent(thinking_enabled, capabilities).astream_events(
            {"messages": private_messages},
            version="v2",
            config={
                "recursion_limit": (
                    services.settings.react_max_model_calls * 4
                    + services.settings.react_max_tool_calls * 2
                    + 4
                )
            },
        ):
            event_name = event.get("event")
            tool_name = event.get("name")
            definition = registry.definition(tool_name) if isinstance(tool_name, str) else None
            if event_name == "on_tool_start" and definition is not None:
                args = registry.safe_arguments(tool_name, event.get("data", {}).get("input"))
                emit_event(
                    "tool_start",
                    tool_call_id=str(event.get("run_id")),
                    tool_name=tool_name,
                    args=args,
                )
            elif event_name == "on_tool_end" and definition is not None:
                output = event.get("data", {}).get("output")
                artifacts = registry.artifacts(tool_name, output)
                knowledge_results.extend(
                    artifact
                    for artifact in artifacts
                    if isinstance(artifact, KnowledgeSearchResult)
                )
                emit_event(
                    "tool_end",
                    tool_call_id=str(event.get("run_id")),
                    tool_name=tool_name,
                    success=not _is_tool_error(output),
                    result_count=_artifact_count(artifacts),
                )
            elif event_name == "on_chain_end":
                response = _react_answer(event.get("data", {}).get("output")) or response

    knowledge_results = _unique_results(knowledge_results)
    evidence, grade, rounds, queries = _aggregate_knowledge_results(knowledge_results)

    if response is None:
        response, summary = await services.structured(
            ReactAnswer,
            state.get("messages", []),
            state.get("conversation_summary"),
            "\n".join(
                [
                    "根据已获得的企业知识库证据生成 ReAct 的最终答案，"
                    "并输出 JSON。",
                    "draft_answer 只能使用下列证据中的事实；"
                    "[1]...[n] 必须按 cited_chunk_ids 的顺序引用真实 chunk_id。",
                    f"原始问题：{state.get('user_query', '')}",
                    f"证据：{evidence_text(evidence)}",
                ]
            ),
            thinking_enabled,
        )
    else:
        summary = context.conversation_summary
    update: AceRagState = {
        "retrieval_batch": evidence,
        "retrieved_chunks": merge_chunks(state.get("retrieved_chunks", []), evidence),
        "retrieval_grade": grade,
        "evidence_insufficient": (
            not grade.sufficient if grade is not None else "knowledge" in capabilities
        ),
        "queries_used": list(dict.fromkeys([*state.get("queries_used", []), *queries])),
        "retrieval_count": state.get("retrieval_count", 0) + rounds,
        "draft_answer": response.draft_answer,
        "cited_chunk_ids": response.cited_chunk_ids,
        "conversation_summary": summary,
    }
    if "knowledge" not in capabilities and not knowledge_results:
        update["answer_status"] = "accepted"
    return update


def _react_answer(value: object) -> ReactAnswer | None:
    if isinstance(value, ReactAnswer):
        return value
    if isinstance(value, AIMessage):
        return _parse_react_answer(value.content)
    if isinstance(value, Mapping):
        structured = value.get("structured_response")
        if isinstance(structured, ReactAnswer):
            return structured
        if isinstance(structured, Mapping):
            try:
                return ReactAnswer.model_validate(structured)
            except Exception:
                return None
        messages = value.get("messages")
        if isinstance(messages, list):
            for message in reversed(messages):
                answer = _react_answer(message)
                if answer is not None:
                    return answer
    return None


def _parse_react_answer(content: object) -> ReactAnswer | None:
    text = content if isinstance(content, str) else str(content)
    if text.startswith("```") and text.endswith("```"):
        text = text.split("\n", 1)[-1].rsplit("```", 1)[0]
    try:
        return ReactAnswer.model_validate(json.loads(text))
    except (TypeError, ValueError, json.JSONDecodeError):
        return None


def _unique_results(
    results: list[KnowledgeSearchResult],
) -> list[KnowledgeSearchResult]:
    unique: list[KnowledgeSearchResult] = []
    seen: set[tuple[str, ...]] = set()
    for result in results:
        key = tuple(result.queries_used)
        if key in seen:
            continue
        seen.add(key)
        unique.append(result)
    return unique


def _aggregate_knowledge_results(
    results: list[KnowledgeSearchResult],
) -> tuple[list[RetrievedChunk], EvidenceGrade | None, int, list[str]]:
    if not results:
        return [], None, 0, []
    evidence = merge_chunks([], [chunk for result in results for chunk in result.evidence])
    sufficient = any(result.sufficient for result in results)
    best = max(
        results,
        key=lambda result: (result.sufficient, result.grade.coverage_score),
    )
    grade = best.grade.model_copy(
        update={
            "relevant": bool(evidence),
            "sufficient": sufficient,
            "relevant_chunk_ids": [chunk.chunk_id for chunk in evidence],
            "next_action": "answer" if sufficient else best.grade.next_action,
        }
    )
    return (
        evidence,
        grade,
        sum(result.retrieval_rounds for result in results),
        [query for result in results for query in result.queries_used],
    )


def _artifact_count(value: object) -> int:
    if isinstance(value, list):
        return sum(_artifact_count(item) for item in value)
    if isinstance(value, KnowledgeSearchResult):
        return len(value.evidence)
    if isinstance(value, (RetrievedChunk, DocumentInfo)):
        return 1
    return 0


def _is_tool_error(value: object) -> bool:
    return isinstance(value, ToolMessage) and value.status == "error"
