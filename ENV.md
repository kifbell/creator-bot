# Environments

The bot supports two environments controlled by the `BOT_ENV` variable. Any other value causes an immediate startup error.

## `prod` (default)

Real API providers are used for every operation:

- TTS and voice clone → ElevenLabs
- Music generation → ElevenLabs or Tempolor (user-selectable via ⚙️ Settings)

All API keys must be valid and have sufficient quota.

## `test`

Stub providers replace every AI call. No external APIs are contacted.
A tiny silent MP3 is returned instead of generated audio.

The full conversation flow — commands, buttons, state transitions — is identical to prod.
Use this mode to verify UI/UX without spending API credits.

## How to switch

In `.env`:

```
BOT_ENV=test   # test mode
BOT_ENV=prod   # production mode (default if omitted)
```

Or inline when starting:

```bash
BOT_ENV=test python -m bot.main
```
