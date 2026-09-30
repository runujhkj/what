from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from enum import Enum

class EventType(str, Enum):
    TRANSCRIPTION = "transcription"
    CONTROL = "control"
    STATUS = "status"

class TranscriptionEvent(BaseModel):
    """Rich data packet for live transcription with re-edit support."""
    sequence_id: str = Field(..., description="Stable ID for a single continuous block of speech")
    version: int = Field(default=1, description="Increments when the model refines previous text")
    is_final: bool = Field(default=False, description="True if the segment is committed and unlikely to change")
    
    # Content
    text: str = Field(..., description="The decoded text or <unintelligible> marker")
    language: str = Field(..., description="Detected or locked language code")
    
    # Performance & Quality
    confidence: float = Field(..., description="Mean logprob of the segment; trigger for unintelligible fallback")
    stability: float = Field(default=1.0, description="0.0-1.0 probability that this version will be refined again")
    
    # Timing & Audio Pointers (Boost for future review/labeling)
    start_sec: float
    end_sec: float
    audio_start_byte: int = Field(..., description="Pointer to session buffer for labeling review")
    audio_end_byte: int
    
    # Metadata for Auditing
    metadata: Dict[str, Any] = Field(default_factory=dict)

class ControlCommand(BaseModel):
    """Commands sent from Client (CLI/GUI) to Server mid-stream."""
    unintelligible_threshold: Optional[float] = None
    vad_sensitivity: Optional[float] = None
    language_lock: Optional[str] = None  # e.g., "en" or "auto"
    logging_enabled: Optional[bool] = None

class ServerStatus(BaseModel):
    """Periodic status heartbeats for monitoring VRAM and GPU lag."""
    session_id: str
    vram_usage_mb: int
    inference_lag_ms: float = Field(..., description="Processing time vs Real-time clock")
    active_clients: int
