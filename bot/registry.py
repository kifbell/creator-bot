from bot.providers.music.base_music import MusicProvider
from bot.providers.tts.base_tts import TTSProvider
from bot.providers.voice_clone.base_clone import VoiceCloneProvider


class ProviderRegistry:
    def __init__(
        self,
        tts_providers: dict[str, TTSProvider] | None = None,
        clone_providers: dict[str, VoiceCloneProvider] | None = None,
        music_providers: dict[str, MusicProvider] | None = None,
    ) -> None:
        self._tts_providers: dict[str, TTSProvider] = tts_providers or {}
        self._clone_providers: dict[str, VoiceCloneProvider] = clone_providers or {}
        self._music_providers: dict[str, MusicProvider] = music_providers or {}

    def get_tts(self, provider: str = "elevenlabs") -> TTSProvider:
        if provider not in self._tts_providers:
            raise NotImplementedError(f"TTS provider '{provider}' not configured.")
        return self._tts_providers[provider]

    def get_voice_clone(self, provider: str = "elevenlabs") -> VoiceCloneProvider:
        if provider not in self._clone_providers:
            raise NotImplementedError(f"Voice clone provider '{provider}' not configured.")
        return self._clone_providers[provider]

    def get_music(self, provider: str = "elevenlabs") -> MusicProvider:
        if provider not in self._music_providers:
            raise NotImplementedError(f"Music provider '{provider}' not configured.")
        return self._music_providers[provider]

    def tts_providers(self) -> list[str]:
        return list(self._tts_providers.keys())

    def clone_providers(self) -> list[str]:
        return list(self._clone_providers.keys())

    def music_providers(self) -> list[str]:
        return list(self._music_providers.keys())
