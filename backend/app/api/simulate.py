from fastapi import APIRouter, Body, Request

from app.api.common import ok

router = APIRouter(prefix="/simulate", tags=["simulate"])


@router.post("/start")
async def start(request: Request, params: dict = Body(...)):
    return ok(request.app.state.runtime.start(params))


@router.post("/stop")
async def stop(request: Request):
    return ok(request.app.state.runtime.stop())


@router.post("/pause")
async def pause(request: Request):
    return ok(request.app.state.runtime.pause())


@router.post("/resume")
async def resume(request: Request):
    return ok(request.app.state.runtime.resume())


@router.post("/step")
async def step_n(request: Request, body: dict = Body(default={"steps": 1})):
    return ok(request.app.state.runtime.step_n(int(body.get("steps", 1))))


@router.post("/speed")
async def set_speed(request: Request, body: dict = Body(...)):
    return ok(request.app.state.runtime.set_speed(float(body.get("speed", 1.0))))


@router.get("/status")
async def status(request: Request):
    return ok(request.app.state.runtime.status())
