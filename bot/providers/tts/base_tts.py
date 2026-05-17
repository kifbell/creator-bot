"""TTS provider interface.

The `usage` dict on TTSResult carries provider-reported metering, used
by `CreditManager.reconcile` to compute the actual cost. Shape:

    {"mode": "vendor",       "units": int, "source": "vendor_history" | "fallback_min"}
    {"mode": "input_length", "units": int, "source": "input_length"}

`source` lets log-grepping distinguish authoritative vendor metering
from fallback paths. `fallback_min` triggers the minimum-billing path
in reconcile (no overage charged, no refund issued).
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class TTSVoice:
    voice_id: str
    name: str


@dataclass
class TTSResult:
    audio_bytes: bytes
    mime_type: str = "audio/mpeg"
    usage: dict = field(default_factory=dict)


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
