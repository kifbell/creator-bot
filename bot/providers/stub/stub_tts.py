from bot.providers.stub import SILENT_MP3
from bot.providers.tts.base_tts import TTSProvider, TTSResult, TTSVoice

_STUB_VOICE = TTSVoice(voice_id="stub-voice-1", name="Stub Voice")


class StubTTSProvider(TTSProvider):
    async def list_voices(self) -> list[TTSVoice]:
        return [_STUB_VOICE]

    async def synthesize(self, text: str, voice_id: str) -> TTSResult:
        return TTSResult(audio_bytes=SILENT_MP3)

    async def synthesize_described(self, text: str, description: str) -> TTSResult:
        return TTSResult(audio_bytes=SILENT_MP3)
