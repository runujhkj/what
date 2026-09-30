from typing import Any

from .types import SuiteResult


def suite_header(index: int, total: int, settings: dict[str, Any]) -> str:
    return (
        f"[{index}/{total}] model={settings['model_size']} beam={settings['beam_size']} "
        f"ns={settings['no_speech_threshold']} vad={settings['vad_mode']}/{settings['vad_speech_ratio']} "
        f"overlap={settings['overlap_ms']} chunk={settings['chunk_ms']} cond_prev={settings['condition_on_previous_text']}"
    )


def suite_better(current: SuiteResult, best: dict[str, Any]) -> bool:
    curr_overall = current.overall
    best_overall = best["overall"]
    if curr_overall.get("pass_rate") is not None and best_overall.get("pass_rate") is not None:
        if curr_overall["pass_rate"] != best_overall["pass_rate"]:
            return curr_overall["pass_rate"] > best_overall["pass_rate"]
    return curr_overall.get("wer", 1.0) < best_overall.get("wer", 1.0)


def suite_worse(current: SuiteResult, worst: dict[str, Any]) -> bool:
    curr_overall = current.overall
    worst_overall = worst["overall"]
    if curr_overall.get("pass_rate") is not None and worst_overall.get("pass_rate") is not None:
        if curr_overall["pass_rate"] != worst_overall["pass_rate"]:
            return curr_overall["pass_rate"] < worst_overall["pass_rate"]
    return curr_overall.get("wer", 0.0) > worst_overall.get("wer", 0.0)


def settings_line(settings: dict[str, Any]) -> str:
    return (
        f"model={settings['model_size']} beam={settings['beam_size']} ns={settings['no_speech_threshold']} "
        f"vad={settings['vad_mode']}/{settings['vad_speech_ratio']} overlap={settings['overlap_ms']} "
        f"chunk={settings['chunk_ms']} cond_prev={settings['condition_on_previous_text']}"
    )


def overall_line(overall: dict[str, Any]) -> str:
    return (
        f"wer={overall['wer']:.3f} sub={overall['sub']} ins={overall['ins']} del={overall['del']} "
        f"stutter={overall['stutter']:.3f} thanks={overall['thanks_for_watching']}"
    )
