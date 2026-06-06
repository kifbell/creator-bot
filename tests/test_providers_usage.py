"""Tests for the provider `usage` field contract.

Mocks the vendor SDKs so we can validate that each provider populates
`usage` with the right shape under both success and fallback paths.
"""

import os

import pytest

os.environ.setdefault("BOT_ENV", "test")
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "stub")


# ─── Stub providers — usage shape sanity ──────────────────────────────


@pytest.mark.asyncio
async def test_stub_tts_returns_input_length_usage() -> None:
    from bot.providers.stub.stub_tts import StubTTSProvider
    p = StubTTSProvider()
    result = await p.synthesize(text="hello world", voice_id="x")
    assert result.usage == {"mode": "input_length", "units": 11, "source": "input_length"}


@pytest.mark.asyncio
async def test_stub_clone_returns_input_length_usage() -> None:
    from bot.providers.stub.stub_clone import StubVoiceCloneProvider
    p = StubVoiceCloneProvider()
    result = await p.clone_and_speak(sample_path="/x", text="hello", voice_name="v")
    assert result.usage == {"mode": "input_length", "units": 5, "source": "input_length"}


@pytest.mark.asyncio
async def test_stub_music_returns_input_length_usage() -> None:
    from bot.providers.stub.stub_music import StubMusicProvider
    p = StubMusicProvider()
    result = await p.generate(prompt="lo-fi beats")
    assert result.usage == {"mode": "input_length", "units": 11, "source": "input_length"}


# ─── OpenAI — input_length self-metering ──────────────────────────────


@pytest.mark.asyncio
async def test_openai_returns_input_length_chars(monkeypatch) -> None:
    from bot.providers.tts.openai_tts import OpenAITTSProvider

    class FakeStreamingResponse:
        def __init__(self, audio: bytes) -> None:
            self._audio = audio

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def read(self) -> bytes:
            return self._audio

    class FakeSpeech:
        def with_streaming_response_create(self, **kwargs):
            return FakeStreamingResponse(b"\xff\xfb\x00" + b"\x00" * 100)

    class FakeAudio:
        def __init__(self):
            self.speech = FakeSpeechWrapper()

    class FakeSpeechWrapper:
        @property
        def with_streaming_response(self):
            class _Inner:
                @staticmethod
                def create(**kwargs):
                    return FakeStreamingResponse(b"\xff\xfb\x00" + b"\x00" * 100)
            return _Inner()

    class FakeClient:
        def __init__(self, **kwargs):
            self.audio = FakeAudio()

    monkeypatch.setattr("bot.providers.tts.openai_tts.OpenAI", FakeClient)
    p = OpenAITTSProvider(api_key="stub")
    result = await p.synthesize(text="hello", voice_id="coral")
    assert result.usage == {"mode": "input_length", "units": 5, "source": "input_length"}


# ─── ElevenLabs — input_length self-metering ──────────────────────────
# `convert()` returns a byte iterator with no usage payload and no
# request-ID we can correlate to History, so we self-meter on len(text)
# like every other provider. See `bot/providers/tts/elevenlabs_tts.py`.


class _FakeElevenLabsClient:
    """Mocks the small slice of the ElevenLabs SDK we actually use."""

    def __init__(self, **kwargs):
        self.text_to_speech = self._TTSNamespace()
        self.text_to_voice = self._VoiceNamespace()
        self.voices = self._VoicesNamespace()
        self.music = self._MusicNamespace()
        # `clone` is a top-level method on the SDK client.
        self.clone = self._clone

    class _TTSNamespace:
        @staticmethod
        def convert(**kwargs):
            return iter([b"\xff\xfb\x00", b"\x00" * 100])

    class _VoiceNamespace:
        @staticmethod
        def create_previews(**kwargs):
            import base64
            class _Preview:
                audio_base_64 = base64.b64encode(b"\xff\xfb\x00" + b"\x00" * 100).decode()
            class _R:
                previews = [_Preview()]
            return _R()

    class _VoicesNamespace:
        delete_calls: list = []

        def delete(self, voice_id: str) -> None:
            type(self).delete_calls.append(voice_id)

    class _MusicNamespace:
        @staticmethod
        def compose(**kwargs):
            return iter([b"\xff\xfb\x00", b"\x00" * 100])

    @staticmethod
    def _clone(**kwargs):
        class _V:
            voice_id = "clone-voice-1"
        return _V()


@pytest.mark.asyncio
async def test_elevenlabs_tts_returns_input_length(monkeypatch) -> None:
    from bot.providers.tts import elevenlabs_tts

    monkeypatch.setattr(elevenlabs_tts, "ElevenLabs", _FakeElevenLabsClient)
    p = elevenlabs_tts.ElevenLabsTTSProvider(api_key="stub")
    result = await p.synthesize(text="hello world", voice_id="x")
    assert result.usage == {"mode": "input_length", "units": 11, "source": "input_length"}


@pytest.mark.asyncio
async def test_elevenlabs_described_bills_original_len_not_padded(monkeypatch) -> None:
    """Regression: synthesize_described pads short text to 100 chars before
    calling the vendor, but the user must be billed for the chars they
    actually typed."""
    from bot.providers.tts import elevenlabs_tts

    monkeypatch.setattr(elevenlabs_tts, "ElevenLabs", _FakeElevenLabsClient)
    p = elevenlabs_tts.ElevenLabsTTSProvider(api_key="stub")
    result = await p.synthesize_described(text="hi there", description="cheerful")
    assert result.usage == {"mode": "input_length", "units": 8, "source": "input_length"}


@pytest.mark.asyncio
async def test_elevenlabs_clone_returns_input_length(monkeypatch) -> None:
    from bot.providers.voice_clone import elevenlabs_clone

    monkeypatch.setattr(elevenlabs_clone, "ElevenLabs", _FakeElevenLabsClient)
    p = elevenlabs_clone.ElevenLabsCloneProvider(api_key="stub")
    result = await p.clone_and_speak(sample_path="/dev/null", text="hello", voice_name="v")
    assert result.usage == {"mode": "input_length", "units": 5, "source": "input_length"}


@pytest.mark.asyncio
async def test_elevenlabs_clone_deletes_voice_even_on_failure(monkeypatch) -> None:
    """Regression: ephemeral voice slot must be freed even when synthesis
    raises mid-flight."""
    from bot.providers.voice_clone import elevenlabs_clone

    class _RaisingClient(_FakeElevenLabsClient):
        class _TTSNamespace:
            @staticmethod
            def convert(**kwargs):
                raise RuntimeError("synth failed mid-stream")

    # Reset the class-level delete log before this test.
    _FakeElevenLabsClient._VoicesNamespace.delete_calls = []
    monkeypatch.setattr(elevenlabs_clone, "ElevenLabs", _RaisingClient)
    p = elevenlabs_clone.ElevenLabsCloneProvider(api_key="stub")
    with pytest.raises(RuntimeError):
        await p.clone_and_speak(sample_path="/dev/null", text="hello", voice_name="v")
    assert _FakeElevenLabsClient._VoicesNamespace.delete_calls == ["clone-voice-1"]


@pytest.mark.asyncio
async def test_elevenlabs_music_returns_input_length(monkeypatch) -> None:
    from bot.providers.music import elevenlabs_music

    monkeypatch.setattr(elevenlabs_music, "ElevenLabs", _FakeElevenLabsClient)
    p = elevenlabs_music.ElevenLabsMusicProvider(api_key="stub")
    result = await p.generate(prompt="lo-fi beats")
    assert result.usage == {"mode": "input_length", "units": 11, "source": "input_length"}


# ─── Google TTS — input_length self-metering ──────────────────────────


class _FakeGoogleResponse:
    def __init__(self, content: bytes) -> None:
        self.audio_content = content


class _FakeGoogleClient:
    def __init__(self, *args, **kwargs):
        pass

    def synthesize_speech(self, **kwargs):
        return _FakeGoogleResponse(b"\xff\xfb\x00" + b"\x00" * 100)


@pytest.mark.asyncio
async def test_google_tts_returns_input_length(monkeypatch) -> None:
    from bot.providers.tts import google_tts

    monkeypatch.setattr(google_tts.texttospeech, "TextToSpeechClient", _FakeGoogleClient)
    p = google_tts.GoogleTTSProvider()
    result = await p.synthesize(text="hello world", voice_id="en-US-Neural2-F")
    assert result.usage == {"mode": "input_length", "units": 11, "source": "input_length"}


# ─── Azure TTS — input_length self-metering ───────────────────────────


class _FakeAzureResult:
    def __init__(self, audio: bytes, completed: bool) -> None:
        self.audio_data = audio
        # Match the SDK's enum semantics: completed → SynthesizingAudioCompleted.
        import azure.cognitiveservices.speech as speechsdk
        self.reason = (
            speechsdk.ResultReason.SynthesizingAudioCompleted if completed
            else speechsdk.ResultReason.Canceled
        )
        self.cancellation_details = None


class _FakeAzureFuture:
    def __init__(self, result) -> None:
        self._result = result

    def get(self):
        return self._result


class _FakeAzureSynthesizer:
    def __init__(self, **kwargs):
        pass

    def speak_text_async(self, text):
        return _FakeAzureFuture(_FakeAzureResult(b"\xff\xfb\x00" + b"\x00" * 100, completed=True))


@pytest.mark.asyncio
async def test_azure_tts_returns_input_length(monkeypatch) -> None:
    from bot.providers.tts import azure_tts

    monkeypatch.setattr(azure_tts.speechsdk, "SpeechSynthesizer", _FakeAzureSynthesizer)
    p = azure_tts.AzureTTSProvider(api_key="stub", endpoint="https://francecentral.api.cognitive.microsoft.com/")
    result = await p.synthesize(text="hello world", voice_id="en-US-AvaMultilingualNeural")
    assert result.usage == {"mode": "input_length", "units": 11, "source": "input_length"}


def test_azure_region_parsed_from_endpoint() -> None:
    from bot.providers.tts.azure_tts import _region_from_endpoint
    assert _region_from_endpoint("https://francecentral.api.cognitive.microsoft.com/") == "francecentral"
    assert _region_from_endpoint("https://westus2.api.cognitive.microsoft.com/") == "westus2"


# ─── Typecast voice clone — input_length self-metering + cleanup ──────


class _FakeTypecastClient:
    """Async mock that tracks delete_voice calls and can be configured
    to raise from text_to_speech."""

    delete_calls: list = []

    def __init__(self, *args, raise_on_synth: bool = False, **kwargs):
        self.raise_on_synth = raise_on_synth

    async def clone_voice(self, **kwargs):
        class _V:
            voice_id = "uc_test_123"
        return _V()

    async def text_to_speech(self, request):
        if self.raise_on_synth:
            raise RuntimeError("synth failed mid-stream")

        class _R:
            audio_data = b"\xff\xfb\x00" + b"\x00" * 100
        return _R()

    async def delete_voice(self, voice_id: str) -> None:
        type(self).delete_calls.append(voice_id)


@pytest.mark.asyncio
async def test_typecast_clone_returns_input_length(monkeypatch) -> None:
    from bot.providers.voice_clone import typecast_clone

    _FakeTypecastClient.delete_calls = []
    monkeypatch.setattr(typecast_clone, "AsyncTypecast", _FakeTypecastClient)
    p = typecast_clone.TypecastCloneProvider(api_key="stub")
    result = await p.clone_and_speak(sample_path="/dev/null", text="hello", voice_name="v")
    assert result.usage == {"mode": "input_length", "units": 5, "source": "input_length"}
    # Voice slot must have been freed.
    assert _FakeTypecastClient.delete_calls == ["uc_test_123"]


@pytest.mark.asyncio
async def test_typecast_clone_deletes_voice_even_on_failure(monkeypatch) -> None:
    """Regression: voice slot quota must be freed even when synthesis raises."""
    from bot.providers.voice_clone import typecast_clone

    _FakeTypecastClient.delete_calls = []

    def _make_raising_client(*args, **kwargs):
        return _FakeTypecastClient(raise_on_synth=True)

    monkeypatch.setattr(typecast_clone, "AsyncTypecast", _make_raising_client)
    p = typecast_clone.TypecastCloneProvider(api_key="stub")
    with pytest.raises(RuntimeError):
        await p.clone_and_speak(sample_path="/dev/null", text="hello", voice_name="v")
    assert _FakeTypecastClient.delete_calls == ["uc_test_123"]
