from fastapi import APIRouter, File, HTTPException, Request, UploadFile
from fastapi.responses import Response


router = APIRouter(prefix="/api", tags=["music-config"])


@router.get("/music-generator/status")
def music_generator_status(request: Request):
    return request.app.state.music_generator.status()


@router.get("/music-generator/themes")
def music_generator_themes(request: Request):
    return request.app.state.theme_library.list()


@router.put("/music-generator/theme/{theme_id}")
def select_music_generator_theme(theme_id: str, request: Request):
    try:
        return request.app.state.music_generator.select_theme(theme_id)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/music-generator/random-theme")
def random_music_generator_theme(request: Request):
    try:
        return request.app.state.music_generator.randomize_theme()
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.patch("/music-generator/settings")
def update_music_generator_settings(payload: dict, request: Request):
    try:
        return request.app.state.music_generator.update_settings(payload)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/music-generator/mode")
async def set_music_generator_mode(payload: dict, request: Request):
    mode = payload.get("system_mode") or payload.get("mode")
    if mode not in {"MIRROR", "ENGAGING"}:
        raise HTTPException(status_code=422, detail="system_mode must be MIRROR or ENGAGING")
    return await request.app.state.music_generator.set_system_mode(mode)


@router.get("/music/config")
def get_music_config(request: Request):
    return request.app.state.config_store.api_payload()


@router.put("/music/config")
def put_music_config(payload: dict, request: Request):
    try:
        config = request.app.state.config_store.replace(payload)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    request.app.state.runtime.apply_config()
    return config.as_api()


@router.post("/music/config/reset")
def reset_music_config(request: Request):
    config = request.app.state.config_store.reset()
    request.app.state.runtime.apply_config()
    return config.as_api()


@router.get("/music/config/export")
def export_music_config(request: Request):
    return Response(
        request.app.state.config_store.export_yaml(),
        media_type="application/x-yaml",
        headers={"Content-Disposition": "attachment; filename=music-config.yaml"},
    )


@router.post("/music/config/import")
async def import_music_config(request: Request, file: UploadFile = File(...)):
    try:
        text = (await file.read()).decode("utf-8")
        config = request.app.state.config_store.import_text(text)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    request.app.state.runtime.apply_config()
    return config.as_api()


@router.get("/presets")
def list_presets(request: Request):
    return request.app.state.presets.list()


@router.post("/presets")
def save_preset(payload: dict, request: Request):
    return request.app.state.presets.save(payload.get("name", "Untitled Preset"), request.app.state.config_store.active_config.as_api())


@router.post("/presets/{preset_id}/load")
def load_preset(preset_id: str, request: Request):
    try:
        payload = request.app.state.presets.load(preset_id, request.app.state.config_store.reset().as_api())
        config = request.app.state.config_store.replace(payload)
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    request.app.state.runtime.apply_config()
    return config.as_api()
