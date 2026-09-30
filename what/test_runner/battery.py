import json
import os
import time
from itertools import product
from typing import Any

from ..asr import AsrConfig
from ..audio import AudioConfig
from ..vad import VadConfig
from .alignment import error_word_stats
from .quality import phrase_count, stutter_score
from .transcribe import transcribe_file_streaming
from .types import Case
from .wer import edit_stats, word_error_rate


def run_battery(
    cases: list[Case],
    audio_cfg: AudioConfig,
    vad_cfg: VadConfig,
    asr_cfg: AsrConfig,
    max_wer: float,
    log_path: str,
    model_sizes: list[str] | None = None,
    reporter: Any | None = None,
) -> None:
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    params = {
        "model_size": model_sizes or ["small", "medium", "large-v2"],
        "beam_size": [1, 5, 8],
        "no_speech_threshold": [0.6, 0.8],
        "vad_mode": [2, 3],
        "vad_speech_ratio": [0.2, 0.3],
        "overlap_ms": [0, 100],
        "chunk_ms": [800, 1200],
        "condition_on_previous_text": [False, True],
    }

    keys = list(params.keys())
    combos = list(product(*[params[k] for k in keys]))
    total = len(combos)
    if reporter:
        reporter.suite_total = total
    for _, values in enumerate(combos, start=1):
        overrides = dict(zip(keys, values))
        run_audio = AudioConfig(
            sample_rate=audio_cfg.sample_rate,
            channels=audio_cfg.channels,
            frame_ms=audio_cfg.frame_ms,
            chunk_ms=overrides["chunk_ms"],
            overlap_ms=overrides["overlap_ms"],
        )
        run_vad = VadConfig(
            enabled=vad_cfg.enabled,
            mode=overrides["vad_mode"],
            speech_ratio=overrides["vad_speech_ratio"],
        )
        run_asr = AsrConfig(
            model_size=overrides["model_size"],
            compute_type=asr_cfg.compute_type,
            beam_size=overrides["beam_size"],
            language=asr_cfg.language,
            device=asr_cfg.device,
            min_avg_logprob=asr_cfg.min_avg_logprob,
            no_speech_threshold=overrides["no_speech_threshold"],
            logprob_threshold=asr_cfg.logprob_threshold,
            compression_ratio_threshold=asr_cfg.compression_ratio_threshold,
            condition_on_previous_text=overrides["condition_on_previous_text"],
        )

        suite = {
            "timestamp": time.time(),
            "settings": overrides,
            "cases": [],
            "overall": {},
        }
        if reporter:
            reporter.start_suite(overrides)
        total_sub = total_ins = total_del = 0
        total_ref = 0
        stutter_sum = 0.0
        thanks_sum = 0
        pass_count = 0
        for case in cases:
            text = transcribe_file_streaming(case.audio, run_audio, run_vad, run_asr)
            wer = word_error_rate(case.text, text)
            stats = edit_stats(case.text, text)
            stutter = stutter_score(text)
            thanks = phrase_count(text, "thanks for watching")
            errors = error_word_stats(case.text, text)
            passed = wer <= max_wer
            if passed:
                pass_count += 1
            suite["cases"].append(
                {
                    "id": case.case_id,
                    "audio": case.audio,
                    "wer": wer,
                    "pass": passed,
                    "sub": stats["sub"],
                    "ins": stats["ins"],
                    "del": stats["del"],
                    "stutter": stutter,
                    "thanks_for_watching": thanks,
                    "error_words": errors,
                }
            )
            if reporter:
                reporter.case_result(
                    case.case_id,
                    {
                        "wer": wer,
                        "pass": passed,
                        "sub": stats["sub"],
                        "ins": stats["ins"],
                        "del": stats["del"],
                        "stutter": stutter,
                        "thanks": thanks,
                    },
                )
            total_sub += stats["sub"]
            total_ins += stats["ins"]
            total_del += stats["del"]
            total_ref += stats["ref_words"]
            stutter_sum += stutter
            thanks_sum += thanks

        total_err = total_sub + total_ins + total_del
        suite["overall"] = {
            "wer": total_err / max(total_ref, 1),
            "sub": total_sub,
            "ins": total_ins,
            "del": total_del,
            "stutter": stutter_sum / max(len(cases), 1),
            "thanks_for_watching": thanks_sum,
            "pass_rate": pass_count / max(len(cases), 1),
        }
        if reporter:
            reporter.suite_done(suite["overall"])

        with open(log_path, "a", encoding="ascii") as f:
            f.write(json.dumps(suite, ensure_ascii=True) + "\n")
            f.flush()
