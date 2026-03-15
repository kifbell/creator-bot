from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class CloneResult:
    audio_bytes: bytes
    mime_type: str = "audio/mpeg"


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
