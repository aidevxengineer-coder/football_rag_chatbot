from fastapi import FastAPI, HTTPException, UploadFile, File, BackgroundTasks

from futbot_common import CorrelationIdMiddleware

app = FastAPI(title="FutBot API")
app.add_middleware(CorrelationIdMiddleware)


@app.post("/api/ingest")
async def ingest_endpoint(
    background_tasks: BackgroundTasks,
    file: UploadFile | None = File(None),
):
    raise HTTPException(
        status_code=501,
        detail="Ingestion moved to ingestion microservice (Phase 5).",
    )


@app.get("/api/ingest/status/{event_id}")
def ingest_status(event_id: int):
    raise HTTPException(
        status_code=501,
        detail="Ingestion moved to ingestion microservice (Phase 5).",
    )


@app.post("/api/chat")
def chat():
    raise HTTPException(
        status_code=501,
        detail="Chat RAG moved to chat microservice (Phase 6). Use POST /chats/{id}/messages via gateway.",
    )


@app.get("/")
def root():
    return {
        "service": "legacy-api",
        "status": "deprecated",
        "message": "Use the gateway API and Pitchside web service.",
    }
