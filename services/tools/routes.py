from fastapi import APIRouter, HTTPException

from futbot_common.responses import DataResponse
from services.tools.live_events import fetch_live_events
from services.tools.registry import (
    WEB_SEARCH_TOOL,
    execute_tool,
    list_tools,
    mcp_tools_available,
)
from services.tools.schemas import (
    ExecuteToolRequest,
    ExecuteToolResponse,
    LiveEventsResponse,
    ToolDefinition,
)

router = APIRouter(tags=["tools"])


@router.get("/tools", response_model=DataResponse[list[ToolDefinition]])
def list_available_tools() -> DataResponse[list[ToolDefinition]]:
    tools = list_tools(include_web_search=True)
    return DataResponse(data=tools)


@router.get("/tools/health", response_model=DataResponse[dict])
def tools_health() -> DataResponse[dict]:
    return DataResponse(
        data={
            "mcp_available": mcp_tools_available(),
        }
    )


@router.get("/tools/live-events", response_model=DataResponse[LiveEventsResponse])
def live_events() -> DataResponse[LiveEventsResponse]:
    """Safe public facade over the allowlisted live-score MCP tools."""
    return DataResponse(data=fetch_live_events())


@router.post("/tools/execute", response_model=DataResponse[ExecuteToolResponse])
def execute_tool_route(body: ExecuteToolRequest) -> DataResponse[ExecuteToolResponse]:
    if body.tool == WEB_SEARCH_TOOL and not body.web_search_enabled:
        return DataResponse(
            data=ExecuteToolResponse(
                tool=body.tool,
                success=False,
                skipped=True,
                error_message="web_search disabled",
            )
        )
    result = execute_tool(
        body.tool,
        body.arguments,
        web_search_enabled=body.web_search_enabled,
    )
    if not result.success and not result.skipped and result.error_message:
        if "not found" in (result.error_message or "").lower():
            raise HTTPException(status_code=404, detail=result.error_message)
    return DataResponse(data=result)
