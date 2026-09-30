"""Coverage for the CLI boot layer.

Covers argv parsing (parser.py, args_*.py), command dispatch (main.py), and the
ServiceConfig precedence in handle_service.py -- the entry/config layer that assembles
configuration and routes commands, which had no coverage when the service startup
regression shipped.
"""
from __future__ import annotations

import argparse

import pytest

import what.cli.main as cli_main
from what.cli.parser import build_parser


# --- parsing -----------------------------------------------------------------

def test_bare_run_defaults_are_none():
    args = build_parser().parse_args(["run"])
    assert args.command == "run"
    # Unset options default to None so config/env can supply them downstream.
    assert args.model is None and args.device is None and args.chunk_ms is None
    assert args.no_vad is False  # store_true flags default False


def test_numeric_flags_are_coerced():
    args = build_parser().parse_args(
        ["service", "--port", "8790", "--max-clients", "2", "--chunk-ms", "2500", "--beam-size", "3"]
    )
    assert args.command == "service"
    assert args.port == 8790 and isinstance(args.port, int)
    assert args.max_clients == 2
    assert args.chunk_ms == 2500
    assert args.beam_size == 3


def test_store_true_flag_sets_boolean():
    args = build_parser().parse_args(["service", "--no-mdns", "--no-vad"])
    assert args.no_mdns is True
    assert args.no_vad is True


@pytest.mark.parametrize(
    "argv",
    [
        ["run", "--input", "telepathy"],       # not in input choices
        ["run", "--engine", "bogus"],          # not in engine choices
        ["service", "--port", "not-a-number"],  # int coercion fails
    ],
)
def test_invalid_values_are_rejected(argv):
    with pytest.raises(SystemExit):
        build_parser().parse_args(argv)


@pytest.mark.parametrize(
    "command",
    ["run", "service", "client", "view", "log", "control", "start", "gui"],
)
def test_every_command_parses(command):
    # pair / control-client have required options and are parsed with them elsewhere.
    args = build_parser().parse_args([command])
    assert args.command == command


def test_commands_with_required_options_parse():
    args = build_parser().parse_args(["pair", "-k", "sess-key"])
    assert args.command == "pair" and args.session_key == "sess-key"


def test_pair_has_config_args_so_dispatch_can_load_cfg():
    # Regression: main() calls load_cfg(args.config, ...) before dispatching pair, so the
    # pair subparser must define these or `what pair -k KEY` raises AttributeError.
    args = build_parser().parse_args(["pair", "-k", "sess-key"])
    assert args.config is None
    assert args.preset is None
    assert args.profile is None


# --- dispatch ----------------------------------------------------------------

@pytest.fixture
def _stub_dispatch(monkeypatch):
    """Neutralize config/env loading and record which handler main() calls."""
    calls: list[str] = []
    for name in (
        "handle_run", "handle_service", "handle_client", "handle_view", "handle_pair",
        "handle_log", "handle_control", "handle_control_client", "handle_start", "handle_gui",
    ):
        monkeypatch.setattr(cli_main, name, (lambda n: (lambda *a, **k: calls.append(n)))(name))
    monkeypatch.setattr(cli_main, "load_cfg", lambda *a, **k: {"service": {}})
    monkeypatch.setattr(cli_main, "validate_language", lambda *a, **k: None)
    monkeypatch.setattr(cli_main, "load_env", lambda *a, **k: None)
    return calls


def _run_main(monkeypatch, argv: list[str]):
    monkeypatch.setattr(cli_main.sys, "argv", ["what"] + argv)


def test_no_args_dispatches_run(monkeypatch, _stub_dispatch):
    _run_main(monkeypatch, [])
    cli_main.main()
    assert _stub_dispatch == ["handle_run"]


def test_leading_option_implies_run(monkeypatch, _stub_dispatch):
    # A leading option (no subcommand token) is treated as an implicit `run`.
    _run_main(monkeypatch, ["--jsonl-dir", "/tmp/x"])
    cli_main.main()
    assert _stub_dispatch == ["handle_run"]


@pytest.mark.parametrize(
    "argv,handler",
    [
        (["service"], "handle_service"),
        (["gui"], "handle_gui"),
        (["view"], "handle_view"),
        (["control"], "handle_control"),
        (["start"], "handle_start"),
        (["client"], "handle_client"),
        (["pair", "-k", "sess-key"], "handle_pair"),
    ],
)
def test_command_routes_to_handler(monkeypatch, _stub_dispatch, argv, handler):
    _run_main(monkeypatch, argv)
    cli_main.main()
    assert _stub_dispatch == [handler]


def test_service_selects_env_file_when_present(monkeypatch, _stub_dispatch):
    monkeypatch.delenv("WHAT_ENV_FILE", raising=False)
    monkeypatch.setattr(cli_main.os.path, "exists", lambda p: p == ".env.service")
    _run_main(monkeypatch, ["service"])
    cli_main.main()
    assert cli_main.os.environ.get("WHAT_ENV_FILE") == ".env.service"


# --- handle_service ServiceConfig precedence ---------------------------------

@pytest.fixture
def _captured_service(monkeypatch):
    """Run handle_service with the heavy bits stubbed, capturing the ServiceConfig it
    builds so precedence (CLI flag > env var > config file) can be asserted."""
    import what.cli.handle_service as hs
    import what.cuda_runtime as cuda_runtime
    from what.config import load_config

    captured: dict[str, object] = {}
    # prepare_service_runtime is imported inside handle_service from cuda_runtime, so patch
    # it at the source module rather than on handle_service.
    monkeypatch.setattr(cuda_runtime, "prepare_service_runtime", lambda *a, **k: None)
    monkeypatch.setattr(hs, "detect_gpu", lambda *a, **k: None)
    monkeypatch.setattr(hs, "run_service_tests", lambda *a, **k: False)
    monkeypatch.setattr(hs, "run_service",
                        lambda *a, **k: captured.__setitem__("service_cfg", a[4]))
    cfg = load_config("config/default.toml")

    def _run(extra_argv=None):
        # device is pinned so detect_gpu / auto-cpu never runs in the test.
        argv = ["service", "--device", "cpu"] + (extra_argv or [])
        args = build_parser().parse_args(argv)
        hs.handle_service(args, cfg)
        return captured["service_cfg"]

    return _run


def test_service_config_uses_config_defaults(monkeypatch, _captured_service):
    for key in ("WHAT_SERVICE_PORT", "WHAT_SERVICE_HOST"):
        monkeypatch.delenv(key, raising=False)
    svc = _captured_service()
    assert svc.port == 8765  # from config/default.toml [service]
    assert svc.max_clients == 4


def test_env_overrides_config(monkeypatch, _captured_service):
    monkeypatch.setenv("WHAT_SERVICE_PORT", "8801")
    svc = _captured_service()
    assert svc.port == 8801


def test_flag_overrides_env_and_config(monkeypatch, _captured_service):
    monkeypatch.setenv("WHAT_SERVICE_PORT", "8801")
    svc = _captured_service(["--port", "8888"])
    assert svc.port == 8888


def test_no_mdns_flag_disables_mdns(monkeypatch, _captured_service):
    svc = _captured_service(["--no-mdns"])
    assert svc.mdns_enabled is False
