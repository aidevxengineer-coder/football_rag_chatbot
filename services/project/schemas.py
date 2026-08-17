from datetime import datetime

from pydantic import BaseModel, Field


class CreateProjectRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: str | None = None


class ProjectResponse(BaseModel):
    id: str
    name: str
    description: str | None
    created_at: datetime


class ProjectFileResponse(BaseModel):
    id: str
    filename: str
    content_hash: str
    status: str
    error_message: str | None = None
    created_at: datetime


class UpdateFileStatusRequest(BaseModel):
    status: str = Field(min_length=1, max_length=32)
    error_message: str | None = None


class CreateMemoryRequest(BaseModel):
    memory_type: str = Field(min_length=1, max_length=64)
    content: str = Field(min_length=1)
    source_chat_id: str | None = None


class MemoryItemResponse(BaseModel):
    id: str
    memory_type: str
    content: str
    source_chat_id: str | None
    created_at: datetime


class MemoryListResponse(BaseModel):
    items: list[MemoryItemResponse]


class ProjectContextResponse(BaseModel):
    project: ProjectResponse
    files: list[ProjectFileResponse]
    memory: list[MemoryItemResponse]


class KnowledgeFileResponse(BaseModel):
    id: str
    filename: str
    content_hash: str
    status: str
    error_message: str | None = None
    chunks_indexed: int = 0
    tokens_indexed: int = 0
    created_at: datetime


class KnowledgeStatsResponse(BaseModel):
    chunks: int
    files: int
    memory_tokens: int


class UpdateKnowledgeFileStatusRequest(BaseModel):
    status: str = Field(min_length=1, max_length=32)
    error_message: str | None = None
    chunks_indexed: int | None = None
    tokens_indexed: int | None = None
