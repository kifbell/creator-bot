from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class MusicResult:
    audio_bytes: bytes
    mime_type: str = "audio/mpeg"


class MusicProvider(ABC):
    @abstractmethod
    async def generate(self, prompt: str) -> MusicResult:
        """Generate a music clip from a text prompt."""
        ...
