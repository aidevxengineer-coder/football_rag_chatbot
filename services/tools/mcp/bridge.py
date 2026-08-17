import asyncio
import json
import logging
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Callable

from services.tools.config import settings
from services.tools.errors import ToolExecutionError

logger = logging.getLogger(__name__)


async def _call_sse_mcp_tool(url: str, tool_name: str, arguments: dict[str, Any]) -> Any:
    try:
        from mcp import ClientSession
        from mcp.client.sse import sse_client
    except ImportError as exc:
        raise ToolExecutionError("mcp package not installed") from exc

    async with sse_client(url) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(tool_name, arguments)
            if result.content:
                texts = [c.text for c in result.content if hasattr(c, "text") and c.text]
                if texts:
                    combined = "\n".join(texts)
                    try:
                        return json.loads(combined)
                    except json.JSONDecodeError:
                        return {"text": combined}
            return {"content": str(result)}


async def _call_sse_with_timeout(
    url: str, tool_name: str, arguments: dict[str, Any]
) -> Any:
    return await asyncio.wait_for(
        _call_sse_mcp_tool(url, tool_name, arguments),
        timeout=settings.request_timeout_sec,
    )


async def _call_stdio_mcp_tool(
    command: str,
    args: list[str],
    env: dict[str, str],
    tool_name: str,
    arguments: dict[str, Any],
) -> Any:
    try:
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client
    except ImportError as exc:
        raise ToolExecutionError("mcp package not installed") from exc

    server_params = StdioServerParameters(command=command, args=args, env=env)
    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(tool_name, arguments)
            if result.content:
                texts = [c.text for c in result.content if hasattr(c, "text") and c.text]
                if texts:
                    combined = "\n".join(texts)
                    try:
                        return json.loads(combined)
                    except json.JSONDecodeError:
                        return {"text": combined}
            return {"content": str(result)}


def call_sse_tool(url: str, tool_name: str, arguments: dict[str, Any]) -> Any:
    return asyncio.run(_call_sse_with_timeout(url, tool_name, arguments))


def call_stdio_tool(
    command: str,
    args: list[str],
    env: dict[str, str],
    tool_name: str,
    arguments: dict[str, Any],
) -> Any:
    return asyncio.run(_call_stdio_mcp_tool(command, args, env, tool_name, arguments))


def run_npx_mcp_pdf(
    package: str,
    tool_name: str,
    arguments: dict[str, Any],
) -> bytes:
    """Invoke markdown PDF MCP via npx; returns PDF bytes from outputPath."""
    with tempfile.TemporaryDirectory() as tmp:
        output_path = str(Path(tmp) / "export.pdf")
        payload = {**arguments, "outputPath": output_path}
        script = json.dumps({"tool": tool_name, "arguments": payload})
        proc = subprocess.run(
            ["npx", "-y", package],
            input=script,
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
        if proc.returncode != 0:
            raise ToolExecutionError(proc.stderr or proc.stdout or f"{package} failed")
        out_file = Path(output_path)
        if not out_file.exists():
            raise ToolExecutionError(f"{package} did not produce {output_path}")
        return out_file.read_bytes()


def markdown_to_pdf(markdown: str, title: str = "Chat Export") -> bytes:
    args = {"markdown": markdown, "title": title}
    try:
        return run_npx_mcp_pdf(settings.pdf_mcp_primary, "markdown_to_pdf", args)
    except Exception as primary_exc:
        logger.warning("Primary PDF MCP failed: %s", primary_exc)
        try:
            return run_npx_mcp_pdf(
                settings.pdf_mcp_fallback,
                "convert_markdown_to_pdf",
                {
                    "markdown": markdown,
                    "outputFilename": "export.pdf",
                    "showPageNumbers": True,
                },
            )
        except Exception as fallback_exc:
            raise ToolExecutionError(
                f"PDF export failed: {primary_exc}; fallback: {fallback_exc}"
            ) from fallback_exc


def make_mcp_tool_handler(
    *,
    name: str,
    description: str,
    mcp_tool: str,
    caller: Callable[[str, dict[str, Any]], Any],
    parameters: list[dict[str, Any]] | None = None,
):
    from services.tools.registry import register_tool
    from services.tools.schemas import ToolDefinition, ToolParameter

    class _McpTool:
        def __init__(self) -> None:
            self.name = name
            self._mcp_tool = mcp_tool
            self._caller = caller
            self._description = description
            self._parameters = parameters or []

        def definition(self) -> ToolDefinition:
            return ToolDefinition(
                name=self.name,
                description=self._description,
                parameters=[
                    ToolParameter(
                        name=p.get("name", "arg"),
                        type=p.get("type", "string"),
                        description=p.get("description", ""),
                        required=bool(p.get("required", False)),
                    )
                    for p in self._parameters
                ],
                source="mcp",
            )

        def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
            raw = self._caller(self._mcp_tool, arguments)
            if isinstance(raw, dict):
                return raw
            return {"result": raw}

    register_tool(_McpTool())
