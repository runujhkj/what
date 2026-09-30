import struct

from what.service.recording import recording_duration_sec, tee_frames_to_wav


def test_live_recording_publishes_wav_length_before_stream_closes(tmp_path):
    """Review playback can slice an active recording with ffmpeg."""
    wav = tmp_path / "live.wav"
    frames = iter([b"\x01\x00" * 16000])
    stream = tee_frames_to_wav(frames, str(wav), sample_rate=16000, channels=1)
    assert next(stream) == b"\x01\x00" * 16000
    with open(wav, "rb") as fh:
        header = fh.read(44)
    assert struct.unpack_from("<I", header, 40)[0] == 32000
    stream.close()


def test_open_recording_duration_uses_data_bytes_not_stale_header(tmp_path):
    wav = tmp_path / "reconnecting.wav"
    wav.write_bytes(b"\0" * (44 + 64000))
    assert recording_duration_sec(str(wav), sample_rate=16000, channels=1) == 2.0
