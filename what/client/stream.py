import asyncio
from typing import AsyncGenerator
import subprocess


async def audio_generator(proc: subprocess.Popen, chunk_size: int = 4096) -> AsyncGenerator[bytes, None]:
    assert proc.stdout is not None
    while True:
        data = await asyncio.to_thread(proc.stdout.read, chunk_size)
        if not data:
            break
        yield data
