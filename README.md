# AI Creator Bot

A Telegram bot (`@genaicreatorbot`) for AI-generated voice and music. Users can synthesize speech in preset or described voices, clone their own voice from an audio sample, and generate music from text prompts — all paid for with an in-bot credit balance.

Built on `python-telegram-bot` with a pluggable provider layer (ElevenLabs, OpenAI, Tempolor) and a SQLite-backed credit ledger with per-provider metering.

---

## Features

| Command       | What it does                                                                                                  |
| ------------- | ------------------------------------------------------------------------------------------------------------- |
| `/speak`      | Text → speech. Pick a preset voice, describe one in words, or reuse a previously saved description.           |
| `/voiceover`  | Clone a voice from a 30–90s audio sample, then speak arbitrary text in that voice. Samples can be saved.      |
| `/song`       | Generate a short music track from a text prompt (e.g. *"upbeat lo-fi hip hop"*). Backed by Tempolor or ElevenLabs. |
| `/settings`   | Pick which provider powers TTS, voiceover, and music for your account.                                        |
| `/topup`      | Buy credits via YooKassa (50₽ / 100₽ / 500₽ presets).                                                         |
| `/credits`    | Check your current balance.                                                                                   |
| `/cancel`     | Cancel any active flow.                                                                                       |

The Telegram UI is a persistent reply keyboard:

```
🎙 Speak     |  🎤 Voiceover  |  🎵 Song
⚙️ Settings  |  ℹ️ Info        |  💳 Credits
             ❌ Cancel
```

Tapping any main-menu button mid-flow silently cancels the current conversation and jumps to the new one.

---

## Requirements

- Python 3.11+
- A [Telegram bot token](https://t.me/BotFather)
- An [ElevenLabs API key](https://elevenlabs.io) (free tier: 10,000 chars/month)
- Optionally: Tempolor, OpenAI, and YooKassa credentials

---

## Quick start

```bash
git clone <repo-url>
cd creator_bot
python3 -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env           # then fill in tokens — see "Environment" below
BOT_ENV=test python -m bot.main   # stub providers, no API calls, no spend
BOT_ENV=prod python -m bot.main   # real ElevenLabs / Tempolor / YooKassa
```

The bot logs `Bot starting…` and begins polling. Open Telegram, find `@genaicreatorbot`, and send `/start`. Stop with `Ctrl+C`.

`test` mode swaps every external provider for a stub that returns a silent MP3 instantly. Conversation flows, menus, persistence, and credit accounting are identical to production — useful for UI work without burning API quota.

---

## Environment

Required in `.env`:

```bash
TELEGRAM_BOT_TOKEN=...      # from @BotFather
BOT_ENV=test                # test | prod

# Real-provider keys (required in prod, ignored in test)
ELEVENLABS_API_KEY=...
TEMPOLOR_API_KEY=...        # optional, music
OPENAI_API_KEY=...          # optional, alternative TTS

# Payments (optional — /topup is hidden if missing)
YOOKASSA_SHOP_ID=...
YOOKASSA_SECRET_KEY=...

# Optional overrides
PRICING_CONFIG_PATH=config/pricing.json
```

`bot/config.py` validates these via `pydantic-settings` at startup and fails fast on a misconfigured env. Keys can also be kept in `tokens/` for reference — that folder is git-ignored.

---

## Architecture (one-screen version)

```
Telegram update
   │
   ▼
ConversationHandler  (bot/commands/{speak,voiceover,song,settings,topup}.py)
   │
   ▼
CreditManager.pre_deduct()      ← atomic minimum charge, frozen rate snapshot
   │
   ▼
ProviderRegistry.get_tts(...)   ← ABC-based provider lookup
   │   (ElevenLabs / OpenAI / Tempolor / Stub)
   ▼
CreditManager.reconcile()       ← settle against real vendor usage; refund overcharge
   │
   ▼
MP3 → user
```

Three properties worth noting:

- **Provider abstraction.** Every external service implements an ABC under `bot/providers/`. Handlers only ever talk to the abstract interface; concrete classes are wired up exactly once in `bot/main.py`. Swapping ElevenLabs for another vendor is a single-file change.
- **Test/prod is just a constructor swap.** `BOT_ENV=test` instantiates `Stub*` classes; nothing in the handler code branches on env.
- **Credits are a two-phase ledger.** A minimum is deducted *before* the API call so concurrent requests can't race a balance. After the provider returns its usage dict, `CreditManager.reconcile()` writes a paired transaction row keyed by `call_id` — overage charges, underage refunds, or full refund on error.

For the full design see [ARCHITECTURE.md](ARCHITECTURE.md). Env modes are documented in [ENV.md](ENV.md). The conversation state machines are diagrammed in [CLAUDE.md](CLAUDE.md).

---

## Persistence

Three SQLite files, all written through `asyncio.Lock`-serialized wrappers around the stdlib `sqlite3` module:

| File                     | Scope          | Contents                                                         |
| ------------------------ | -------------- | ---------------------------------------------------------------- |
| `credits_{env}.db`       | per-environment | User balances, transaction ledger, pending YooKassa payments     |
| `voices.db`              | shared          | Saved voice descriptions (text) and voice-sample metadata        |
| `preferences.db`         | shared          | Each user's chosen TTS / voiceover / music provider              |

Voice sample audio itself lives on disk under `data/voices/{user_id}/`; `voices.db` only stores file paths. Conversation state is snapshotted to disk via `PicklePersistence` so in-progress flows survive a restart.

---

## Pricing

Per-call cost is computed from `config/pricing.json` (or `config/pricing.test.json` in test mode), validated by `bot/credits/pricing_schema.py`. Three metering modes are supported:

- **`vendor`** — provider reports billable units; cost = `ceil(units × multiplier)`.
- **`input_length`** — meter on input characters or seconds.
- **`payment`** — used by YooKassa to convert ₽ → credits.

The `multiplier` (default 2×) covers payment-processor fees and margin.

---

## Project layout

```
bot/
├── main.py                # bootstrap, provider wiring, handler registration
├── config.py              # pydantic settings (.env + validation)
├── registry.py            # ProviderRegistry
├── commands/              # one ConversationHandler per command
│   ├── common.py          # /start, /help, /cancel, shared UI
│   ├── speak.py           # /speak (states 0–9)
│   ├── voiceover.py       # /voiceover (states 10–19)
│   ├── song.py            # /song (states 20–29)
│   ├── settings.py        # /settings (states 30–39)
│   └── topup.py           # /topup (states 40–49)
├── providers/
│   ├── tts/               # ElevenLabs, OpenAI, Stub
│   ├── voice_clone/       # ElevenLabs, Stub
│   ├── music/             # ElevenLabs, Tempolor, Stub
│   └── payment/           # YooKassa
├── credits/
│   ├── manager.py         # pre_deduct / reconcile / refund_minimum
│   └── pricing_schema.py  # config loader
└── db/                    # credits.py, voices.py, preferences.py

config/
├── pricing.json           # prod rates
└── pricing.test.json      # test rates

deploy/
├── creator-bot.service    # systemd unit
└── playbook.yml           # Ansible deploy
```

---

## Adding a new provider

1. Implement the relevant ABC (`TTSProvider`, `VoiceCloneProvider`, `MusicProvider`, or `PaymentProvider`).
2. Register it in `bot/main.py`:
   ```python
   registry = ProviderRegistry(
       tts={"my_new_tts": MyNewTTSProvider(api_key=...)},
       voice_clone={"elevenlabs": ElevenLabsCloneProvider(...)},
       ...
   )
   ```
3. Add a pricing entry for it in `config/pricing.json` so the credit manager knows how to meter it.

Command handlers never import concrete providers, so no other files need to change.

---

## Deployment

Production runs as a `systemd` service (`Restart=always`, `SIGTERM` with a 30s grace period). Updates are pushed by an idempotent Ansible playbook:

```bash
ansible-playbook -i deploy/inventory.ini deploy/playbook.yml
```

The bot uses Telegram long-polling, so no HTTPS/webhook setup is required. Only one process can poll a given token at a time — when developing locally against a prod token, stop the service first:

```bash
ssh prod 'sudo systemctl stop creator-bot'
```

See [SYSTEMD.md](SYSTEMD.md) and [REPRODUCTION_GUIDE.md](REPRODUCTION_GUIDE.md) for full details.

---

## Logging

Logs go to `bot.log` via a `RotatingFileHandler` (5 MB × 3 backups). Structured event lines (`user_created`, `credit_deducted`, `payment_recorded`, `pricing_*`) make it easy to grep for a single user's full request history.

---

## Key dependencies

- [`python-telegram-bot`](https://github.com/python-telegram-bot/python-telegram-bot) 21.10 — bot framework & `ConversationHandler`
- [`elevenlabs`](https://github.com/elevenlabs/elevenlabs-python) 1.50.5 — TTS, voice cloning, music
- [`openai`](https://github.com/openai/openai-python) ≥ 1.60 — alternative TTS
- [`yookassa`](https://github.com/yoomoney/yookassa-sdk-python) ≥ 3.10 — payments
- [`pydantic-settings`](https://docs.pydantic.dev/latest/concepts/pydantic_settings/) 2.8.1 — typed env loading

---

## See also

- [`ARCHITECTURE.md`](ARCHITECTURE.md) — full request lifecycle and provider system
- [`ENV.md`](ENV.md) — test vs prod modes in depth
- [`CLAUDE.md`](CLAUDE.md) — UI blueprint and conversation state diagrams
