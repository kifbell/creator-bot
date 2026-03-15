import asyncio

from elevenlabs.client import ElevenLabs

from bot.providers.voice_clone.base_clone import CloneResult, VoiceCloneProvider


class ElevenLabsCloneProvider(VoiceCloneProvider):
    def __init__(self, api_key: str) -> None:
        self._client = ElevenLabs(api_key=api_key)

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
            finally:
                # Always clean up — free accounts have a voice slot limit
                self._client.voices.delete(voice_id=voice_id)
            return audio_bytes

        audio_bytes = await asyncio.to_thread(_run)
        return CloneResult(audio_bytes=audio_bytes)
