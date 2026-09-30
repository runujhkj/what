import pytest

from what.worker_protocol import PROTOCOL_VERSION, WorkerProtocolError, WorkerRequest, encode_pcm, parse_line


def test_worker_request_round_trip():
    request = WorkerRequest("abc", "transcribe", {"pcm_s16le_b64": encode_pcm(b"\x01\x00")})
    message = parse_line(request.line())
    assert message["version"] == PROTOCOL_VERSION
    assert message["id"] == "abc"
    assert message["type"] == "transcribe"


def test_worker_protocol_rejects_wrong_version():
    with pytest.raises(WorkerProtocolError, match="unsupported worker protocol"):
        parse_line(b'{"version": 0}\n')
