"""ElevenLabs TTS provider."""

import asyncio
import base64
import contextlib

from elevenlabs.client import ElevenLabs

from bot.providers.tts.base_tts import TTSProvider, TTSResult, TTSVoice
from bot.providers.usage import input_length_usage


class ElevenLabsTTSProvider(TTSProvider):
    def __init__(self, api_key: str, semaphore: asyncio.Semaphore | None = None) -> None:
        self._client = ElevenLabs(api_key=api_key)
        self._semaphore = semaphore

    async def list_voices(self) -> list[TTSVoice]:
        def _fetch():
            response = self._client.voices.get_all()
            return [TTSVoice(voice_id=v.voice_id, name=v.name) for v in response.voices]

        return await asyncio.to_thread(_fetch)

    async def synthesize(self, text: str, voice_id: str) -> TTSResult:
        def _synth():
            return b"".join(self._client.text_to_speech.convert(
                voice_id=voice_id,
                text=text,
                model_id="eleven_multilingual_v2",
            ))

        async with self._semaphore or contextlib.nullcontext():
            audio_bytes = await asyncio.to_thread(_synth)

        return TTSResult(audio_bytes=audio_bytes, usage=input_length_usage(len(text)))

    async def synthesize_described(self, text: str, description: str) -> TTSResult:
        # original_len: bill what the user typed, not the padded vendor text.
        original_len = len(text)
        if len(text) < 100:
            text = text + (" " + text) * ((100 // len(text)) + 1)
            text = text[:100]

        def _synth():
            response = self._client.text_to_voice.create_previews(
                voice_description=description,
                text=text,
            )
            return base64.b64decode(response.previews[0].audio_base_64)

        async with self._semaphore or contextlib.nullcontext():
            audio_bytes = await asyncio.to_thread(_synth)

        return TTSResult(audio_bytes=audio_bytes, usage=input_length_usage(original_len))
