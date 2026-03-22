from bot.providers.music.base_music import MusicProvider
from bot.providers.tts.base_tts import TTSProvider
from bot.providers.voice_clone.base_clone import VoiceCloneProvider


class ProviderRegistry:
    def __init__(
        self,
        tts: TTSProvider,
        voice_clone: VoiceCloneProvider,
        music_providers: dict[str, MusicProvider] | None = None,
    ) -> None:
        self._tts = tts
        self._voice_clone = voice_clone
        self._music_providers: dict[str, MusicProvider] = music_providers or {}

    def get_tts(self) -> TTSProvider:
        return self._tts

    def get_voice_clone(self) -> VoiceCloneProvider:
        return self._voice_clone

    def get_music(self, provider: str = "elevenlabs") -> MusicProvider:
        if provider not in self._music_providers:
            raise NotImplementedError(f"Music provider '{provider}' not configured.")
        return self._music_providers[provider]

    def music_providers(self) -> list[str]:
        return list(self._music_providers.keys())
