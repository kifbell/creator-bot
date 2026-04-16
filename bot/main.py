"""Entry point — bootstraps the Telegram Application and registers all handlers."""

import logging
from logging.handlers import RotatingFileHandler

from telegram.ext import Application, CommandHandler, MessageHandler, filters

from bot.commands.common import cancel, help_command, start
from bot.commands.info import build_info_handler
from bot.commands.settings import build_settings_handler
from bot.commands.song import build_song_handler
from bot.commands.speak import build_speak_handler
from bot.commands.topup import build_topup_handler
from bot.commands.voiceover import build_voiceover_handler
from bot.config import settings
from bot.credits.manager import CreditManager
from bot.db.credits import init_db
from bot.db.voices import init_voices_db
from bot.providers.payment.mock_payment import MockPaymentProvider
from bot.providers.music.elevenlabs_music import ElevenLabsMusicProvider
from bot.providers.music.tempolor_music import TempolorMusicProvider
from bot.providers.stub.stub_clone import StubVoiceCloneProvider
from bot.providers.stub.stub_music import StubMusicProvider
from bot.providers.stub.stub_tts import StubTTSProvider
from bot.providers.tts.elevenlabs_tts import ElevenLabsTTSProvider
from bot.providers.voice_clone.elevenlabs_clone import ElevenLabsCloneProvider
from bot.registry import ProviderRegistry

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    level=logging.INFO,
    handlers=[
        logging.StreamHandler(),
        RotatingFileHandler("bot.log", maxBytes=5*1024*1024, backupCount=3, encoding="utf-8"),
    ],
)
logger = logging.getLogger(__name__)


def main() -> None:
    init_db()
    init_voices_db()

    app = Application.builder().token(settings.telegram_bot_token).build()

    if settings.bot_env == "test":
        logger.info("BOT_ENV=test — using stub providers (no API calls will be made)")
        registry = ProviderRegistry(
            tts=StubTTSProvider(),
            voice_clone=StubVoiceCloneProvider(),
            music_providers={
                "elevenlabs": StubMusicProvider(),
                "tempolor": StubMusicProvider(),
            },
        )
    else:
        logger.info("BOT_ENV=prod — using real API providers")
        registry = ProviderRegistry(
            tts=ElevenLabsTTSProvider(api_key=settings.elevenlabs_api_key),
            voice_clone=ElevenLabsCloneProvider(api_key=settings.elevenlabs_api_key),
            music_providers={
                "elevenlabs": ElevenLabsMusicProvider(api_key=settings.elevenlabs_api_key),
                "tempolor": TempolorMusicProvider(api_key=settings.tempolor_api_key),
            },
        )

    app.bot_data["registry"] = registry
    app.bot_data["credit_manager"] = CreditManager(MockPaymentProvider())

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))

    app.add_handler(build_speak_handler())
    app.add_handler(build_voiceover_handler())
    app.add_handler(build_song_handler())
    app.add_handler(build_settings_handler())
    app.add_handler(build_topup_handler())

    app.add_handler(build_info_handler())

    app.add_handler(CommandHandler("cancel", cancel))

    logger.info("Bot starting…")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
