# AI Creator Bot

A Telegram bot (`@genaicreatorbot`) with AI audio features powered by ElevenLabs.

| Command | What it does |
|---|---|
| `/speak` | Text-to-speech with preset ElevenLabs voices |
| `/voiceover` | Clone a voice from an audio sample, then speak new text |
| `/song` | Song generation *(coming soon)* |
| `/cancel` | Cancel any active flow |

---

## Requirements

- Python 3.11+
- A [Telegram bot token](https://t.me/BotFather)
- An [ElevenLabs API key](https://elevenlabs.io) (free tier: 10,000 chars/month)

---

## Setup

### 1. Clone and create a virtual environment

```bash
git clone <repo-url>
cd creator_bot
python3 -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Configure credentials

Create a `.env` file in the project root:

```
TELEGRAM_BOT_TOKEN=<your telegram bot token>
ELEVENLABS_API_KEY=<your elevenlabs api key>
```

> Keys can also be kept in `tokens/elevenlabs.txt` and `token.txt` for reference — that folder is git-ignored.

---

## How to Run

```bash
source .venv/bin/activate
python -m bot.main
```

The bot will log `Bot starting…` and begin polling. Open Telegram, find `@genaicreatorbot`, and send `/start`.

To stop the bot, press `Ctrl+C`.

---

## Project Structure

```
creator_bot/
├── .env                              # Credentials (git-ignored)
├── requirements.txt
├── tokens/                           # Optional plaintext key storage (git-ignored)
│   └── elevenlabs.txt
└── bot/
    ├── main.py                       # Entry point
    ├── config.py                     # Typed .env loading (pydantic-settings)
    ├── registry.py                   # ProviderRegistry — injects providers into handlers
    ├── commands/
    │   ├── common.py                 # /start, /help, /cancel
    │   ├── speak.py                  # /speak ConversationHandler
    │   ├── voiceover.py              # /voiceover ConversationHandler
    │   └── song.py                   # /song stub
    ├── providers/
    │   ├── tts/
    │   │   ├── base_tts.py           # TTSProvider ABC
    │   │   └── elevenlabs_tts.py     # ElevenLabs implementation
    │   ├── voice_clone/
    │   │   ├── base_clone.py         # VoiceCloneProvider ABC
    │   │   └── elevenlabs_clone.py   # ElevenLabs IVC implementation
    │   └── music/
    │       └── base_music.py         # MusicProvider ABC (stub)
    └── utils/
        └── audio.py                  # Telegram file download helpers
```

---

## Adding a New Provider

1. Implement the relevant ABC (`TTSProvider`, `VoiceCloneProvider`, or `MusicProvider`)
2. Register it in `bot/main.py`:
   ```python
   registry = ProviderRegistry(
       tts=MyNewTTSProvider(api_key=...),
       voice_clone=ElevenLabsCloneProvider(...),
   )
   ```
Command handlers never import concrete providers, so no other files need to change.
