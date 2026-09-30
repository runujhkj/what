import queue
import threading
from typing import Generator

BYTES_PER_SAMPLE = 2


def pcm_frames_from_queue(
    data_queue: queue.Queue[bytes],
    frame_samples: int,
    stop_event: threading.Event | None = None,
) -> Generator[bytes, None, None]:
    frame_bytes = frame_samples * BYTES_PER_SAMPLE
    buffer = bytearray()

    while True:
        if stop_event is not None and stop_event.is_set():
            break

        try:
            chunk = data_queue.get(timeout=0.1)
        except queue.Empty:
            continue

        if chunk == b"":
            break
        buffer.extend(chunk)
        while len(buffer) >= frame_bytes:
            yield bytes(buffer[:frame_bytes])
            del buffer[:frame_bytes]
