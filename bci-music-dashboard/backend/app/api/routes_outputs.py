from fastapi import APIRouter, HTTPException, Request


router = APIRouter(prefix="/api/outputs", tags=["outputs"])


@router.get("/midi-ports")
def midi_ports(request: Request):
    return request.app.state.midi.list_ports().__dict__


@router.post("/test")
def test_output(payload: dict, request: Request):
    track_id = payload.get("track_id")
    track = next((item for item in request.app.state.config_store.active_config.tracks if item.id == track_id), None)
    if not track:
        raise HTTPException(status_code=404, detail="track not found")
    events = request.app.state.engine.test_event(track)
    for event in events:
        request.app.state.recorder.record_event(event)
    return {"events": [event.model_dump() for event in events], "midi": request.app.state.midi.status.__dict__}
