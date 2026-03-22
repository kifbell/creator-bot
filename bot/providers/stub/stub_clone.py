from bot.providers.stub import SILENT_MP3
from bot.providers.voice_clone.base_clone import CloneResult, VoiceCloneProvider


class StubVoiceCloneProvider(VoiceCloneProvider):
    async def clone_and_speak(self, sample_path: str, text: str, voice_name: str) -> CloneResult:
        return CloneResult(audio_bytes=SILENT_MP3)
