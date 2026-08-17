from pydantic import BaseModel, Field


class ChunkInput(BaseModel):
    chunk_id: str
    text: str
    bm25_text: str | None = None
    source_file: str
    section_heading: str = ""
    page: int | None = None
    chunk_type: str = "text"
    chunk_index: int = 0
    token_count: int = 0
    sheet_name: str | None = None


class IndexChunksRequest(BaseModel):
    project_id: str | None = None
    file_id: str
    chunks: list[ChunkInput] = Field(min_length=1)


class IndexChunksResponse(BaseModel):
    indexed: int


class RetrieveRequest(BaseModel):
    query: str = Field(min_length=1)
    top_k: int = Field(default=5, ge=1, le=50)
    project_id: str | None = None
    project_ids: list[str] | None = None


class RetrievedChunk(BaseModel):
    chunk_id: str
    source_file: str
    page: int | None
    section_heading: str
    document: str
    rrf_score: float


class RetrieveResponse(BaseModel):
    chunks: list[RetrievedChunk]


class DeleteIndexResponse(BaseModel):
    removed: int
