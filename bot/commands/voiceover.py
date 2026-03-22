"""
/voiceover command — Instant Voice Cloning via ElevenLabs.

State range: 10–19
  WAITING_SAMPLE = 10
  WAITING_TEXT   = 11
"""

import io

from telegram import Update
from telegram.constants import ChatAction
from telegram.ext import (
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

from bot.commands.common import BTN_VOICEOVER, MAIN_MENU, USER_TEXT, cancel, menu_fallbacks
from bot.credits.manager import CreditManager
from bot.registry import ProviderRegistry
from bot.utils.audio import delete_temp_file, download_telegram_audio

WAITING_SAMPLE = 10
WAITING_TEXT = 11


async def voiceover_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text(
        "Send an audio sample — a voice message or MP3 file.\n"
        "_30–90 seconds of clear speech works best._",
        parse_mode="Markdown",
    )
    return WAITING_SAMPLE


async def receive_sample(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    message = update.message

    # Accept voice messages or audio file uploads
    if message.voice:
        file_id = message.voice.file_id
    elif message.audio:
        file_id = message.audio.file_id
    else:
        await message.reply_text("Please send a voice message or an audio file.")
        return WAITING_SAMPLE

    user_id = message.from_user.id
    sample_path = await download_telegram_audio(bot=context.bot, file_id=file_id, user_id=user_id)
    context.user_data["sample_path"] = sample_path

    await message.reply_text("Got it! Now send the text to speak in that voice.")
    return WAITING_TEXT


async def receive_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    sample_path = context.user_data.get("sample_path")

    if not sample_path:
        await update.message.reply_text("Something went wrong. Please start again with /voiceover.")
        return ConversationHandler.END

    user_id = update.message.from_user.id
    cm: CreditManager = context.bot_data["credit_manager"]
    await cm.ensure_user(user_id)

    if not await cm.check_and_deduct(user_id, "voiceover"):
        bal = await cm.get_balance(user_id)
        await update.message.reply_text(
            f"❌ Not enough credits (balance: {bal}).\nTap 💳 Credits to top up.",
            reply_markup=MAIN_MENU,
        )
        return ConversationHandler.END

    await update.message.reply_text("Cloning voice and generating audio…")
    await update.message.chat.send_action(ChatAction.UPLOAD_VOICE)

    registry: ProviderRegistry = context.bot_data["registry"]
    clone_provider = registry.get_voice_clone()

    voice_name = f"ivc_{update.message.from_user.id}"
    try:
        result = await clone_provider.clone_and_speak(
            sample_path=sample_path,
            text=text,
            voice_name=voice_name,
        )
    except Exception as e:
        await update.message.reply_text(
            f"❌ Voice cloning failed: {e}",
            reply_markup=MAIN_MENU,
        )
        return ConversationHandler.END
    finally:
        delete_temp_file(sample_path)
        cancelled = context.user_data.pop("_cancelled", False)
        context.user_data.clear()

    if cancelled:
        return ConversationHandler.END

    audio_file = io.BytesIO(result.audio_bytes)
    audio_file.name = "voiceover.mp3"
    await update.message.reply_audio(
        audio=audio_file,
        title="Voiceover",
        caption="Done! The cloned voice has been removed from our servers.",
    )
    return ConversationHandler.END


def build_voiceover_handler() -> ConversationHandler:
    audio_filter = filters.VOICE | filters.AUDIO
    return ConversationHandler(
        entry_points=[
            CommandHandler("voiceover", voiceover_start),
            MessageHandler(filters.Text([BTN_VOICEOVER]), voiceover_start),
        ],
        states={
            WAITING_SAMPLE: [MessageHandler(audio_filter, receive_sample)],
            WAITING_TEXT: [MessageHandler(USER_TEXT, receive_text)],
        },
        fallbacks=[CommandHandler("cancel", cancel), *menu_fallbacks()],
    )
