# Architecture — AI Creator Bot
---


## Request Lifecycle

1. **Startup** (`main.py`): reads `BOT_ENV`, instantiates concrete providers (or stubs if `test`), stores them in `ProviderRegistry` → `app.bot_data["registry"]`. Initializes SQLite databases (`credits_{env}.db`, `voices.db`). Registers all `ConversationHandler`s and starts polling.

2. **User taps a button / sends a command**: Telegram delivers the update. `python-telegram-bot` matches it to a `ConversationHandler` entry point (e.g. `/speak` → `speak_start`).

3. **Conversation state machine**: Each handler function returns the next state integer. The handler for that state processes the next user message. States are scoped per command (0–9 speak, 10–19 voiceover, etc.) to avoid collisions. `context.user_data` carries in-flight data (selected voice, description, sample path) between states.

4. **Provider call**: The command handler pulls the provider from the registry (`registry.get_tts()`, `registry.get_voice_clone()`, etc.) and calls it. The command never knows which concrete implementation is behind the interface.

5. **Credit gate**: Before any provider call, `CreditManager.check_and_deduct()` atomically checks the user's balance and deducts the cost. If insufficient, the flow ends with an error message. The check + deduction happen in a single async lock to prevent race conditions.

6. **Response**: The provider returns audio bytes. The handler wraps them in a `BytesIO`, sends them as a Telegram audio message, clears `user_data`, and returns `ConversationHandler.END`.

---

## Provider System

Commands depend on abstract base classes, never concrete implementations. `main.py` is the only file that imports and instantiates concrete providers.

```
TTSProvider (base_tts.py)
  ├── ElevenLabsTTSProvider      ← BOT_ENV=prod
  └── StubTTSProvider            ← BOT_ENV=test

VoiceCloneProvider (base_clone.py)
  ├── ElevenLabsCloneProvider    ← BOT_ENV=prod
  └── StubVoiceCloneProvider     ← BOT_ENV=test

MusicProvider (base_music.py)
  ├── ElevenLabsMusicProvider    ← user-selectable via /settings
  ├── TempolorMusicProvider      ← user-selectable via /settings
  └── StubMusicProvider          ← BOT_ENV=test

PaymentProvider (base_payment.py)
  └── MockPaymentProvider        ← placeholder for real payments
```

To add a new provider: implement the ABC, instantiate it in `main.py`. No command files change.

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
WAITING_SAMPLE (10) → user sends voice message or audio
    └── WAITING_TEXT (11) → clone_and_speak() → MP3
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
