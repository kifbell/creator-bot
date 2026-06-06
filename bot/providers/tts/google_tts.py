"""Google Cloud Text-to-Speech provider — input_length self-metering.

SDK reads ``GOOGLE_APPLICATION_CREDENTIALS`` from the environment
automatically; it accepts both service-account JSONs and user OAuth
credentials. The sync SDK is wrapped with ``asyncio.to_thread`` so it
doesn't block the event loop, matching ``tempolor_music.py``.

Google bills per character of input; the response carries audio bytes
only, with no usage payload — so we self-meter on ``len(text)``.
"""

import asyncio

from google.cloud import texttospeech

from bot.providers.tts.base_tts import TTSProvider, TTSResult, TTSVoice
from bot.providers.usage import input_length_usage

_DEFAULT_VOICE = "en-US-Neural2-F"
_LANG = "en-US"


class GoogleTTSProvider(TTSProvider):
    def __init__(self) -> None:
        self._client = texttospeech.TextToSpeechClient()

    async def list_voices(self) -> list[TTSVoice]:
        return [TTSVoice(voice_id=_DEFAULT_VOICE, name="Neural2-F (en-US)")]

    async def synthesize(self, text: str, voice_id: str) -> TTSResult:
        audio_bytes = await asyncio.to_thread(self._sync_synthesize, text, voice_id)
        return TTSResult(audio_bytes=audio_bytes, usage=input_length_usage(len(text)))

    async def synthesize_described(self, text: str, description: str) -> TTSResult:
        # Google doesn't support free-text voice description; use default voice.
        return await self.synthesize(text, _DEFAULT_VOICE)

    def _sync_synthesize(self, text: str, voice_id: str) -> bytes:
        resp = self._client.synthesize_speech(
            input=texttospeech.SynthesisInput(text=text),
            voice=texttospeech.VoiceSelectionParams(language_code=_LANG, name=voice_id),
            audio_config=texttospeech.AudioConfig(
                audio_encoding=texttospeech.AudioEncoding.MP3,
            ),
        )
        return resp.audio_content
