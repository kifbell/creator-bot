"""ElevenLabs TTS provider — Mode A (vendor-metered).

After every synthesis we query the History endpoint inside the same
worker thread to obtain the exact char count ElevenLabs billed us for.
If the history fetch fails or returns nothing, we tag `source=fallback_min`
and CreditManager.reconcile bills the configured minimum (no overage,
no refund).
"""

import asyncio
import base64
import contextlib
import logging
import time

from elevenlabs.client import ElevenLabs

from bot.providers.tts.base_tts import TTSProvider, TTSResult, TTSVoice

_logger = logging.getLogger(__name__)


def _extract_vendor_chars(history_response) -> int | None:
    """Read the most recent History entry's billed character count.

    Returns None if the response is empty, the entry is malformed, or
    the relevant fields are missing — caller treats that as fallback_min.
    """
    try:
        item = history_response.history[0]
        return int(item.character_count_change_to) - int(item.character_count_change_from)
    except (AttributeError, IndexError, TypeError, ValueError):
        return None


def _meter_via_history(client) -> tuple[str, int]:
    """Query the ElevenLabs History endpoint for the billed char count of
    the most recent call on this API key. Returns ``(source, units)``.

    On success: ``("vendor_history", <chars>)`` plus a `pricing_vendor_query_ok`
    INFO log line with latency.
    On any failure (empty response, malformed entry, exception):
    ``("fallback_min", 0)`` plus a `pricing_vendor_query_failed` WARNING line.

    This helper is the single point where the History endpoint is consumed —
    shared across `synthesize`, `synthesize_described`, `clone_and_speak`,
    and `music.generate`. Tuning it (e.g. switching to text-match filtering
    to avoid the cross-user race) only needs to happen here.
    """
    t0 = time.perf_counter()
    try:
        hist = client.history.get_all(page_size=1)
        latency_ms = int((time.perf_counter() - t0) * 1000)
        chars = _extract_vendor_chars(hist)
        if chars is None or chars <= 0:
            return ("fallback_min", 0)
        _logger.info(
            "pricing_vendor_query_ok provider=elevenlabs vendor_units=%d latency_ms=%d",
            chars, latency_ms,
        )
        return ("vendor_history", chars)
    except Exception as e:
        latency_ms = int((time.perf_counter() - t0) * 1000)
        _logger.warning("elevenlabs_history_failed err=%r", e)
        _logger.warning(
            "pricing_vendor_query_failed provider=elevenlabs err=%r latency_ms=%d",
            e, latency_ms,
        )
        return ("fallback_min", 0)


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
        def _synth_and_meter():
            audio = b"".join(self._client.text_to_speech.convert(
                voice_id=voice_id,
                text=text,
                model_id="eleven_multilingual_v2",
            ))
            return audio, _meter_via_history(self._client)

        async with self._semaphore or contextlib.nullcontext():
            audio_bytes, (source, units) = await asyncio.to_thread(_synth_and_meter)

        usage = {"mode": "vendor", "units": int(units), "source": source}
        return TTSResult(audio_bytes=audio_bytes, usage=usage)

    async def synthesize_described(self, text: str, description: str) -> TTSResult:
        # ElevenLabs requires text to be 100–1000 chars for create_previews
        if len(text) < 100:
            text = text + (" " + text) * ((100 // len(text)) + 1)
            text = text[:100]

        def _synth_and_meter():
            response = self._client.text_to_voice.create_previews(
                voice_description=description,
                text=text,
            )
            audio = base64.b64decode(response.previews[0].audio_base_64)
            return audio, _meter_via_history(self._client)

        async with self._semaphore or contextlib.nullcontext():
            audio_bytes, (source, units) = await asyncio.to_thread(_synth_and_meter)

        usage = {"mode": "vendor", "units": int(units), "source": source}
        return TTSResult(audio_bytes=audio_bytes, usage=usage)
