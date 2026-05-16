"""Entry point — bootstraps the Telegram Application and registers all handlers."""

import asyncio
import logging
from logging.handlers import RotatingFileHandler

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    PersistenceInput,
    PicklePersistence,
)

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
from bot.db.preferences import init_preferences_db
from bot.db.voices import init_voices_db
from bot.providers.payment.yookassa_payment import YooKassaPaymentProvider
from bot.providers.music.elevenlabs_music import ElevenLabsMusicProvider
from bot.providers.music.tempolor_music import TempolorMusicProvider
from bot.providers.stub.stub_clone import StubVoiceCloneProvider
from bot.providers.stub.stub_music import StubMusicProvider
from bot.providers.stub.stub_tts import StubTTSProvider
from bot.providers.tts.elevenlabs_tts import ElevenLabsTTSProvider
from bot.providers.tts.openai_tts import OpenAITTSProvider
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


async def _on_error(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Global handler for any uncaught exception inside a Telegram callback.
    Without this, exceptions are swallowed by python-telegram-bot's internal
    error logger and never surface in our bot.log."""
    logger.error("unhandled_exception", exc_info=context.error)
    if isinstance(update, Update) and update.effective_message:
        # Reset ephemeral conversation state so a future restart can't resurrect
        # a half-completed flow (e.g. stale voice_id / sample_path) via the
        # PicklePersistence snapshot.
        if context.user_data is not None:
            context.user_data.clear()
        try:
            await update.effective_message.reply_text(
                "⚠️ Something went wrong. Please try again or tap /cancel."
            )
        except Exception:
            # Best-effort notification — never re-raise from the error handler.
            pass


def main() -> None:
    init_db()
    init_voices_db()
    init_preferences_db()

    persistence = PicklePersistence(
        filepath="data/persistence.pickle",
        store_data=PersistenceInput(bot_data=False),
    )

    app = (
        Application.builder()
        .token(settings.telegram_bot_token)
        .concurrent_updates(True)
        .persistence(persistence)
        .build()
    )

    # Payment providers: YooKassa is the only supported acquirer.
    # If credentials are absent /topup will report "no payment methods configured".
    payment_providers: dict = {}
    if settings.yookassa_shop_id and settings.yookassa_secret_key:
        from yookassa import Configuration
        Configuration.account_id = settings.yookassa_shop_id
        Configuration.secret_key = settings.yookassa_secret_key
        payment_providers["yookassa"] = YooKassaPaymentProvider()
        logger.info("YooKassa payment provider enabled")
    else:
        logger.info("YooKassa credentials not set — /topup will be unavailable")

    if settings.bot_env == "test":
        logger.info("BOT_ENV=test — using stub providers (no API calls will be made)")
        registry = ProviderRegistry(
            tts_providers={
                "elevenlabs": StubTTSProvider(),
                "openai": StubTTSProvider(),
            },
            clone_providers={
                "elevenlabs": StubVoiceCloneProvider(),
            },
            music_providers={
                "elevenlabs": StubMusicProvider(),
                "tempolor": StubMusicProvider(),
            },
            payment_providers=payment_providers,
        )
    else:
        logger.info("BOT_ENV=prod — using real API providers")
        el_sem = asyncio.Semaphore(3)
        tempolor_sem = asyncio.Semaphore(3)
        registry = ProviderRegistry(
            tts_providers={
                "elevenlabs": ElevenLabsTTSProvider(api_key=settings.elevenlabs_api_key, semaphore=el_sem),
                "openai": OpenAITTSProvider(api_key=settings.openai_api_key),
            },
            clone_providers={
                "elevenlabs": ElevenLabsCloneProvider(api_key=settings.elevenlabs_api_key, semaphore=el_sem),
            },
            music_providers={
                "elevenlabs": ElevenLabsMusicProvider(api_key=settings.elevenlabs_api_key, semaphore=el_sem),
                "tempolor": TempolorMusicProvider(api_key=settings.tempolor_api_key, semaphore=tempolor_sem),
            },
            payment_providers=payment_providers,
        )

    app.bot_data["registry"] = registry
    app.bot_data["credit_manager"] = CreditManager()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))

    app.add_handler(build_speak_handler())
    app.add_handler(build_voiceover_handler())
    app.add_handler(build_song_handler())
    app.add_handler(build_settings_handler())
    app.add_handler(build_topup_handler())

    app.add_handler(build_info_handler())

    app.add_handler(CommandHandler("cancel", cancel))
    app.add_error_handler(_on_error)

    logger.info("Bot starting…")
    app.run_polling()


if __name__ == "__main__":
    main()
