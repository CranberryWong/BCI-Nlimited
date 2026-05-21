from fastapi import APIRouter, HTTPException, Request


router = APIRouter(prefix="/api/control", tags=["control"])


@router.get("/status")
def status(request: Request):
    return request.app.state.runtime.status()


@router.post("/start-model")
def start_model(request: Request):
    try:
        return request.app.state.runtime.start_model()
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/stop-model")
def stop_model(request: Request):
    return request.app.state.runtime.stop_model()


@router.post("/start-simulator")
async def start_simulator(request: Request):
    request.app.state.runtime.simulator.start()
    return request.app.state.runtime.status()


@router.post("/stop-simulator")
async def stop_simulator(request: Request):
    await request.app.state.runtime.simulator.stop()
    return request.app.state.runtime.status()
