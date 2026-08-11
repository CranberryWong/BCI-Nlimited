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


@router.post("/start-music-generator")
async def start_music_generator(request: Request):
    if request.app.state.presets_testing.running or request.app.state.noto_testing.running:
        raise HTTPException(status_code=409, detail="stop the active experiment before starting Generator")
    try:
        request.app.state.music_generator.start()
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return request.app.state.music_generator.status()


@router.post("/stop-music-generator")
async def stop_music_generator(request: Request):
    await request.app.state.music_generator.stop()
    return request.app.state.music_generator.status()


@router.post("/start-presets-testing")
async def start_presets_testing(request: Request):
    if request.app.state.music_generator.running:
        raise HTTPException(status_code=409, detail="stop Start Generator before starting the isolated Presets Testing experiment")
    if request.app.state.noto_testing.running:
        raise HTTPException(status_code=409, detail="stop Noto Testing before starting Presets Testing")
    request.app.state.presets_testing.start()
    return request.app.state.presets_testing.status()


@router.post("/stop-presets-testing")
async def stop_presets_testing(request: Request):
    await request.app.state.presets_testing.stop()
    return request.app.state.presets_testing.status()


@router.post("/start-noto-testing")
async def start_noto_testing(request: Request):
    if request.app.state.music_generator.running or request.app.state.presets_testing.running:
        raise HTTPException(status_code=409, detail="stop Generator and Presets Testing before starting Noto Testing")
    try:
        request.app.state.noto_testing.start()
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return request.app.state.noto_testing.status()


@router.post("/stop-noto-testing")
async def stop_noto_testing(request: Request):
    await request.app.state.noto_testing.stop()
    return request.app.state.noto_testing.status()


@router.post("/reload-music-model")
def reload_music_model(request: Request):
    loaded = request.app.state.music_generator.reload_model()
    request.app.state.recorder.set_model_metadata(request.app.state.melody_model.public_metadata())
    return {"loaded": loaded, **request.app.state.music_generator.status()}
