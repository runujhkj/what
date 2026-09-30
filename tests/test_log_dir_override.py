"""WHAT_JSONL_DIR redirects recordings/transcripts to a writable dir (packaged app)."""
from argparse import Namespace
from pathlib import Path

from what.cli.builders import build_output_cfg
from what.controller.controller_route_utils import resolve_log_root


def _args():
    return Namespace(
        jsonl_log=None, jsonl_dir=None, text_stream=False, no_text_stream=False,
        text_mode=None, text_window_segments=None, text_window_chars=None,
        text_block_clear=False, no_text_block_clear=False,
        text_normalize=False, no_text_normalize=False,
    )


def _cfg():
    return {"output": {"text_stream": False, "jsonl_log": "", "jsonl_dir": "logs"}}


def test_build_output_cfg_prefers_env(monkeypatch):
    monkeypatch.setenv("WHAT_JSONL_DIR", "/writable/logs")
    out = build_output_cfg(_args(), _cfg())
    assert out.jsonl_dir == "/writable/logs"


def test_build_output_cfg_falls_back_to_config(monkeypatch):
    monkeypatch.delenv("WHAT_JSONL_DIR", raising=False)
    out = build_output_cfg(_args(), _cfg())
    assert out.jsonl_dir == "logs"


def test_build_output_cfg_flag_beats_env(monkeypatch):
    monkeypatch.setenv("WHAT_JSONL_DIR", "/writable/logs")
    args = _args()
    args.jsonl_dir = "/explicit"
    assert build_output_cfg(args, _cfg()).jsonl_dir == "/explicit"


def test_resolve_log_root_prefers_env(monkeypatch):
    monkeypatch.setenv("WHAT_JSONL_DIR", "/writable/logs")
    cfg = Namespace(config_path=None)
    assert resolve_log_root(cfg, Path("/read/only/root")) == Path("/writable/logs")


def test_resolve_log_root_without_env_uses_repo_root(monkeypatch):
    monkeypatch.delenv("WHAT_JSONL_DIR", raising=False)
    cfg = Namespace(config_path=None)
    # Relative config default resolves under the given (repo) root.
    assert resolve_log_root(cfg, Path("/repo")) == Path("/repo/logs")
