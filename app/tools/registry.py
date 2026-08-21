from __future__ import annotations

from collections.abc import Iterable, Mapping

from langchain_core.messages import ToolMessage
from langchain_core.tools import BaseTool

from app.tools.types import ToolCapability, ToolDefinition


class ToolRegistry:
    def __init__(self, definitions: Iterable[ToolDefinition] = ()) -> None:
        self._definitions: dict[str, ToolDefinition] = {}
        for definition in definitions:
            self.register(definition)

    def register(self, definition: ToolDefinition) -> None:
        name = definition.tool.name
        if name in self._definitions:
            raise ValueError(f"tool already registered: {name}")
        self._definitions[name] = definition

    def tools_for(self, capabilities: Iterable[ToolCapability]) -> list[BaseTool]:
        allowed = set(capabilities)
        return [
            definition.tool
            for definition in self._definitions.values()
            if definition.capability in allowed
        ]

    def definition(self, name: str) -> ToolDefinition | None:
        return self._definitions.get(name)

    def safe_arguments(self, name: str, value: object) -> dict[str, object]:
        definition = self.definition(name)
        if definition is None or not isinstance(value, Mapping):
            return {}
        return {
            key: item
            for key, item in value.items()
            if key in definition.safe_argument_names
        }

    def artifacts(self, name: str, value: object) -> list[object]:
        definition = self.definition(name)
        if definition is None:
            return []
        return _matching_artifacts(value, definition.artifact_types)

    @property
    def definitions(self) -> tuple[ToolDefinition, ...]:
        return tuple(self._definitions.values())


def _matching_artifacts(
    value: object,
    artifact_types: tuple[type[object], ...],
) -> list[object]:
    if isinstance(value, ToolMessage):
        return _matching_artifacts(value.artifact, artifact_types)
    if isinstance(value, Mapping):
        if "artifact" in value:
            return _matching_artifacts(value.get("artifact"), artifact_types)
        messages = value.get("messages")
        if isinstance(messages, list):
            return [
                artifact
                for message in messages
                for artifact in _matching_artifacts(message, artifact_types)
            ]
        return []
    if isinstance(value, list):
        return [
            artifact
            for item in value
            for artifact in _matching_artifacts(item, artifact_types)
        ]
    return [value] if isinstance(value, artifact_types) else []
