import asyncio

from openai import OpenAI

from bot.providers.tts.base_tts import TTSProvider, TTSResult, TTSVoice

_VOICES = ["alloy", "ash", "ballad", "coral", "echo", "fable", "nova", "onyx", "sage", "shimmer"]
_DEFAULT_VOICE = "coral"
_MODEL = "gpt-4o-mini-tts"


class OpenAITTSProvider(TTSProvider):
    def __init__(self, api_key: str) -> None:
        self._client = OpenAI(api_key=api_key)

    async def list_voices(self) -> list[TTSVoice]:
        return [TTSVoice(voice_id=v, name=v.capitalize()) for v in _VOICES]

    async def synthesize(self, text: str, voice_id: str) -> TTSResult:
        def _synth():
            with self._client.audio.speech.with_streaming_response.create(
                model=_MODEL,
                voice=voice_id,
                input=text,
            ) as response:
                return response.read()

        audio_bytes = await asyncio.to_thread(_synth)
        return TTSResult(audio_bytes=audio_bytes)

    async def synthesize_described(self, text: str, description: str) -> TTSResult:
        def _synth():
            with self._client.audio.speech.with_streaming_response.create(
                model=_MODEL,
                voice=_DEFAULT_VOICE,
                input=text,
                instructions=description,
            ) as response:
                return response.read()

        audio_bytes = await asyncio.to_thread(_synth)
        return TTSResult(audio_bytes=audio_bytes)
