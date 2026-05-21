from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse


router = APIRouter(prefix="/api/sessions", tags=["sessions"])


@router.post("/start")
def start_session(request: Request):
    session_id = request.app.state.recorder.start(request.app.state.config_store.active_config.as_api())
    return {"id": session_id}


@router.post("/stop")
def stop_session(request: Request):
    session_id = request.app.state.recorder.stop()
    return {"id": session_id, "stopped": bool(session_id)}


@router.get("")
def list_sessions(request: Request):
    return request.app.state.recorder.list_sessions()


@router.get("/{session_id}/download")
def download(session_id: str, format: str, request: Request):
    try:
        path = request.app.state.recorder.artifact(session_id, format)
    except KeyError as exc:
        raise HTTPException(status_code=400, detail="format must be mid, jsonl, or csv") from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="session artifact not found") from exc
    media_types = {"mid": "audio/midi", "jsonl": "application/x-ndjson", "csv": "text/csv"}
    return FileResponse(path, media_type=media_types[format], filename=path.name)
