from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from langchain_core.tools import BaseTool

ToolCapability = Literal["knowledge", "realtime_info", "action"]
ToolOperation = Literal["read", "write"]


@dataclass(frozen=True, slots=True)
class ToolDefinition:
    tool: BaseTool
    capability: ToolCapability
    operation: ToolOperation
    safe_argument_names: frozenset[str]
    artifact_types: tuple[type[object], ...]
