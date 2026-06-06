"""Typecast voice-cloning provider — input_length self-metering.

Uses ``AsyncTypecast`` so calls don't need ``asyncio.to_thread``. The
flow mirrors ``elevenlabs_clone.py``: clone an ephemeral voice from the
user's WAV, synthesize, then delete the voice in a ``try/finally`` to
free the per-account slot quota (matters most on free/lower tiers).

Typecast bills per call; the SDK response carries audio bytes only, no
usage payload — we self-meter on ``len(text)``.
"""

import asyncio
import contextlib
import logging

from typecast import AsyncTypecast, TTSRequest
from typecast.models import Output, TTSModel

from bot.providers.usage import input_length_usage
from bot.providers.voice_clone.base_clone import CloneResult, VoiceCloneProvider

_logger = logging.getLogger(__name__)

_MODEL = TTSModel.SSFM_V30
_OUTPUT = Output(audio_format="mp3")


class TypecastCloneProvider(VoiceCloneProvider):
    def __init__(self, api_key: str, semaphore: asyncio.Semaphore | None = None) -> None:
        self._client = AsyncTypecast(api_key=api_key)
        self._semaphore = semaphore

    async def clone_and_speak(
        self,
        sample_path: str,
        text: str,
        voice_name: str,
    ) -> CloneResult:
        # Typecast voice name must be 1-30 chars.
        name = (voice_name or "creator_bot_clone")[:30] or "creator_bot_clone"

        async with self._semaphore or contextlib.nullcontext():
            voice = await self._client.clone_voice(
                audio=sample_path,
                name=name,
                model=_MODEL,
            )
            voice_id = voice.voice_id
            try:
                resp = await self._client.text_to_speech(
                    TTSRequest(
                        voice_id=voice_id,
                        text=text,
                        model=_MODEL,
                        output=_OUTPUT,
                    )
                )
                audio_bytes = resp.audio_data
            finally:
                try:
                    await self._client.delete_voice(voice_id)
                except Exception as e:  # noqa: BLE001 — best-effort cleanup
                    _logger.warning("typecast_voice_delete_failed voice_id=%s err=%r", voice_id, e)

        return CloneResult(audio_bytes=audio_bytes, usage=input_length_usage(len(text)))
