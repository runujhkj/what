from dataclasses import dataclass, field
from threading import Lock
from typing import Any
from collections import deque


@dataclass
class ControlSettings:
    profile: str | None = None
    engine: str | None = None
    device: str | None = None
    device_index: int | None = None
    compute_type: str | None = None
    model_size: str | None = None
    beam_size: int | None = None
    language: str | None = None
    no_vad: bool = True
    publish_delay_seconds: int = 0
    # Candidate low-energy boundary points evaluated when selecting chunk cuts.
    boundary_candidate_points: int = 3
    overlay_width_px: int = 640
    overlay_height_px: int = 140
    overlay_padding_px: int = 6
    overlay_font_size_px: float = 3.0
    # Total GPU VRAM (MiB) the Whisper workers may use; 0 = no limit. Exported to the
    # service as WHAT_GPU_MEM_BUDGET_MB, which picks the largest model that fits.
    gpu_mem_budget_mb: int = 0


@dataclass
class StreamSettings:
    input_mode: str = "mic"
    file_path: str | None = None
    realtime: bool = False
    mic_enabled: bool = True
    mic_backend: str | None = None
    mic_device: str | None = None
    desktop_enabled: bool = False
    desktop_backend: str | None = None
    # Compatibility field used by existing runtime capture paths.
    # Mirrors desktop_capture_input unless explicitly overridden.
    desktop_device: str | None = None
    # Explicit desktop audio roles:
    # - output_target: routed system output device name (e.g. what-desktop)
    # - capture_input: capture selector consumed by ffmpeg (e.g. :3)
    desktop_output_target: str | None = None
    desktop_capture_input: str | None = None
    event_prefix: str | None = "EVENT:"


@dataclass
class ControllerState:
    process: Any | None = None
    client_process: Any | None = None
    settings: ControlSettings = field(default_factory=ControlSettings)
    stream_settings: StreamSettings = field(default_factory=StreamSettings)
    stream_log_lock: Any = field(default_factory=Lock)
    stream_log_seq: int = 0
    stream_logs: Any = field(default_factory=lambda: deque(maxlen=2000))
    stream_log_last_ts: float = 0.0
    stream_event_lock: Any = field(default_factory=Lock)
    stream_event_seq: int = 0
    stream_events: Any = field(default_factory=lambda: deque(maxlen=4000))
    stream_event_last_ts: float = 0.0
    stream_event_stop_event: Any | None = None
    stream_event_thread: Any | None = None
    current_session_id: str | None = None
    process_log_path: str | None = None
    process_log_handle: Any | None = None
