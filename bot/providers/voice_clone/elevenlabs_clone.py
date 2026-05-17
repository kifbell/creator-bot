"""ElevenLabs Instant Voice Clone provider — Mode A (vendor-metered).

After synthesis we query the History endpoint to obtain the exact char
count billed. Ephemeral voice cleanup happens regardless of metering.
"""

import asyncio
import contextlib

from elevenlabs.client import ElevenLabs

from bot.providers.tts.elevenlabs_tts import _meter_via_history
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
            # IVC: upload sample and create ephemeral voice
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
                audio_bytes = b"".join(audio_gen)
                meter = _meter_via_history(self._client)
            finally:
                # Always clean up — free accounts have a voice slot limit
                self._client.voices.delete(voice_id=voice_id)
            return audio_bytes, meter

        async with self._semaphore or contextlib.nullcontext():
            audio_bytes, (source, units) = await asyncio.to_thread(_run)

        usage = {"mode": "vendor", "units": int(units), "source": source}
        return CloneResult(audio_bytes=audio_bytes, usage=usage)
