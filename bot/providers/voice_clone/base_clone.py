"""Voice-clone provider interface.

The `usage` dict on CloneResult carries provider-reported metering.
ElevenLabs IVC is vendor-metered (we query the History endpoint after
synthesis to obtain the actual character count billed).
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class CloneResult:
    audio_bytes: bytes
    mime_type: str = "audio/mpeg"
    usage: dict = field(default_factory=dict)


class VoiceCloneProvider(ABC):
    @abstractmethod
    async def clone_and_speak(
        self,
        sample_path: str,
        text: str,
        voice_name: str,
    ) -> CloneResult:
        """Clone a voice from sample_path and synthesize text in that voice.

        Implementations must clean up any remote resources (e.g. uploaded voice)
        before returning, even on failure.
        """
        ...
