"""Coverage plan chunk 2: request_pair_token network handling (all mocked)."""
from __future__ import annotations

import io
import json
import urllib.error
from types import SimpleNamespace

import pytest

from what import pair


class _Resp:
    def __init__(self, payload: dict):
        self._body = json.dumps(payload).encode("ascii")

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _http_error(code: int, body: bytes = b""):
    return urllib.error.HTTPError(
        url="http://x/pair", code=code, msg="err", hdrs=None, fp=io.BytesIO(body)
    )


def test_returns_token_on_success(monkeypatch):
    monkeypatch.setattr(pair.urllib.request, "urlopen", lambda *a, **k: _Resp({"token": "T-123"}))
    assert pair.request_pair_token("sess", "127.0.0.1", 8765, "/pair") == "T-123"


def test_missing_token_raises(monkeypatch):
    monkeypatch.setattr(pair.urllib.request, "urlopen", lambda *a, **k: _Resp({"nope": 1}))
    with pytest.raises(RuntimeError, match="No token"):
        pair.request_pair_token("sess", "127.0.0.1", 8765, "/pair")


def test_http_error_surfaces_code_and_body(monkeypatch):
    monkeypatch.setattr(
        pair.urllib.request, "urlopen",
        lambda *a, **k: (_ for _ in ()).throw(_http_error(500, b"boom")),
    )
    with pytest.raises(RuntimeError, match="pair failed: 500 boom"):
        pair.request_pair_token("sess", "127.0.0.1", 8765, "/pair")


def test_403_empty_body_retries_with_query(monkeypatch):
    calls = []

    def fake_urlopen(req, *a, **k):
        # First call (header-auth POST) 403s with no body; second call (query form) succeeds.
        url = getattr(req, "full_url", req)
        calls.append(url)
        if len(calls) == 1:
            raise _http_error(403, b"")
        return _Resp({"token": "T-retry"})

    monkeypatch.setattr(pair.urllib.request, "urlopen", fake_urlopen)
    token = pair.request_pair_token("sess", "127.0.0.1", 8765, "/pair")
    assert token == "T-retry"
    assert "session_key=sess" in calls[1]  # the retry carried the key as a query param


def test_403_with_body_does_not_retry(monkeypatch):
    monkeypatch.setattr(
        pair.urllib.request, "urlopen",
        lambda *a, **k: (_ for _ in ()).throw(_http_error(403, b"denied")),
    )
    with pytest.raises(RuntimeError, match="pair failed: 403 denied"):
        pair.request_pair_token("sess", "127.0.0.1", 8765, "/pair")


def test_url_error_raises(monkeypatch):
    monkeypatch.setattr(
        pair.urllib.request, "urlopen",
        lambda *a, **k: (_ for _ in ()).throw(urllib.error.URLError("no route")),
    )
    with pytest.raises(RuntimeError, match="pair failed:"):
        pair.request_pair_token("sess", "127.0.0.1", 8765, "/pair")


def test_no_host_discovers_service(monkeypatch):
    monkeypatch.setattr(
        pair, "discover_services",
        lambda: {"what": SimpleNamespace(host="10.0.0.5", port=9999)},
    )
    seen = {}

    def fake_urlopen(req, *a, **k):
        seen["url"] = getattr(req, "full_url", req)
        return _Resp({"token": "T-disc"})

    monkeypatch.setattr(pair.urllib.request, "urlopen", fake_urlopen)
    token = pair.request_pair_token("sess", None, 0, "/pair")
    assert token == "T-disc"
    assert "10.0.0.5:9999" in seen["url"]


def test_no_host_no_service_raises(monkeypatch):
    monkeypatch.setattr(pair, "discover_services", lambda: {})
    with pytest.raises(RuntimeError, match="No what service"):
        pair.request_pair_token("sess", None, 0, "/pair")
