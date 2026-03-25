"""Runtime tool abstractions and executors."""

__all__ = [
    "OCRLine",
    "OCRPage",
    "OCRProviderResponse",
    "OCRTool",
    "OCRToolRequest",
    "OCRToolResult",
    "ToolExecutor",
    "ToolRegistry",
    "build_default_ocr_adapters",
    "build_default_tool_executor",
    "build_default_tool_registry",
]


def __getattr__(name: str):
    if name in {"ToolExecutor"}:
        from app.runtime.tools.executor import ToolExecutor

        return ToolExecutor
    if name in {"ToolRegistry"}:
        from app.runtime.tools.registry import ToolRegistry

        return ToolRegistry
    if name in {
        "OCRLine",
        "OCRPage",
        "OCRProviderResponse",
        "OCRToolRequest",
        "OCRToolResult",
    }:
        from app.runtime.tools.schemas import (
            OCRLine,
            OCRPage,
            OCRProviderResponse,
            OCRToolRequest,
            OCRToolResult,
        )

        exports = {
            "OCRLine": OCRLine,
            "OCRPage": OCRPage,
            "OCRProviderResponse": OCRProviderResponse,
            "OCRToolRequest": OCRToolRequest,
            "OCRToolResult": OCRToolResult,
        }
        return exports[name]
    if name in {
        "OCRTool",
        "build_default_ocr_adapters",
        "build_default_tool_executor",
        "build_default_tool_registry",
    }:
        from app.runtime.tools.ocr_tool import (
            OCRTool,
            build_default_ocr_adapters,
            build_default_tool_executor,
            build_default_tool_registry,
        )

        exports = {
            "OCRTool": OCRTool,
            "build_default_ocr_adapters": build_default_ocr_adapters,
            "build_default_tool_executor": build_default_tool_executor,
            "build_default_tool_registry": build_default_tool_registry,
        }
        return exports[name]
    raise AttributeError(name)
