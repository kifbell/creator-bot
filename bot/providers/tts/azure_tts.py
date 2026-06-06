"""Microsoft Azure Neural TTS provider."""

import asyncio

import azure.cognitiveservices.speech as speechsdk

from bot.providers.tts.base_tts import TTSProvider, TTSResult, TTSVoice
from bot.providers.usage import input_length_usage

_DEFAULT_VOICE = "en-US-AvaMultilingualNeural"


def _region_from_endpoint(endpoint: str) -> str:
    host = endpoint.replace("https://", "").replace("http://", "")
    return host.split(".")[0]


class AzureTTSProvider(TTSProvider):
    def __init__(self, api_key: str, endpoint: str) -> None:
        region = _region_from_endpoint(endpoint)
        self._config = speechsdk.SpeechConfig(subscription=api_key, region=region)
        self._config.set_speech_synthesis_output_format(
            speechsdk.SpeechSynthesisOutputFormat.Audio24Khz48KBitRateMonoMp3
        )

    async def list_voices(self) -> list[TTSVoice]:
        return [TTSVoice(voice_id=_DEFAULT_VOICE, name="Ava Multilingual (Neural)")]

    async def synthesize(self, text: str, voice_id: str) -> TTSResult:
        audio_bytes = await asyncio.to_thread(self._sync_synthesize, text, voice_id)
        return TTSResult(audio_bytes=audio_bytes, usage=input_length_usage(len(text)))

    async def synthesize_described(self, text: str, description: str) -> TTSResult:
        # Azure doesn't support free-text voice description.
        return await self.synthesize(text, _DEFAULT_VOICE)

    def _sync_synthesize(self, text: str, voice_id: str) -> bytes:
        self._config.speech_synthesis_voice_name = voice_id
        synth = speechsdk.SpeechSynthesizer(speech_config=self._config, audio_config=None)
        result = synth.speak_text_async(text).get()
        if result.reason != speechsdk.ResultReason.SynthesizingAudioCompleted:
            cd = getattr(result, "cancellation_details", None)
            raise RuntimeError(f"Azure TTS failed: reason={result.reason} err={cd}")
        return bytes(result.audio_data)
