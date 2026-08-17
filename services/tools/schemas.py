from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class ToolParameter(BaseModel):
    name: str
    type: str = "string"
    description: str = ""
    required: bool = False


class ToolDefinition(BaseModel):
    name: str
    description: str
    parameters: list[ToolParameter] = Field(default_factory=list)
    source: str = "builtin"


class ExecuteToolRequest(BaseModel):
    tool: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    session_id: str | None = None
    run_id: int | None = None
    web_search_enabled: bool = False


class ExecuteToolResponse(BaseModel):
    tool: str
    success: bool
    result: dict[str, Any] | None = None
    error_message: str | None = None
    duration_ms: int = 0
    skipped: bool = False


class LiveEvent(BaseModel):
    id: str
    competition: str = "Football"
    home_team: str
    away_team: str
    home_score: int | None = None
    away_score: int | None = None
    status: str = "Live"
    minute: str | None = None
    started_at: str | None = None


class LiveEventsResponse(BaseModel):
    events: list[LiveEvent] = Field(default_factory=list)
    provider: str | None = None
    updated_at: datetime
    message: str | None = None
