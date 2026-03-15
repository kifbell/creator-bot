import asyncio

from elevenlabs.client import ElevenLabs

from bot.providers.music.base_music import MusicProvider, MusicResult


class ElevenLabsMusicProvider(MusicProvider):
    def __init__(self, api_key: str) -> None:
        self._client = ElevenLabs(api_key=api_key)

    async def generate(self, prompt: str) -> MusicResult:
        def _generate():
            audio_gen = self._client.music.compose(
                prompt=prompt,
                music_length_ms=5000,
            )
            return b"".join(audio_gen)

        audio_bytes = await asyncio.to_thread(_generate)
        return MusicResult(audio_bytes=audio_bytes)
