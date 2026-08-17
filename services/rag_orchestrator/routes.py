import asyncio
import queue

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

from futbot_common.responses import DataResponse
from services.rag_orchestrator.pipeline_events import (
    clear_session_events,
    emit_event,
    register_session,
)
from services.rag_orchestrator.schemas import PipelineRunRequest, PipelineRunResponse

router = APIRouter(tags=["pipeline"])


def _run_pipeline(**kwargs):
    from services.rag_orchestrator.graph import run_pipeline

    return run_pipeline(**kwargs)


@router.post("/pipeline/run", response_model=DataResponse[PipelineRunResponse])
def pipeline_run(body: PipelineRunRequest) -> DataResponse[PipelineRunResponse]:
    register_session(body.session_id)
    clear_session_events(body.session_id)
    emit_event(body.session_id, {"type": "pipeline_start", "query": body.query})

    try:
        result = _run_pipeline(
            query=body.query,
            context_messages=body.context_messages,
            session_id=body.session_id,
            snapshot=body.snapshot,
            snapshot_turn_count=body.snapshot_turn_count,
            project_id=body.project_id,
            user_id=body.user_id,
            web_search_enabled=body.web_search_enabled,
        )
    except Exception as exc:
        emit_event(body.session_id, {"type": "pipeline_error", "message": str(exc)})
        return DataResponse(
            data=PipelineRunResponse(
                reply=f"Pipeline failed: {exc}",
                snapshot=body.snapshot,
                snapshot_turn_count=body.snapshot_turn_count,
            )
        )

    return DataResponse(data=PipelineRunResponse(**result))


@router.websocket("/ws/pipeline")
async def pipeline_websocket(websocket: WebSocket, session_id: str = Query(...)):
    await websocket.accept()
    event_queue = register_session(session_id)
    await websocket.send_json({"type": "connected", "session_id": session_id})

    try:
        while True:
            try:
                event = await asyncio.to_thread(event_queue.get, True, 30.0)
                await websocket.send_json(event)
            except queue.Empty:
                await websocket.send_json({"type": "ping"})
    except WebSocketDisconnect:
        pass
