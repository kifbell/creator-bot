"""ElevenLabs Music provider — Mode A (vendor-metered).

After generation we query the History endpoint to obtain the exact
units billed. If the music endpoint reports something other than chars,
the calibration loop will surface the discrepancy and the rate table
can be adjusted (or the metering can be ported to input_length).
"""

import asyncio
import contextlib

from elevenlabs.client import ElevenLabs

from bot.providers.music.base_music import MusicProvider, MusicResult
from bot.providers.tts.elevenlabs_tts import _meter_via_history


class ElevenLabsMusicProvider(MusicProvider):
    def __init__(self, api_key: str, semaphore: asyncio.Semaphore | None = None) -> None:
        self._client = ElevenLabs(api_key=api_key)
        self._semaphore = semaphore

    async def generate(self, prompt: str) -> MusicResult:
        def _generate_and_meter():
            audio_gen = self._client.music.compose(
                prompt=prompt,
                music_length_ms=5000,
            )
            audio = b"".join(audio_gen)
            return audio, _meter_via_history(self._client)

        async with self._semaphore or contextlib.nullcontext():
            audio_bytes, (source, units) = await asyncio.to_thread(_generate_and_meter)

        usage = {"mode": "vendor", "units": int(units), "source": source}
        return MusicResult(audio_bytes=audio_bytes, usage=usage)
