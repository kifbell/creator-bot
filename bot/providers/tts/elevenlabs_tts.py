import asyncio
import base64

from elevenlabs.client import ElevenLabs

from bot.providers.tts.base_tts import TTSProvider, TTSResult, TTSVoice


class ElevenLabsTTSProvider(TTSProvider):
    def __init__(self, api_key: str) -> None:
        self._client = ElevenLabs(api_key=api_key)

    async def list_voices(self) -> list[TTSVoice]:
        def _fetch():
            response = self._client.voices.get_all()
            return [TTSVoice(voice_id=v.voice_id, name=v.name) for v in response.voices]

        return await asyncio.to_thread(_fetch)

    async def synthesize(self, text: str, voice_id: str) -> TTSResult:
        def _synth():
            audio_gen = self._client.text_to_speech.convert(
                voice_id=voice_id,
                text=text,
                model_id="eleven_multilingual_v2",
            )
            return b"".join(audio_gen)

        audio_bytes = await asyncio.to_thread(_synth)
        return TTSResult(audio_bytes=audio_bytes)

    async def synthesize_described(self, text: str, description: str) -> TTSResult:
        # ElevenLabs requires text to be 100–1000 chars for create_previews
        if len(text) < 100:
            text = text + (" " + text) * ((100 // len(text)) + 1)
            text = text[:100]

        def _synth():
            response = self._client.text_to_voice.create_previews(
                voice_description=description,
                text=text,
            )
            return base64.b64decode(response.previews[0].audio_base_64)

        audio_bytes = await asyncio.to_thread(_synth)
        return TTSResult(audio_bytes=audio_bytes)
