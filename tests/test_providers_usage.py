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


# ─── ElevenLabs TTS — vendor metering with fallback ───────────────────


class _FakeHistoryItem:
    def __init__(self, from_count: int, to_count: int) -> None:
        self.character_count_change_from = from_count
        self.character_count_change_to = to_count


class _FakeHistoryResponse:
    def __init__(self, items) -> None:
        self.history = items


class _FakeElevenLabsClient:
    """Configurable fake: pass history_response or history_exception."""

    def __init__(self, *, history_response=None, history_exception=None, **kwargs):
        self._history_response = history_response
        self._history_exception = history_exception
        self.text_to_speech = self._TTSNamespace()
        self.history = self._HistoryNamespace(self)
        self.text_to_voice = self._VoiceNamespace()

    class _TTSNamespace:
        @staticmethod
        def convert(**kwargs):
            return iter([b"\xff\xfb\x00", b"\x00" * 100])

    class _HistoryNamespace:
        def __init__(self, parent: "_FakeElevenLabsClient") -> None:
            self._parent = parent

        def get_all(self, page_size: int = 1):
            if self._parent._history_exception is not None:
                raise self._parent._history_exception
            return self._parent._history_response

    class _VoiceNamespace:
        @staticmethod
        def create_previews(**kwargs):
            class _R:
                previews = []
            return _R()


@pytest.mark.asyncio
async def test_elevenlabs_history_populates_vendor_units(monkeypatch) -> None:
    from bot.providers.tts import elevenlabs_tts

    hist = _FakeHistoryResponse([_FakeHistoryItem(from_count=100, to_count=150)])
    monkeypatch.setattr(
        elevenlabs_tts, "ElevenLabs",
        lambda **kwargs: _FakeElevenLabsClient(history_response=hist),
    )
    p = elevenlabs_tts.ElevenLabsTTSProvider(api_key="stub")
    result = await p.synthesize(text="hi", voice_id="x")
    # vendor billed 150-100 = 50 chars
    assert result.usage == {"mode": "vendor", "units": 50, "source": "vendor_history"}


@pytest.mark.asyncio
async def test_elevenlabs_history_failure_falls_back(monkeypatch) -> None:
    from bot.providers.tts import elevenlabs_tts

    monkeypatch.setattr(
        elevenlabs_tts, "ElevenLabs",
        lambda **kwargs: _FakeElevenLabsClient(history_exception=RuntimeError("api down")),
    )
    p = elevenlabs_tts.ElevenLabsTTSProvider(api_key="stub")
    result = await p.synthesize(text="hi", voice_id="x")
    assert result.usage["mode"] == "vendor"
    assert result.usage["source"] == "fallback_min"


@pytest.mark.asyncio
async def test_elevenlabs_history_empty_falls_back(monkeypatch) -> None:
    from bot.providers.tts import elevenlabs_tts

    empty_hist = _FakeHistoryResponse([])
    monkeypatch.setattr(
        elevenlabs_tts, "ElevenLabs",
        lambda **kwargs: _FakeElevenLabsClient(history_response=empty_hist),
    )
    p = elevenlabs_tts.ElevenLabsTTSProvider(api_key="stub")
    result = await p.synthesize(text="hi", voice_id="x")
    assert result.usage["source"] == "fallback_min"
