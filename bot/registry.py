from bot.providers.tts.base_tts import TTSProvider
from bot.providers.voice_clone.base_clone import VoiceCloneProvider
from bot.providers.music.base_music import MusicProvider


class ProviderRegistry:
    def __init__(
        self,
        tts: TTSProvider,
        voice_clone: VoiceCloneProvider,
        music: MusicProvider | None = None,
    ) -> None:
        self._tts = tts
        self._voice_clone = voice_clone
        self._music = music

    def get_tts(self) -> TTSProvider:
        return self._tts

    def get_voice_clone(self) -> VoiceCloneProvider:
        return self._voice_clone

    def get_music(self) -> MusicProvider:
        if self._music is None:
            raise NotImplementedError("No music provider configured.")
        return self._music
