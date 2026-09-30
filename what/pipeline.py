from __future__ import annotations

import threading
import time
import os
import sys
from typing import Any, Callable, Iterable

from .audio import AudioConfig, InputConfig, chunk_stream, pcm_frame_generator, start_ffmpeg, stdin_frame_generator
from .asr import AsrConfig, WhisperASR
from .caption_ops import CaptionOpsBuilder
from .hallucination import is_hallucination
from .output import OutputConfig, OutputManager
from .vad import VadConfig, is_speech_chunk


def run_pipeline(
    audio_cfg: AudioConfig,
    input_cfg: InputConfig,
    vad_cfg: VadConfig,
    asr_cfg: AsrConfig,
    output_cfg: OutputConfig,
    on_event: Callable[[dict[str, Any]], None] | None = None,
    event_enricher: Callable[[dict[str, Any]], None] | None = None,
    stats_hook: Callable[[float, float], None] | None = None,
    stop_event: threading.Event | None = None,
    stderr_target=None,
) -> None:
    output = OutputManager(output_cfg)
    frame_samples = int(audio_cfg.sample_rate * audio_cfg.frame_ms / 1000)

    if input_cfg.mode == "stdin" and input_cfg.stdin_raw:
        # Bypass ffmpeg: data is already s16le at the configured rate/channels.
        # Passing sys.stdin.buffer to subprocess.Popen stdin= stalls when the
        # producer (e.g. SCStream) has a startup delay before its first write;
        # reading directly avoids that race.
        try:
            _run_frames_pipeline(
                frames=stdin_frame_generator(frame_samples),
                audio_cfg=audio_cfg,
                vad_cfg=vad_cfg,
                asr_cfg=asr_cfg,
                output_cfg=output_cfg,
                output=output,
                on_event=on_event,
                event_enricher=event_enricher,
                stats_hook=stats_hook,
                stop_event=stop_event,
            )
        finally:
            output.close()
        return

    proc = start_ffmpeg(input_cfg, audio_cfg, stderr_target=stderr_target)
    try:
        frames = pcm_frame_generator(proc, frame_samples)
        _run_frames_pipeline(
            frames=frames,
            audio_cfg=audio_cfg,
            vad_cfg=vad_cfg,
            asr_cfg=asr_cfg,
            output_cfg=output_cfg,
            output=output,
            on_event=on_event,
            event_enricher=event_enricher,
            stats_hook=stats_hook,
            stop_event=stop_event,
        )
    finally:
        output.close()
        proc.terminate()


def run_frames_pipeline(
    frames: Iterable[bytes],
    audio_cfg: AudioConfig,
    vad_cfg: VadConfig,
    asr_cfg: AsrConfig,
    output_cfg: OutputConfig,
    on_event: Callable[[dict[str, Any]], None] | None = None,
    event_enricher: Callable[[dict[str, Any]], None] | None = None,
    stats_hook: Callable[[float, float], None] | None = None,
    stop_event: threading.Event | None = None,
    shared_asr: Any | None = None,
    asr_lock: threading.Lock | None = None,
    stream_label: str = "",
    timeline_offset_sec: float = 0.0,
    segment_id_prefix: str = "",
) -> None:
    output = OutputManager(output_cfg)
    try:
        _run_frames_pipeline(
            frames=frames,
            audio_cfg=audio_cfg,
            vad_cfg=vad_cfg,
            asr_cfg=asr_cfg,
            output_cfg=output_cfg,
            output=output,
            on_event=on_event,
            event_enricher=event_enricher,
            stats_hook=stats_hook,
            stop_event=stop_event,
            shared_asr=shared_asr,
            asr_lock=asr_lock,
            stream_label=stream_label,
            timeline_offset_sec=timeline_offset_sec,
            segment_id_prefix=segment_id_prefix,
        )
    except Exception as exc:
        # This runs on a worker thread, so an escaping exception only prints a bare
        # "Exception in thread" traceback and the thread dies -- the service keeps
        # answering /health and recording audio while transcribing nothing, forever.
        # Emit a greppable marker so that silent-death mode is diagnosable from the log.
        sys.stderr.write(
            f"FATAL: transcription pipeline stopped ({stream_label or 'default'}): "
            f"{type(exc).__name__}: {exc}\n"
            "No further captions will be produced until the service is restarted.\n"
        )
        sys.stderr.flush()
        raise
    finally:
        output.close()


def _run_frames_pipeline(
    frames: Iterable[bytes],
    audio_cfg: AudioConfig,
    vad_cfg: VadConfig,
    asr_cfg: AsrConfig,
    output_cfg: OutputConfig,
    output: OutputManager,
    on_event: Callable[[dict[str, Any]], None] | None = None,
    event_enricher: Callable[[dict[str, Any]], None] | None = None,
    stats_hook: Callable[[float, float], None] | None = None,
    stop_event: threading.Event | None = None,
    shared_asr: Any | None = None,
    asr_lock: threading.Lock | None = None,
    stream_label: str = "",
    timeline_offset_sec: float = 0.0,
    segment_id_prefix: str = "",
) -> None:
    def _env_flag(name: str, default: bool) -> bool:
        raw = str(os.environ.get(name, "")).strip().lower()
        if not raw:
            return bool(default)
        return raw in {"1", "true", "yes", "on"}

    def _env_float(name: str, default: float) -> float:
        raw = str(os.environ.get(name, "")).strip()
        if not raw:
            return float(default)
        try:
            return float(raw)
        except Exception:
            return float(default)

    asr = shared_asr if shared_asr is not None else WhisperASR(asr_cfg)
    timeline_offset_sec = max(0.0, float(timeline_offset_sec))
    pipeline_started_at = time.perf_counter()
    stale_chunk_drop_enabled = _env_flag("WHAT_DROP_STALE_CHUNKS", True)
    max_processing_lag_sec = max(1.0, _env_float("WHAT_MAX_PROCESSING_LAG_SEC", 3.0))
    catchup_lag_sec = max(0.5, _env_float("WHAT_CATCHUP_LAG_SEC", 2.5))
    hard_drop_lag_sec = max(catchup_lag_sec + 0.5, _env_float("WHAT_HARD_DROP_LAG_SEC", 5.0))
    skip_subchunks_when_lagged = _env_flag("WHAT_SKIP_SUBCHUNKS_WHEN_LAGGED", True)
    subchunk_lag_sec = max(0.5, _env_float("WHAT_SUBCHUNK_LAG_SEC", 1.5))
    subchunk_min_ratio = max(0.5, min(1.0, _env_float("WHAT_SUBCHUNK_MIN_RATIO", 0.9)))
    dynamic_decode_simplify_enabled = _env_flag("WHAT_DYNAMIC_DECODE_SIMPLIFY", True)
    dynamic_simplify_lag_sec = max(1.0, _env_float("WHAT_DYNAMIC_SIMPLIFY_LAG_SEC", 2.5))
    catchup_full_chunk_ratio = max(0.7, min(1.0, _env_float("WHAT_CATCHUP_FULL_CHUNK_RATIO", 0.85)))
    target_decode_ratio = max(0.6, _env_float("WHAT_TARGET_DECODE_RATIO", 1.0))
    force_decode_every_chunks = max(2, int(_env_float("WHAT_FORCE_DECODE_EVERY_CHUNKS", 4)))
    # Off by default: decoding chunks VAD classified as non-speech makes Whisper caption
    # room silence as hallucinated words ("you"). Enable only to diagnose a VAD that
    # rejects real speech.
    force_decode_on_vad_reject = _env_flag("WHAT_FORCE_DECODE_ON_VAD_REJECT", False)
    force_decode_on_vad_reject_every_chunks = max(
        2,
        int(_env_float("WHAT_FORCE_DECODE_ON_VAD_REJECT_EVERY_CHUNKS", 2.0)),
    )
    lag_telemetry_interval_chunks = max(1, int(_env_float("WHAT_LAG_TELEMETRY_EVERY_CHUNKS", 20)))
    lag_total_seen = 0
    lag_dropped_stale_total = 0
    lag_dropped_subchunk_total = 0
    lag_dropped_dynamic_total = 0
    lag_vad_reject_total = 0
    lag_vad_forced_decode_total = 0
    lag_decoded_total = 0
    lag_decode_audio_total = 0.0
    lag_decode_elapsed_total = 0.0
    lag_processing_lag_sec = 0.0
    lag_last_telemetry_seq = 0
    chunks_since_decode = 0

    def emit_lag_snapshot_if_due() -> None:
        """Write soak-friendly telemetry even when a chunk produces no caption.

        Lag is most useful while VAD or the governor is shedding work.  Keeping
        this independent of segment emission makes those periods observable in
        the normal service log rather than appearing as a telemetry gap.
        """
        nonlocal lag_last_telemetry_seq
        if (lag_total_seen - lag_last_telemetry_seq) < lag_telemetry_interval_chunks:
            return
        lag_last_telemetry_seq = lag_total_seen
        decode_ratio_avg = (
            (lag_decode_elapsed_total / lag_decode_audio_total)
            if lag_decode_audio_total > 0.0
            else 0.0
        )
        try:
            sys.stderr.write(
                "lag telemetry:"
                f" stream={stream_label or 'mic'}"
                f" lag_sec={lag_processing_lag_sec:.3f}"
                f" ratio_avg={decode_ratio_avg:.3f}"
                f" seen={lag_total_seen}"
                f" decoded={lag_decoded_total}"
                f" drop_stale={lag_dropped_stale_total}"
                f" drop_subchunk={lag_dropped_subchunk_total}"
                f" drop_dynamic={lag_dropped_dynamic_total}"
                f" vad_reject={lag_vad_reject_total}"
                f" vad_forced={lag_vad_forced_decode_total}\n"
            )
            sys.stderr.flush()
        except Exception:
            pass
    # Caption ops are upstream transport hints. Keep their default limits permissive
    # so authoritative wrap/eviction stays in overlay runtime policy.
    max_visible_lines = int(output_cfg.text_window_segments or 0)
    if max_visible_lines <= 0:
        max_visible_lines = 10000
    max_chars_per_line = int(output_cfg.text_window_chars or 0)
    if max_chars_per_line <= 0:
        max_chars_per_line = 10000
    caption_ops = CaptionOpsBuilder(
        gap_break_ms=3000,
        max_visible_lines=max(1, max_visible_lines),
        max_chars_per_line=max(16, max_chars_per_line),
    )
    chunk_index = 0
    segment_index = 0
    nominal_chunk_sec = max(0.001, float(audio_cfg.chunk_ms) / 1000.0)
    _trace = os.environ.get("WHAT_TRACE")
    for chunk in chunk_stream(frames, audio_cfg):
        if stop_event and stop_event.is_set():
            break
        lag_total_seen += 1
        if _trace:
            sys.stderr.write(f"[trace] chunk seen={lag_total_seen} bytes={len(chunk.pcm_bytes)}\n"); sys.stderr.flush()
        chunks_since_decode += 1
        # Keep live streams responsive when decode falls behind:
        # if we're processing audio far behind wall time, drop stale chunks
        # until we catch up instead of compounding backlog.
        if stale_chunk_drop_enabled:
            processing_lag_sec = max(
                0.0,
                (time.perf_counter() - pipeline_started_at) - float(chunk.end_sec),
            )
            lag_processing_lag_sec = processing_lag_sec
            if processing_lag_sec > max_processing_lag_sec:
                # Escape hatch so the stream never goes permanently mute. A single
                # contention spike (Blender readback + OBS + the other worker) could push
                # lag past the cap; the old unconditional drop then discarded EVERY chunk
                # forever -- the mic went silent with no recovery even though audio kept
                # arriving. Instead keep shedding the backlog but force a decode every
                # force_decode_every_chunks: dropping N-1 + decoding 1 consumes audio faster
                # than real time, so captions continue AND the queue drains back toward
                # fresh audio (full recovery once the transient load eases).
                if chunks_since_decode < force_decode_every_chunks:
                    lag_dropped_stale_total += 1
                    emit_lag_snapshot_if_due()
                    continue
                lag_vad_forced_decode_total += 1  # count the forced catch-up decode
                # fall through to decode this (freshest available) chunk
            # Under moderate lag, skip short boundary-cut chunks so ASR processes
            # fewer calls and catches up without changing display/layout policy.
            chunk_audio_sec = max(0.0, float(chunk.end_sec) - float(chunk.start_sec))
            if skip_subchunks_when_lagged and processing_lag_sec > subchunk_lag_sec:
                if chunk_audio_sec < (nominal_chunk_sec * subchunk_min_ratio):
                    lag_dropped_subchunk_total += 1
                    emit_lag_snapshot_if_due()
                    continue
            # Dynamic decode simplification under lag:
            # tighten accepted minimum chunk duration as lag grows so decode
            # work converges toward fresh audio.
            if dynamic_decode_simplify_enabled and processing_lag_sec > dynamic_simplify_lag_sec:
                severity = min(1.0, (processing_lag_sec - dynamic_simplify_lag_sec) / max(dynamic_simplify_lag_sec, 1.0))
                dynamic_ratio = min(0.98, subchunk_min_ratio + (0.33 * severity))
                if chunk_audio_sec < (nominal_chunk_sec * dynamic_ratio):
                    lag_dropped_dynamic_total += 1
                    emit_lag_snapshot_if_due()
                    continue
            # Catch-up governor:
            # when lag persists, prioritize near-full chunks and thin decode load
            # if decoder is running slower than realtime.
            if processing_lag_sec > catchup_lag_sec:
                if (
                    chunks_since_decode < force_decode_every_chunks
                    and chunk_audio_sec < (nominal_chunk_sec * catchup_full_chunk_ratio)
                ):
                    lag_dropped_dynamic_total += 1
                    emit_lag_snapshot_if_due()
                    continue
                decode_ratio_avg = (
                    (lag_decode_elapsed_total / lag_decode_audio_total)
                    if lag_decode_audio_total > 0.0
                    else 0.0
                )
                if (
                    chunks_since_decode < force_decode_every_chunks
                    and decode_ratio_avg > target_decode_ratio
                    and processing_lag_sec > hard_drop_lag_sec
                ):
                    severity = min(
                        1.0,
                        (processing_lag_sec - hard_drop_lag_sec) / max(hard_drop_lag_sec, 1.0),
                    )
                    keep_every = 2 + int(severity * 2.0)  # 2..4
                    if (lag_total_seen % keep_every) != 0:
                        lag_dropped_dynamic_total += 1
                        emit_lag_snapshot_if_due()
                        continue
        if not is_speech_chunk(chunk.pcm_bytes, audio_cfg.sample_rate, audio_cfg.frame_ms, vad_cfg):
            lag_vad_reject_total += 1
            if not (
                force_decode_on_vad_reject
                and chunks_since_decode >= force_decode_on_vad_reject_every_chunks
            ):
                emit_lag_snapshot_if_due()
                continue
            lag_vad_forced_decode_total += 1
        if asr_lock is not None:
            lock_wait_start = time.perf_counter()
            with asr_lock:
                # Advance the pipeline reference time by however long we waited for
                # the lock so that blocked time doesn't accumulate as processing lag.
                pipeline_started_at += time.perf_counter() - lock_wait_start
                if _trace:
                    sys.stderr.write(f"[trace] transcribe start (locked) bytes={len(chunk.pcm_bytes)}\n"); sys.stderr.flush()
                infer_start = time.perf_counter()
                result = asr.transcribe(chunk.pcm_bytes)
                elapsed = time.perf_counter() - infer_start
                if _trace:
                    sys.stderr.write(f"[trace] transcribe done in {elapsed:.2f}s text={result.get('text','')!r}\n"); sys.stderr.flush()
        else:
            if _trace:
                sys.stderr.write(f"[trace] transcribe start bytes={len(chunk.pcm_bytes)}\n"); sys.stderr.flush()
            infer_start = time.perf_counter()
            result = asr.transcribe(chunk.pcm_bytes)
            elapsed = time.perf_counter() - infer_start
            if _trace:
                sys.stderr.write(f"[trace] transcribe done in {elapsed:.2f}s text={result.get('text','')!r}\n"); sys.stderr.flush()
        if stats_hook:
            audio_sec = max(0.0, chunk.end_sec - chunk.start_sec)
            stats_hook(elapsed, audio_sec)
        if not result["text"]:
            emit_lag_snapshot_if_due()
            continue
        chunks_since_decode = 0
        lag_decoded_total += 1
        audio_sec = max(0.0, chunk.end_sec - chunk.start_sec)
        lag_decode_audio_total += audio_sec
        lag_decode_elapsed_total += elapsed
        best_avg = result.get("best_avg_logprob")
        if best_avg is not None and best_avg < asr_cfg.min_avg_logprob:
            continue
        seg_list = []
        dropped_hallucination = 0
        for seg in result.get("segments", []):
            # Drop canned near-silence fillers ("Thanks for watching!", subtitle credits).
            # They arrive with high confidence, so the logprob gate above misses them; this
            # matches the whole segment text against a known set. See what/hallucination.py.
            if is_hallucination(seg.get("text", "")):
                dropped_hallucination += 1
                continue
            segment_index += 1
            seg_id = f"{segment_id_prefix}s{segment_index:06d}"
            # Per-word timestamps when the engine provides them (WhisperKit and
            # faster_whisper do) -- absolute session seconds like abs_start, so they map
            # straight onto the session recording for word-level click-to-replay and finer
            # training alignment. Optional: engines without word timing omit them and the
            # UI falls back to segment-level seeking.
            words = [
                {
                    "word": w.get("word", ""),
                    "abs_start": float(timeline_offset_sec + chunk.start_sec + w.get("start", 0.0)),
                    "abs_end": float(timeline_offset_sec + chunk.start_sec + w.get("end", 0.0)),
                }
                for w in (seg.get("words") or [])
            ]
            seg_list.append(
                {
                    "id": seg_id,
                    "index": segment_index,
                    "start": seg.get("start", 0.0),
                    "end": seg.get("end", 0.0),
                    "abs_start": float(timeline_offset_sec + chunk.start_sec + seg.get("start", 0.0)),
                    # Both seg.start and seg.end are relative to the START of this
                    # chunk's audio, so both offset from chunk.start_sec. Using
                    # chunk.end_sec here pushed every segment's end a full chunk late
                    # (2.5s at the default chunk size), which made consecutive segments
                    # overlap and stretched the mouth's terminal viseme past the audio.
                    "abs_end": float(timeline_offset_sec + chunk.start_sec + seg.get("end", 0.0)),
                    "text": seg.get("text", ""),
                    "avg_logprob": seg.get("avg_logprob"),
                    "words": words,
                }
            )
        if dropped_hallucination and not seg_list:
            # The whole chunk was near-silence filler; emit nothing at all.
            emit_lag_snapshot_if_due()
            continue
        # When only some segments were filtered, keep the chunk-level text in step with the
        # segments that survived so the caption text can't still show the dropped phrase.
        chunk_text = result["text"]
        if dropped_hallucination:
            chunk_text = "".join(s["text"] for s in seg_list).strip()
        event = {
            "type": "segment",
            "chunk_index": chunk_index,
            "chunk_start": timeline_offset_sec + chunk.start_sec,
            "chunk_end": timeline_offset_sec + chunk.end_sec,
            "chunk_cut_samples": int(chunk.cut_samples or 0),
            "chunk_boundary_scores": list(chunk.boundary_scores or []),
            "text": chunk_text,
            "language": result["language"],
            "language_probability": result["language_probability"],
            "segments": seg_list,
        }
        ops = caption_ops.build(seg_list, int(time.time() * 1000.0))
        if ops:
            event["caption_ops"] = ops
        decode_ratio_avg = (
            (lag_decode_elapsed_total / lag_decode_audio_total)
            if lag_decode_audio_total > 0.0
            else 0.0
        )
        event["lag"] = {
            "processing_lag_sec": float(lag_processing_lag_sec),
            "decode_audio_ratio_avg": float(decode_ratio_avg),
            "chunks_seen_total": int(lag_total_seen),
            "chunks_decoded_total": int(lag_decoded_total),
            "dropped_stale_total": int(lag_dropped_stale_total),
            "dropped_subchunk_total": int(lag_dropped_subchunk_total),
            "dropped_dynamic_total": int(lag_dropped_dynamic_total),
            "vad_reject_total": int(lag_vad_reject_total),
            "vad_forced_decode_total": int(lag_vad_forced_decode_total),
        }
        emit_lag_snapshot_if_due()
        chunk_index += 1
        if event_enricher:
            event_enricher(event)
        output.enrich_event(event)
        output.write_event(event)
        if on_event:
            on_event(event)
