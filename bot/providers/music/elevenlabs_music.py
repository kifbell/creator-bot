import asyncio
import contextlib

from elevenlabs.client import ElevenLabs

from bot.providers.music.base_music import MusicProvider, MusicResult


class ElevenLabsMusicProvider(MusicProvider):
    def __init__(self, api_key: str, semaphore: asyncio.Semaphore | None = None) -> None:
        self._client = ElevenLabs(api_key=api_key)
        self._semaphore = semaphore

    async def generate(self, prompt: str) -> MusicResult:
        def _generate():
            audio_gen = self._client.music.compose(
                prompt=prompt,
                music_length_ms=5000,
            )
            return b"".join(audio_gen)

        async with self._semaphore or contextlib.nullcontext():
            audio_bytes = await asyncio.to_thread(_generate)
        return MusicResult(audio_bytes=audio_bytes)
