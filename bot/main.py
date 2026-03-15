"""Entry point — bootstraps the Telegram Application and registers all handlers."""

import logging

from telegram.ext import Application, CommandHandler, MessageHandler, filters

from bot.commands.common import cancel, help_command, more, start
from bot.commands.song import build_song_handler
from bot.commands.speak import build_speak_handler
from bot.commands.voiceover import build_voiceover_handler
from bot.config import settings
from bot.providers.music.elevenlabs_music import ElevenLabsMusicProvider
from bot.providers.tts.elevenlabs_tts import ElevenLabsTTSProvider
from bot.providers.voice_clone.elevenlabs_clone import ElevenLabsCloneProvider
from bot.registry import ProviderRegistry

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


def main() -> None:
    app = Application.builder().token(settings.telegram_bot_token).build()

    # Wire up providers — swap these lines to change implementations
    registry = ProviderRegistry(
        tts=ElevenLabsTTSProvider(api_key=settings.elevenlabs_api_key),
        voice_clone=ElevenLabsCloneProvider(api_key=settings.elevenlabs_api_key),
        music=ElevenLabsMusicProvider(api_key=settings.elevenlabs_api_key),
    )
    app.bot_data["registry"] = registry

    # Global handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))

    # Conversation handlers (order matters — more specific first)
    app.add_handler(build_speak_handler())
    app.add_handler(build_voiceover_handler())
    app.add_handler(build_song_handler())

    app.add_handler(MessageHandler(filters.Text(["ℹ️ Info"]), more))

    # Standalone /cancel outside any conversation (no-op, friendly message)
    app.add_handler(CommandHandler("cancel", cancel))

    logger.info("Bot starting…")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
