"""ElevenLabs Instant Voice Clone provider — input_length self-metering.

ElevenLabs's clone+synthesize flow uses ``text_to_speech.convert`` which
returns a byte iterator without per-request billing. We self-meter on
``len(text)``; calibration drift is absorbed by the ``multiplier`` knob.

Ephemeral voice cleanup happens regardless of synthesis outcome.
"""

import asyncio
import contextlib

from elevenlabs.client import ElevenLabs

from bot.providers.usage import input_length_usage
from bot.providers.voice_clone.base_clone import CloneResult, VoiceCloneProvider


class ElevenLabsCloneProvider(VoiceCloneProvider):
    def __init__(self, api_key: str, semaphore: asyncio.Semaphore | None = None) -> None:
        self._client = ElevenLabs(api_key=api_key)
        self._semaphore = semaphore

    async def clone_and_speak(
        self,
        sample_path: str,
        text: str,
        voice_name: str,
    ) -> CloneResult:
        def _run():
            voice = self._client.clone(
                name=voice_name,
                description="Ephemeral IVC voice — will be deleted after synthesis.",
                files=[sample_path],
            )
            voice_id = voice.voice_id
            try:
                audio_gen = self._client.text_to_speech.convert(
                    voice_id=voice_id,
                    text=text,
                    model_id="eleven_multilingual_v2",
                )
                return b"".join(audio_gen)
            finally:
                self._client.voices.delete(voice_id=voice_id)

        async with self._semaphore or contextlib.nullcontext():
            audio_bytes = await asyncio.to_thread(_run)

        return CloneResult(audio_bytes=audio_bytes, usage=input_length_usage(len(text)))
