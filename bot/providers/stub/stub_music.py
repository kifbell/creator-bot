from bot.providers.music.base_music import MusicProvider, MusicResult
from bot.providers.stub import SILENT_MP3
from bot.providers.usage import input_length_usage


class StubMusicProvider(MusicProvider):
    async def generate(self, prompt: str) -> MusicResult:
        return MusicResult(audio_bytes=SILENT_MP3, usage=input_length_usage(len(prompt)))
