"""End-to-end boot smoke test: the service process actually starts and serves /health.

This guards the gap that let a startup-ordering regression ship unnoticed -- the ASR
warmup used to run before uvicorn bound the port, so the service accepted no connections
until the (possibly doubled) model load finished and the GUI reported "Failed to fetch".
Nothing in the suite booted the real process, so nothing caught it.

Launched with --device cuda and no tty, run_service defers warmup to a background thread;
the port must answer /health long before the model is ready. The model is not required:
warmup may resolve to ready (CUDA or the CPU fallback) or to error (no model cached
offline), but either way the server must respond while it works.
"""
from __future__ import annotations

import json
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import pytest

pytest.importorskip("faster_whisper", reason="service boot needs the faster-whisper engine")

_REPO_ROOT = Path(__file__).resolve().parents[1]


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _get_health(port: int) -> dict | None:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=0.5) as resp:
            if resp.status != 200:
                return None
            return json.loads(resp.read().decode("utf-8"))
    except Exception:
        return None


def test_service_boots_and_serves_health():
    port = _free_port()
    proc = subprocess.Popen(
        [
            sys.executable, "-m", "what", "service",
            "--host", "127.0.0.1", "--port", str(port),
            "--engine", "faster_whisper", "--device", "cuda", "--model", "base",
            "--no-mdns",
        ],
        cwd=str(_REPO_ROOT),
        stdin=subprocess.DEVNULL,  # non-interactive -> background warmup path
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    try:
        # The port must start answering well before any model finishes loading. Generous
        # deadline so a slow importer/CI box doesn't flake; pre-fix this would time out
        # because the port stayed closed through the whole warmup.
        deadline = time.time() + 30.0
        payload = None
        while time.time() < deadline:
            if proc.poll() is not None:
                out = proc.stdout.read().decode("utf-8", "replace") if proc.stdout else ""
                pytest.fail(f"service exited early (code {proc.returncode}):\n{out}")
            payload = _get_health(port)
            if payload is not None:
                break
            time.sleep(0.25)
        assert payload is not None, "service never served /health"
        assert payload["status"] == "ok"
        assert payload["asr"] in {"loading", "ready", "error"}
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=5)
