import threading
from typing import Any

from ..asr import WhisperASR, resolve_engine_name
from ..output import OutputConfig
from ..pipeline import run_frames_pipeline
from .runtime import ServiceRuntime


def get_stream_worker(runtime: ServiceRuntime, stream_key: str) -> tuple[Any, threading.Lock]:
    """Return the (WhisperASR, lock) dedicated to this input stream, creating it on
    first use. Distinct streams get distinct workers so they decode in parallel
    instead of serializing behind one lock. The primary ("mic") stream reuses the
    runtime's asr_lock + shared_asr so control tuning and teardown keep working."""
    key = stream_key or "mic"
    # If the model is warming in the background, wait for it to finish before creating a
    # worker: the warmup resolves asr_cfg.device (CUDA -> CPU on missing libraries) and
    # publishes runtime.spare_asr before setting this event, so reusing it here avoids a
    # second model load and never starts a worker on a half-resolved CUDA config.
    if runtime.warm_in_background and not runtime.asr_ready_event.is_set():
        runtime.asr_ready_event.wait(timeout=180.0)
    with runtime.asr_registry_lock:
        asr = runtime.asr_workers.get(key)
        if asr is None:
            asr = runtime.spare_asr if runtime.spare_asr is not None else WhisperASR(runtime.asr_cfg)
            runtime.spare_asr = None
            runtime.asr_workers[key] = asr
            if key == "mic":
                runtime.asr_worker_locks[key] = runtime.asr_lock
                runtime.shared_asr = asr
            else:
                runtime.asr_worker_locks[key] = threading.Lock()
        lock = runtime.asr_worker_locks[key]
    return asr, lock


def make_enricher(runtime: ServiceRuntime, client_id: str, input_mode: str = "mic",
                  recording_epoch: str = "", recorded: bool = False,
                  stream_started_at: float | None = None):
    asr_cfg = getattr(runtime, "asr_cfg", None)
    asr_engine = resolve_engine_name(asr_cfg) if asr_cfg is not None else ""
    asr_model = str((getattr(asr_cfg, "model_path", None) or getattr(asr_cfg, "model_size", "")) or "")

    def _enricher(event: dict[str, Any]) -> None:
        event["session_id"] = runtime.session_id
        event["client_id"] = client_id
        event["input_source_id"] = input_mode
        event["recording_epoch"] = recording_epoch
        # Whether this client's audio is being written to <session>/<client_id>.wav,
        # where segment/word abs times are WAV offsets. Review uses it to explain
        # unavailable audio instead of assuming a recording exists.
        event["recorded"] = bool(recorded)
        # Wall-clock time (epoch s) of sample 0 of that recording. abs times are offsets
        # from it, which is what orders segments from different sources in one transcript
        # (what/session_files.py).
        if stream_started_at is not None:
            event["stream_started_at"] = round(float(stream_started_at), 3)
        # Which recognizer produced the text, so corrections record reproducible context.
        event["asr_engine"] = asr_engine
        event["asr_model"] = asr_model

    return _enricher


def start_client_pipeline(
    runtime: ServiceRuntime,
    client_id: str,
    frames,
    log_path: str,
    stop_event: threading.Event,
    input_mode: str = "mic",
    timeline_offset_sec: float = 0.0,
    recording_epoch: str = "",
    recorded: bool = False,
    stream_started_at: float | None = None,
) -> tuple[threading.Thread, list[str]]:
    client_output_cfg = OutputConfig(
        text_stream=False,
        jsonl_log=log_path,
        jsonl_dir=runtime.output_cfg.jsonl_dir,
        text_mode=runtime.output_cfg.text_mode,
        text_window_segments=runtime.output_cfg.text_window_segments,
        text_window_chars=runtime.output_cfg.text_window_chars,
        text_block_clear=runtime.output_cfg.text_block_clear,
        text_normalize=runtime.output_cfg.text_normalize,
    )
    transcript: list[str] = []

    stream_asr, stream_lock = get_stream_worker(runtime, input_mode)

    def _on_event(event: dict[str, Any]) -> None:
        text = event.get("text", "")
        if text:
            transcript.append(text)
        runtime.event_queue.put(event)
        runtime.event_bus.publish(event)

    thread = threading.Thread(
        target=run_frames_pipeline,
        kwargs=dict(
            frames=frames,
            audio_cfg=runtime.audio_cfg,
            vad_cfg=runtime.vad_cfg,
            asr_cfg=runtime.asr_cfg,
            output_cfg=client_output_cfg,
            on_event=_on_event,
            event_enricher=make_enricher(runtime, client_id, input_mode, recording_epoch, recorded,
                                         stream_started_at),
            stats_hook=runtime.stats.update,
            stop_event=stop_event,
            shared_asr=stream_asr,
            asr_lock=stream_lock,
            stream_label=input_mode,
            timeline_offset_sec=timeline_offset_sec,
            segment_id_prefix=f"{recording_epoch}-" if recording_epoch else "",
        ),
        daemon=True,
    )
    thread.start()
    return thread, transcript
