from bot.providers.stub import SILENT_MP3
from bot.providers.music.base_music import MusicProvider, MusicResult


class StubMusicProvider(MusicProvider):
    async def generate(self, prompt: str) -> MusicResult:
        return MusicResult(audio_bytes=SILENT_MP3)
