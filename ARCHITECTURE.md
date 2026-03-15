# Architecture — AI Creator Bot

## Overview

A Telegram bot that exposes ElevenLabs AI audio generation features through a conversational interface. Built with `python-telegram-bot` and a provider pattern that keeps API integrations swappable.

---

## Directory Structure

```
creator_bot/
├── bot/
│   ├── main.py               # Entry point — wires providers, registers handlers, starts polling
│   ├── config.py             # Pydantic settings — reads TELEGRAM_BOT_TOKEN, ELEVENLABS_API_KEY from .env
│   ├── registry.py           # ProviderRegistry — injects providers into bot_data at startup
│   ├── commands/
│   │   ├── common.py         # MAIN_MENU keyboard, /start, /help, /cancel, ℹ️ Info
│   │   ├── speak.py          # /speak — TTS with preset or described voice
│   │   ├── voiceover.py      # /voiceover — voice clone from sample
│   │   └── song.py           # /song — music generation from text prompt
│   ├── providers/
│   │   ├── tts/
│   │   │   ├── base_tts.py           # Abstract: list_voices, synthesize, synthesize_described
│   │   │   └── elevenlabs_tts.py     # ElevenLabs implementation
│   │   ├── voice_clone/
│   │   │   ├── base_clone.py         # Abstract: clone_and_speak
│   │   │   └── elevenlabs_clone.py   # ElevenLabs IVC implementation
│   │   └── music/
│   │       ├── base_music.py         # Abstract: generate
│   │       └── elevenlabs_music.py   # ElevenLabs music.compose implementation
│   └── utils/
│       └── audio.py          # Shared audio helpers
├── requirements.txt
├── .env                      # Secret keys (not committed)
└── .gitignore
```

---

## Provider Pattern

All API integrations implement an abstract base class. The concrete provider is instantiated once in `main.py` and stored in `app.bot_data["registry"]`. Commands retrieve the provider via `registry.get_tts()` / `registry.get_voice_clone()` / `registry.get_music()` — they never import ElevenLabs directly.

```
TTSProvider (base_tts.py)
    └── ElevenLabsTTSProvider

VoiceCloneProvider (base_clone.py)
    └── ElevenLabsCloneProvider

MusicProvider (base_music.py)
    └── ElevenLabsMusicProvider
```

To swap a provider (e.g. replace ElevenLabs TTS with another service), only `main.py` needs to change.

---

## Conversation Flows

Each command is a `ConversationHandler` with a reserved state integer range to avoid collisions.

### /speak (states 0–9)
```
CHOOSING_VOICE (0)
  ├── tap preset voice → TYPING_TEXT (1) → synthesize() → MP3
  └── tap "✏️ Describe a voice" → TYPING_DESCRIPTION (2)
            └── type description → TYPING_DESCRIBED_TEXT (3) → synthesize_described() → MP3
```
Voice selection uses a `ReplyKeyboardMarkup` (bottom bar buttons). Each voice name maps back to a `voice_id` via the cached voice list.

### /voiceover (states 10–19)
```
UPLOADING_SAMPLE (10) → user sends voice message or audio
    └── TYPING_VOICEOVER_TEXT (11) → clone_and_speak() → MP3
```

### /song (states 20–29)
```
TYPING_PROMPT (20) → music.compose() → MP3 (5 seconds)
```

---

## State Management

- **`context.bot_data`** — shared across all users; used for the voices cache (`elevenlabs_voices`)
- **`context.user_data`** — per-user; stores in-progress conversation state (selected voice, description, sample path)
- Both are cleared on `ConversationHandler.END` or `/cancel`

---

## Configuration

Settings are loaded from `.env` via `pydantic-settings`:

| Variable | Purpose |
|---|---|
| `TELEGRAM_BOT_TOKEN` | Telegram Bot API token |
| `ELEVENLABS_API_KEY` | ElevenLabs API key |

---

## Current Provider: ElevenLabs

| Feature | SDK method |
|---|---|
| List voices | `client.voices.get_all()` |
| TTS (preset voice) | `client.text_to_speech.convert()` |
| TTS (described voice) | `client.text_to_voice.create_previews()` |
| Voice clone | `client.voices.ivc.create()` + `client.text_to_speech.convert()` |
| Music generation | `client.music.compose()` |
