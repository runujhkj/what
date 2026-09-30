import queue
import threading
from dataclasses import dataclass, field
from typing import Any

from ..audio import AudioConfig
from ..output import OutputConfig
from .event_bus import EventBus
from .stats import StatsTracker
from .types import ClientState, ServiceConfig


@dataclass
class ServiceRuntime:
    audio_cfg: AudioConfig
    vad_cfg: Any
    asr_cfg: Any
    output_cfg: OutputConfig
    service_cfg: ServiceConfig
    session_id: str
    session_key: str
    event_queue: queue.Queue[dict[str, Any]] = field(default_factory=queue.Queue)
    event_bus: EventBus = field(default_factory=EventBus)
    clients: dict[str, ClientState] = field(default_factory=dict)
    token_lock: threading.Lock = field(default_factory=threading.Lock)
    issued_tokens: set[str] = field(default_factory=set)
    mdns: Any | None = None
    stats: StatsTracker = field(default_factory=StatsTracker)
    shared_asr: Any | None = None
    asr_lock: threading.Lock = field(default_factory=threading.Lock)
    # Per-stream ASR workers: each distinct input stream (e.g. "mic", "desktop")
    # gets its OWN WhisperASR (and thus its own WhisperKit subprocess) so that a
    # continuous stream (desktop/app audio) can't starve an intermittent one (mic)
    # behind a single shared lock. Keyed by stream id; the "mic"/primary worker
    # reuses asr_lock + shared_asr for back-compat with control tuning + teardown.
    asr_workers: dict[str, Any] = field(default_factory=dict)
    asr_worker_locks: dict[str, threading.Lock] = field(default_factory=dict)
    asr_registry_lock: threading.Lock = field(default_factory=threading.Lock)
    # A worker already loaded by the startup preflight, handed to the first stream that
    # needs one instead of loading the model again.
    spare_asr: Any | None = None
    # Whether the ASR is warmed after the port binds (non-interactive faster-whisper),
    # rather than before it. When true the lifespan launches a background warmup thread.
    warm_in_background: bool = False
    # ASR readiness, observable via /health. "ready" once a decode has succeeded (or was
    # done synchronously before startup), "loading" while the background warmup runs, and
    # "error" if warmup could not produce a working engine. asr_ready_event is set once the
    # final state (and the resolved asr_cfg.device) is known, so stream workers can wait on
    # it instead of racing a half-resolved CUDA/CPU config.
    asr_status: str = "ready"
    asr_error: str = ""
    asr_ready_event: threading.Event = field(default_factory=threading.Event)
