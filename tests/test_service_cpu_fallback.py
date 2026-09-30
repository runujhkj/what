"""A managed (non-interactive) service reaches HTTP startup even when CUDA runtime
libraries are absent, and the CUDA->CPU fallback happens off the port-binding path so the
client never sees a refused connection while the model loads."""
import importlib
import threading
from types import SimpleNamespace
from unittest.mock import Mock

import pytest


@pytest.fixture(autouse=True)
def _unknown_gpu_compute_types(monkeypatch):
    # Keep the ladder hermetic: without this it would query the test host's real GPU.
    warmup = importlib.import_module("what.service.warmup")
    monkeypatch.setattr(warmup, "supported_compute_types", lambda *a, **k: None)
    monkeypatch.setenv("WHAT_GPU_AUTO_BUDGET", "0")


def _runtime(device="cuda", compute_type="float16", model_size="medium"):
    return SimpleNamespace(
        asr_cfg=SimpleNamespace(
            device=device, compute_type=compute_type, model_size=model_size, model_path=None,
        ),
        spare_asr=None,
        asr_status="loading",
        asr_error="",
        asr_ready_event=threading.Event(),
    )


def test_noninteractive_cuda_service_defers_warmup_and_binds_port(monkeypatch):
    service = importlib.import_module("what.service.run")
    cfg = SimpleNamespace(engine="faster_whisper", device="cuda", compute_type="float16")

    # A GPU service must not block the port on a (possibly doubled) model load, and must
    # never prompt when launched by the GUI.
    monkeypatch.setattr(service, "_decode_preflight",
                        Mock(side_effect=AssertionError("must not preflight synchronously")))
    monkeypatch.setattr(service.sys, "stdin", SimpleNamespace(isatty=lambda: False))
    monkeypatch.setattr("builtins.input", Mock(side_effect=AssertionError("GUI must not prompt")))
    monkeypatch.setattr(service, "get_env", lambda key: "test-session")
    app = object()
    create = Mock(return_value=app)
    serve = Mock()
    monkeypatch.setattr(service, "create_app", create)
    monkeypatch.setattr(service.uvicorn, "run", serve)

    service.run_service(None, None, cfg, SimpleNamespace(jsonl_dir="logs"),
                        SimpleNamespace(host="127.0.0.1", port=8765))

    # Port binds (uvicorn is invoked) with no eager worker; warmup is deferred.
    assert serve.call_args.args == (app,)
    assert create.call_args.kwargs["warm_in_background"] is True
    assert create.call_args.kwargs["spare_asr"] is None


def test_fallback_steps_ladder_order(monkeypatch):
    warmup = importlib.import_module("what.service.warmup")
    cfg = SimpleNamespace(device="cuda", compute_type="float16", model_size="medium", model_path=None)
    steps = warmup.fallback_steps(cfg)
    assert steps == [
        ("cuda", "cuda", "float16", "medium"),
        ("cuda-int8", "cuda", "int8_float16", "medium"),
        ("cuda-small", "cuda", "int8_float16", "small"),
        ("cpu", "cpu", "int8", "medium"),
    ]
    # A non-CUDA start is a single attempt at the configured settings.
    cpu_cfg = SimpleNamespace(device="cpu", compute_type="int8", model_size="small", model_path=None)
    assert warmup.fallback_steps(cpu_cfg) == [("configured", "cpu", "int8", "small")]


def test_estimate_vram_scales_with_model_and_compute():
    warmup = importlib.import_module("what.service.warmup")
    assert warmup.estimate_vram_mb("medium", "float16") == 2200
    assert warmup.estimate_vram_mb("medium", "int8_float16") == 1430  # ~0.65x
    assert warmup.estimate_vram_mb("small", "float16") == 1100
    assert warmup.estimate_vram_mb("unknown-model", "float16") is None


def test_budget_picks_largest_model_that_fits():
    warmup = importlib.import_module("what.service.warmup")
    cfg = SimpleNamespace(device="cuda", compute_type="float16", model_size="medium", model_path=None)
    # 1500 MiB total across 2 workers -> 750 MiB/worker.
    steps = warmup.fallback_steps(cfg, budget_mb=1500, max_workers=2)
    # Largest fitting is small/int8 (~715 MiB); medium (>1400) is excluded.
    assert steps[0] == ("cuda:small/int8_float16", "cuda", "int8_float16", "small")
    assert steps[-1] == ("cpu", "cpu", "int8", "medium")  # CPU always the floor
    gpu = [s for s in steps if s[1] == "cuda"]
    assert all(warmup.estimate_vram_mb(s[3], s[2]) <= 750 for s in gpu)
    assert not any(s[3] == "medium" and s[1] == "cuda" for s in steps)  # never over budget


def test_budget_too_small_leaves_only_cpu():
    warmup = importlib.import_module("what.service.warmup")
    cfg = SimpleNamespace(device="cuda", compute_type="float16", model_size="medium", model_path=None)
    steps = warmup.fallback_steps(cfg, budget_mb=200, max_workers=1)
    assert steps == [("cpu", "cpu", "int8", "medium")]


def test_budget_with_model_path_varies_only_compute():
    warmup = importlib.import_module("what.service.warmup")
    cfg = SimpleNamespace(device="cuda", compute_type="float16", model_size="medium",
                          model_path="/models/custom")
    steps = warmup.fallback_steps(cfg, budget_mb=5000, max_workers=1)
    # No model swap for a custom path; only the configured model at fp16/int8, then CPU.
    gpu_models = {s[3] for s in steps if s[1] == "cuda"}
    assert gpu_models == {"medium"}
    assert steps[0] == ("cuda:medium/float16", "cuda", "float16", "medium")


def test_budget_resolves_engine_to_fitting_config(monkeypatch):
    warmup = importlib.import_module("what.service.warmup")
    cfg = SimpleNamespace(device="cuda", compute_type="float16", model_size="medium", model_path=None)
    worker = object()
    monkeypatch.setattr(warmup, "decode_preflight", lambda c: worker)
    asr = warmup.resolve_engine_with_fallback(cfg, log=lambda m: None, budget_mb=1500, max_workers=2)
    assert asr is worker
    # Settled on the budgeted top rung, on the GPU, not CPU.
    assert cfg.device == "cuda" and cfg.model_size == "small" and cfg.compute_type == "int8_float16"


def test_warmup_prefers_smaller_gpu_model_over_cpu(monkeypatch):
    # The user's case: GPU only partly free. medium float16 and medium int8 OOM, but a
    # small model fits -- stay on the GPU rather than collapsing to a slow CPU decode.
    warmup = importlib.import_module("what.service.warmup")
    runtime = _runtime()
    worker = object()
    attempts = []

    def preflight(config):
        attempts.append((config.device, config.compute_type, config.model_size))
        if config.device == "cuda" and config.model_size == "medium":
            raise RuntimeError("CUDA failed with error out of memory")
        return worker  # cuda + small succeeds

    monkeypatch.setattr(warmup, "decode_preflight", preflight)
    warmup.warm_up_in_background(runtime)
    assert runtime.asr_ready_event.wait(timeout=5.0)

    assert attempts == [
        ("cuda", "float16", "medium"),
        ("cuda", "int8_float16", "medium"),
        ("cuda", "int8_float16", "small"),
    ]
    assert ("cpu", "int8", "medium") not in attempts  # never fell to CPU
    assert runtime.asr_cfg.device == "cuda"
    assert runtime.asr_cfg.model_size == "small"
    assert runtime.spare_asr is worker
    assert runtime.asr_status == "ready"


def test_warmup_descends_to_cpu_when_gpu_unusable(monkeypatch):
    warmup = importlib.import_module("what.service.warmup")
    runtime = _runtime()
    worker = object()
    attempts = []

    def preflight(config):
        attempts.append((config.device, config.compute_type, config.model_size))
        if config.device == "cuda":
            raise RuntimeError("Library libcublas.so.12 is not found or cannot be loaded")
        return worker

    monkeypatch.setattr(warmup, "decode_preflight", preflight)
    warmup.warm_up_in_background(runtime)
    assert runtime.asr_ready_event.wait(timeout=5.0)

    # All GPU rungs tried, then CPU/int8 with the configured model.
    assert attempts[-1] == ("cpu", "int8", "medium")
    assert runtime.asr_cfg.device == "cpu"
    assert runtime.asr_cfg.compute_type == "int8"
    assert runtime.spare_asr is worker
    assert runtime.asr_status == "ready"


def test_warmup_reports_error_when_everything_fails(monkeypatch):
    warmup = importlib.import_module("what.service.warmup")
    runtime = _runtime()

    def preflight(config):
        raise RuntimeError("no backend available")

    monkeypatch.setattr(warmup, "decode_preflight", preflight)
    warmup.warm_up_in_background(runtime)
    assert runtime.asr_ready_event.wait(timeout=5.0)

    assert runtime.asr_status == "error"
    assert "no backend available" in runtime.asr_error
    assert runtime.spare_asr is None


PASCAL = {"float32", "int8", "int8_float32"}  # e.g. GTX 1080: no efficient float16


def test_ladder_uses_supported_compute_on_float16_less_gpu():
    warmup = importlib.import_module("what.service.warmup")
    cfg = SimpleNamespace(device="cuda", compute_type="float16", model_size="medium", model_path=None)
    steps = warmup.fallback_steps(cfg, supported=PASCAL)
    # float16 and int8_float16 both resolve to int8_float32, so that rung is tried once.
    assert steps == [
        ("cuda", "cuda", "int8_float32", "medium"),
        ("cuda-small", "cuda", "int8_float32", "small"),
        ("cpu", "cpu", "int8", "medium"),
    ]


def test_budget_on_float16_less_gpu_counts_float32_size():
    warmup = importlib.import_module("what.service.warmup")
    cfg = SimpleNamespace(device="cuda", compute_type="float16", model_size="medium", model_path=None)
    # 3000 MiB / 2 workers = 1500: medium float32 (~3960) must not be chosen; int8 (~1430) fits.
    steps = warmup.fallback_steps(cfg, budget_mb=3000, max_workers=2, supported=PASCAL)
    assert steps[0] == ("cuda:medium/int8_float32", "cuda", "int8_float32", "medium")
    assert not any(s[2] in {"float16", "int8_float16"} for s in steps)


def test_resolve_queries_gpu_compute_types(monkeypatch):
    warmup = importlib.import_module("what.service.warmup")
    monkeypatch.setattr(warmup, "supported_compute_types", lambda *a, **k: PASCAL)
    cfg = SimpleNamespace(device="cuda", device_index=0, compute_type="float16",
                          model_size="medium", model_path=None)
    monkeypatch.setattr(warmup, "decode_preflight", lambda c: object())
    warmup.resolve_engine_with_fallback(cfg, log=lambda m: None)
    assert (cfg.device, cfg.compute_type, cfg.model_size) == ("cuda", "int8_float32", "medium")


def test_effective_compute_type_substitutes_nearest_supported():
    from what.asr import effective_compute_type
    assert effective_compute_type("float16", PASCAL) == "int8_float32"
    assert effective_compute_type("int8_float16", PASCAL) == "int8_float32"
    assert effective_compute_type("float16", {"float16", "float32"}) == "float16"
    assert effective_compute_type("float16", None) == "float16"  # unknown -> unchanged


def test_float16_less_gpu_prefers_int8_over_float32():
    from what.asr import effective_compute_type
    # int8 is faster and half the VRAM on e.g. GTX 10-series; float32 only if int8 is absent.
    assert effective_compute_type("float16", {"float32", "int8", "int8_float32"}) == "int8_float32"
    assert effective_compute_type("float16", {"float32"}) == "float32"


def test_auto_budget_is_free_vram_minus_margin():
    warmup = importlib.import_module("what.service.warmup")
    cfg = SimpleNamespace(device="cuda", device_index=0)
    gpus = [{"name": "GTX 1080", "total_mb": 8192, "used_mb": 1400}]
    assert warmup.auto_budget_mb(cfg, query=lambda: gpus) == 8192 - 1400 - 512
    assert warmup.auto_budget_mb(cfg, query=lambda: []) == 0  # unknown -> no cap
    assert warmup.auto_budget_mb(SimpleNamespace(device="cpu"), query=lambda: gpus) == 0


def test_auto_budget_keeps_two_workers_on_8gb_pascal_within_vram():
    warmup = importlib.import_module("what.service.warmup")
    cfg = SimpleNamespace(device="cuda", compute_type="float16", model_size="medium", model_path=None)
    budget = warmup.auto_budget_mb(SimpleNamespace(device="cuda", device_index=0),
                                   query=lambda: [{"name": "x", "total_mb": 8192, "used_mb": 1400}])
    steps = warmup.fallback_steps(cfg, budget_mb=budget, max_workers=2, supported=PASCAL)
    assert steps[0] == ("cuda:medium/int8_float32", "cuda", "int8_float32", "medium")
