from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, Request

from app.music.schemas import TrackConfig


router = APIRouter(prefix="/api/tracks", tags=["tracks"])


@router.get("")
def list_tracks(request: Request):
    return [track.model_dump() for track in request.app.state.config_store.active_config.tracks]


@router.post("")
def add_track(track: TrackConfig, request: Request):
    try:
        created = request.app.state.config_store.add_track(track)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    request.app.state.runtime.apply_config()
    return created.model_dump()


@router.post("/{track_id}/duplicate")
def duplicate_track(track_id: str, request: Request):
    tracks = request.app.state.config_store.active_config.tracks
    source = next((track for track in tracks if track.id == track_id), None)
    if source is None:
        raise HTTPException(status_code=404, detail="track not found")
    payload = source.model_dump()
    payload["id"] = f"{track_id}-{uuid.uuid4().hex[:5]}"
    payload["name"] = f"{source.name} Copy"
    duplicated = request.app.state.config_store.add_track(TrackConfig.model_validate(payload))
    request.app.state.runtime.apply_config()
    return duplicated.model_dump()


@router.patch("/{track_id}")
def patch_track(track_id: str, patch: dict, request: Request):
    try:
        track = request.app.state.config_store.patch_track(track_id, patch)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="track not found") from exc
    request.app.state.runtime.apply_config()
    return track.model_dump()


@router.post("/{track_id}/reset")
def reset_track(track_id: str, request: Request):
    try:
        track = request.app.state.config_store.reset_track(track_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="default track not found") from exc
    request.app.state.runtime.apply_config()
    return track.model_dump()


@router.delete("/{track_id}")
def delete_track(track_id: str, request: Request):
    try:
        request.app.state.config_store.delete_track(track_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="track not found") from exc
    request.app.state.runtime.apply_config()
    return {"deleted": track_id}
