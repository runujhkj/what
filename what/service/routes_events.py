import asyncio
import queue

from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse

from ..output import format_sse
from .runtime import ServiceRuntime


def register_events(app: FastAPI, runtime: ServiceRuntime) -> None:
    @app.get(runtime.service_cfg.sse_path)
    async def events(request: Request) -> StreamingResponse:
        sub_id, sub_queue = runtime.event_bus.subscribe()

        async def event_generator():
            try:
                while True:
                    if await request.is_disconnected():
                        return
                    try:
                        event = await asyncio.to_thread(sub_queue.get, True, 0.25)
                    except queue.Empty:
                        continue
                    yield format_sse(event)
            except asyncio.CancelledError:
                # Normal shutdown/disconnect path for SSE stream.
                return
            finally:
                runtime.event_bus.unsubscribe(sub_id)

        return StreamingResponse(event_generator(), media_type="text/event-stream")
