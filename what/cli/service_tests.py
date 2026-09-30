import os
import sys

from .helpers import make_log_path, tune_suggestion
from ..env import get_env, get_env_float
from ..reporting import RunReporter
from ..test_runner import (
    edit_stats,
    load_cases,
    run_battery,
    select_cases,
    stutter_score,
    transcribe_file_streaming,
    word_error_rate,
)


def run_service_tests(args, audio_cfg, vad_cfg, asr_cfg) -> bool:
    if not (args.files or args.test_error or args.tune or args.battery):
        return False
    cases_path = os.path.join("tests", "cases.json")
    cases = load_cases(cases_path)
    selected = select_cases(cases, args.files)
    max_wer = get_env_float("WHAT_TEST_MAX_WER", 0.2) or 0.2
    totals = {"sub": 0, "ins": 0, "del": 0, "ref_words": 0, "stutter_sum": 0.0, "stutter_count": 0}

    if args.battery:
        raw_models = args.battery_models or get_env("WHAT_BATTERY_MODELS")
        models = None
        if raw_models:
            models = [m.strip() for m in raw_models.split(",") if m.strip()]
        log_path = make_log_path("battery")
        reporter = RunReporter(
            run_type="battery",
            cases=[c.case_id for c in selected],
            suite_total=1,
            live=True,
            log_path=log_path,
        )
        run_battery(
            selected,
            audio_cfg,
            vad_cfg,
            asr_cfg,
            max_wer,
            log_path,
            model_sizes=models,
            reporter=reporter,
        )
        reporter.run_done()
        return True
    if args.test_error or args.tune:
        reporter = None
        if args.test_error:
            log_path = make_log_path("test")
            reporter = RunReporter(
                run_type="test-error",
                cases=[c.case_id for c in selected],
                suite_total=1,
                live=True,
                log_path=log_path,
            )
            settings = {
                "model_size": asr_cfg.model_size,
                "beam_size": asr_cfg.beam_size,
                "no_speech_threshold": asr_cfg.no_speech_threshold,
                "vad_mode": vad_cfg.mode,
                "vad_speech_ratio": vad_cfg.speech_ratio,
                "overlap_ms": audio_cfg.overlap_ms,
                "chunk_ms": audio_cfg.chunk_ms,
                "condition_on_previous_text": asr_cfg.condition_on_previous_text,
            }
            reporter.start_suite(settings)
        total_sub = total_ins = total_del = 0
        total_ref = 0
        stutter_sum = 0.0
        thanks_sum = 0
        pass_count = 0
        for case in selected:
            on_delta = reporter.update_transcript if reporter else None
            text = transcribe_file_streaming(case.audio, audio_cfg, vad_cfg, asr_cfg, on_delta)
            wer = word_error_rate(case.text, text)
            stats = edit_stats(case.text, text)
            stutter = stutter_score(text)
            thanks = 0
            passed = wer <= max_wer
            if passed:
                pass_count += 1
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
            totals["sub"] += stats["sub"]
            totals["ins"] += stats["ins"]
            totals["del"] += stats["del"]
            totals["ref_words"] += stats["ref_words"]
            totals["stutter_sum"] += stutter
            totals["stutter_count"] += 1

        total_err = total_sub + total_ins + total_del
        overall = {
            "wer": total_err / max(total_ref, 1),
            "sub": total_sub,
            "ins": total_ins,
            "del": total_del,
            "stutter": stutter_sum / max(len(selected), 1),
            "thanks_for_watching": thanks_sum,
            "pass_rate": pass_count / max(len(selected), 1),
        }
        if reporter:
            reporter.suite_done(overall)
            reporter.run_done()
        if args.tune and totals["ref_words"]:
            total_err = totals["sub"] + totals["ins"] + totals["del"]
            overall_wer = total_err / totals["ref_words"]
            stutter_avg = totals["stutter_sum"] / max(totals["stutter_count"], 1)
            sys.stdout.write(
                f"overall: wer={overall_wer:.3f} sub={totals['sub']} ins={totals['ins']} "
                f"del={totals['del']} stutter={stutter_avg:.3f}\n"
            )
            sys.stdout.write(
                tune_suggestion(
                    totals["sub"],
                    totals["ins"],
                    totals["del"],
                    audio_cfg,
                    vad_cfg,
                    asr_cfg,
                )
                + "\n"
            )
        return True
    return False
