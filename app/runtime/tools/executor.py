from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from app.runtime.tools.registry import ToolRegistry


class ToolExecutor:
    def __init__(self, registry: ToolRegistry) -> None:
        self._registry = registry

    @property
    def registry(self) -> ToolRegistry:
        return self._registry

    def execute(self, tool_name: str, request: BaseModel | dict[str, Any]) -> BaseModel:
        tool = self._registry.get(tool_name)
        parsed_request = tool.parse_request(request)
        return tool.execute(parsed_request)

    def list_tool_specs(self) -> list[dict[str, object]]:
        return self._registry.list_tool_specs()
