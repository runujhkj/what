import asyncio
import sys
from contextlib import asynccontextmanager

from ..discovery import publish_service
from .runtime import ServiceRuntime
from .warmup import warm_up_in_background


def build_service_lifespan(runtime: ServiceRuntime):
    @asynccontextmanager
    async def _lifespan(_: object):
        # Startup runs before uvicorn binds the socket, so warm the model on its own
        # thread and return immediately -- /health starts answering while the ASR loads
        # instead of the client seeing a refused connection. When warmup was already done
        # synchronously (WhisperKit, or an interactive CUDA prompt), the engine is ready.
        if runtime.warm_in_background:
            runtime.asr_status = "loading"
            warm_up_in_background(runtime)
        else:
            runtime.asr_status = "ready"
            runtime.asr_ready_event.set()
        if runtime.service_cfg.mdns_enabled:
            try:
                runtime.mdns = await asyncio.to_thread(
                    publish_service,
                    runtime.service_cfg.mdns_name,
                    runtime.service_cfg.host,
                    runtime.service_cfg.port,
                    runtime.service_cfg.advertise_host,
                )
            except Exception as exc:
                sys.stderr.write(f"mdns publish failed: {exc!r} ({type(exc).__name__})\n")
                runtime.mdns = None
        try:
            yield
        finally:
            for state in runtime.clients.values():
                state.stop_event.set()
                if state.queue is not None:
                    state.queue.put(b"")
                if state.decoder_proc is not None:
                    state.decoder_proc.terminate()
                if state.thread.is_alive():
                    state.thread.join(timeout=2)
            # Close every per-stream worker (mic, desktop, ...). Fall back to the
            # legacy shared_asr if no per-stream worker was ever registered.
            workers = list(runtime.asr_workers.values())
            if not workers and runtime.shared_asr is not None:
                workers = [runtime.shared_asr]
            if runtime.spare_asr is not None:
                workers.append(runtime.spare_asr)
                runtime.spare_asr = None
            for asr in workers:
                try:
                    asr.close()
                except Exception:
                    pass
            if runtime.mdns is not None:
                await asyncio.to_thread(runtime.mdns.close)

    return _lifespan
