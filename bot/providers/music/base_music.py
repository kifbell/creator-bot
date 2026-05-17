"""Music provider interface.

The `usage` dict on MusicResult carries provider-reported metering.
ElevenLabs Music is vendor-metered (History endpoint). Tempolor is
input_length-metered (we self-meter on len(prompt) per pricing config).
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class MusicResult:
    audio_bytes: bytes
    mime_type: str = "audio/mpeg"
    usage: dict = field(default_factory=dict)


class MusicProvider(ABC):
    @abstractmethod
    async def generate(self, prompt: str) -> MusicResult:
        """Generate a music clip from a text prompt."""
        ...
