from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class TTSVoice:
    voice_id: str
    name: str


@dataclass
class TTSResult:
    audio_bytes: bytes
    mime_type: str = "audio/mpeg"


class TTSProvider(ABC):
    @abstractmethod
    async def list_voices(self) -> list[TTSVoice]:
        """Return available voices for this provider."""
        ...

    @abstractmethod
    async def synthesize(self, text: str, voice_id: str) -> TTSResult:
        """Synthesize text to audio using the given voice."""
        ...

    @abstractmethod
    async def synthesize_described(self, text: str, description: str) -> TTSResult:
        """Synthesize text to audio in a voice matching the free-text description."""
        ...
