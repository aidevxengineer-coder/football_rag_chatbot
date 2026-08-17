from datetime import datetime

from pydantic import BaseModel, Field


class ContextUsageBreakdown(BaseModel):
    snapshot: int
    hot_messages: int
    current_query: int
    memory: int
    retrieved_chunks: int


class ContextUsage(BaseModel):
    used_tokens: int
    limit_tokens: int
    percent_used: float
    breakdown: ContextUsageBreakdown


class CreateChatRequest(BaseModel):
    project_id: str | None = None
    title: str = "New Chat"


class MergeChatRequest(BaseModel):
    chat_id: str = Field(min_length=1)


class ChatResponse(BaseModel):
    id: str
    user_id: str | None
    project_id: str | None
    title: str
    compression_pending: bool
    created_at: datetime
    updated_at: datetime
    context_usage: ContextUsage
    should_compress: bool


class ChatListItem(BaseModel):
    id: str
    project_id: str | None
    title: str
    updated_at: datetime


class CreateMessageRequest(BaseModel):
    role: str = Field(pattern="^(user|assistant|system)$")
    content: str = Field(min_length=1)
    web_search_enabled: bool = False


class MessageResponse(BaseModel):
    id: str
    role: str
    content: str
    created_at: datetime


class MessageListResponse(BaseModel):
    messages: list[MessageResponse]


class PostMessageResponse(BaseModel):
    message: MessageResponse
    assistant_message: MessageResponse | None = None
    context_usage: ContextUsage
    should_compress: bool
    compression_pending: bool
    run_id: int | None = None
    tool_notice: str | None = None
    tool_notice_code: str | None = None
    web_search_skipped: bool = False
