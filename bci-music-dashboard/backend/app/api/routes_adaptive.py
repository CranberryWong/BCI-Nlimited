from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response

from app.adaptive.config import MODULES
from app.adaptive.schemas import InputSample


router = APIRouter(prefix="/api", tags=["adaptive-performance"])


@router.get("/inputs/status")
def input_status(request: Request):
    return request.app.state.adaptive.context_hub.public_status()


@router.post("/inputs/simulator/start")
async def start_input_simulator(request: Request):
    request.app.state.adaptive.auxiliary_simulator.start()
    return {"running": request.app.state.adaptive.auxiliary_simulator.running}


@router.post("/inputs/simulator/stop")
async def stop_input_simulator(request: Request):
    await request.app.state.adaptive.auxiliary_simulator.stop()
    return {"running": False}


@router.post("/inputs/{source_id}/sample")
def input_sample(source_id: str, payload: dict, request: Request):
    try:
        sample = InputSample.model_validate({**payload, "source_id": source_id})
        accepted = request.app.state.adaptive.ingest(sample)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"accepted": accepted, "sample": sample.model_dump()}


@router.get("/config")
def all_config(request: Request):
    return {"locked": request.app.state.adaptive_config.locked, "modules": request.app.state.adaptive_config.all()}


@router.get("/config/modules")
def config_modules():
    return {"modules": list(MODULES)}


@router.get("/config/export/all")
def export_config(request: Request):
    return Response(
        request.app.state.adaptive_config.export_yaml(),
        media_type="application/x-yaml",
        headers={"Content-Disposition": "attachment; filename=adaptive-performance-config.yaml"},
    )


@router.get("/config/{module}")
def get_config(module: str, request: Request):
    try:
        return {"module": module, "locked": request.app.state.adaptive_config.locked, "config": request.app.state.adaptive_config.get(module)}
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"unknown config module: {module}") from exc


@router.put("/config/{module}")
def put_config(module: str, payload: dict, request: Request):
    try:
        config = request.app.state.adaptive_config.replace(module, payload)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"unknown config module: {module}") from exc
    except (RuntimeError, ValueError) as exc:
        raise HTTPException(status_code=409 if isinstance(exc, RuntimeError) else 422, detail=str(exc)) from exc
    return {"module": module, "locked": False, "config": config}


@router.post("/config/{module}/reset")
def reset_config(module: str, request: Request):
    try:
        config = request.app.state.adaptive_config.reset(module)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"unknown config module: {module}") from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"module": module, "locked": False, "config": config}


@router.post("/performance/start")
async def start_performance(request: Request):
    if request.app.state.music_generator.running or request.app.state.presets_testing.running or request.app.state.noto_testing.running:
        raise HTTPException(status_code=409, detail="stop the legacy generator or active experiment before starting adaptive performance")
    return await request.app.state.adaptive.start()


@router.post("/performance/stop")
async def stop_performance(request: Request):
    return await request.app.state.adaptive.stop()


@router.get("/runtime/status")
def runtime_status(request: Request):
    return request.app.state.adaptive.status()


@router.get("/runtime/logs")
def runtime_logs(request: Request, limit: int = 200):
    return request.app.state.adaptive.journal.recent(limit)


@router.post("/diagnostics/run")
async def diagnostics(request: Request):
    return await request.app.state.adaptive.diagnostics()
