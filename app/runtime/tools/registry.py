from __future__ import annotations

from collections.abc import Iterable

from app.core.exceptions import OCRToolConfigurationError, OCRToolNotFoundError
from app.runtime.tools.base import BaseRuntimeTool


class ToolRegistry:
    def __init__(self, tools: Iterable[BaseRuntimeTool] | None = None) -> None:
        self._tools: dict[str, BaseRuntimeTool] = {}
        for tool in tools or []:
            self.register(tool)

    def register(self, tool: BaseRuntimeTool) -> None:
        if tool.name in self._tools:
            raise OCRToolConfigurationError(
                f"Tool '{tool.name}' has already been registered."
            )
        self._tools[tool.name] = tool

    def has(self, tool_name: str) -> bool:
        return tool_name in self._tools

    def get(self, tool_name: str) -> BaseRuntimeTool:
        tool = self._tools.get(tool_name)
        if tool is None:
            raise OCRToolNotFoundError(f"Tool '{tool_name}' is not registered.")
        return tool

    def list_tools(self) -> list[BaseRuntimeTool]:
        return list(self._tools.values())

    def list_tool_specs(self) -> list[dict[str, object]]:
        return [tool.build_tool_spec() for tool in self.list_tools()]
