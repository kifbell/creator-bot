# CLAUDE.md — AI Creator Bot

## Quick Start

```bash
source .venv/bin/activate
BOT_ENV=test python -m bot.main    # stub providers, no API calls
BOT_ENV=prod python -m bot.main    # real ElevenLabs / Tempolor APIs
```

---

## User Interface Blueprint

Telegram reply-keyboard layout (persistent bottom bar):

```
┌──────────────┬──────────────┬──────────────┐
│  🎙 Speak    │ 🎤 Voiceover │  🎵 Song     │   ← row 0: core features
├──────────────┼──────────────┼──────────────┤
│ ⚙️ Settings  │  ℹ️ Info     │ 💳 Credits   │   ← row 1: utilities
├──────────────┴──────────────┴──────────────┤
│              ❌ Cancel                      │   ← row 2: always available
└─────────────────────────────────────────────┘
```

### Conversation Flows

Each command is a `ConversationHandler` with a reserved state-integer range.

**`/speak` (states 0–9)**
```
speak_start → CHOOSING_VOICE (0)
  ├─ preset voice     → TYPING_TEXT (1) → synthesize → MP3
  ├─ "Describe"       → TYPING_DESCRIPTION (2) → TYPING_DESCRIBED_TEXT (3)
  │     ├─ (saved)    → MP3 → END
  │     └─ (new)      → MP3 → SAVE_DESCRIBED_VOICE (4)
  │           ├─ No   → END
  │           └─ Yes  → NAME_DESCRIBED_VOICE (5) → save → END
  └─ "My saved voices" → CHOOSING_SAVED_DESCRIPTION (6)
        ├─ Back       → speak_start
        └─ pick       → TYPING_DESCRIBED_TEXT (3) → MP3 → END
```

**`/voiceover` (states 10–19)**
```
voiceover_start
  ├─ (has saved) → CHOOSING_SAVED_SAMPLE (14)
  │     ├─ "Record new" → WAITING_SAMPLE (10)
  │     └─ pick         → WAITING_TEXT (11) → clone → MP3 → END
  └─ (no saved)  → WAITING_SAMPLE (10) → WAITING_TEXT (11)
        → clone → MP3 → SAVE_VOICE_SAMPLE (12)
              ├─ No  → delete file → END
              └─ Yes → NAME_VOICE_SAMPLE (13) → save → END
```

**`/song` (states 20–29)**
```
TYPING_PROMPT (20) → generate → MP3 → END
```

**`/settings` (states 30–39)**
```
CHOOSING_FUNCTION (30) → CHOOSING_PROVIDER (31) → save → END
```

**`/topup` (states 40–49)**
```
CHOOSING_AMOUNT (40) → CONFIRMING (41) → payment → END
```

---

## Architecture Blueprint

See [ARCHITECTURE.md](ARCHITECTURE.md) for the request lifecycle and provider system.

### Persistence

- **Credits** (`db/credits.py`): `credits_{env}.db` — separate DB per environment. Tracks user balances and transaction history.
- **Voices** (`db/voices.py`): `voices.db` — shared across environments. Stores saved voice descriptions (text) and voice sample references (file paths to `data/voices/{user_id}/`).
- Both use `asyncio.Lock` to serialize writes. All DB operations are async wrappers around synchronous `sqlite3` calls.

### Menu System

Buttons are defined once in `buttons.py` as `MenuButton` objects with a label, row, and fallback action. `common.py` derives three things automatically:
- `MAIN_MENU` — the `ReplyKeyboardMarkup` sent with most replies
- `USER_TEXT` — a filter that matches free text but excludes button labels and commands
- `menu_fallbacks()` — handlers that end the current conversation when a menu button is tapped mid-flow

---

## References

- [ARCHITECTURE.md](ARCHITECTURE.md) — detailed architecture docs and provider hierarchy
- [ENV.md](ENV.md) — environment modes (test vs prod)
- [README.md](README.md) — setup instructions, requirements, project overview
