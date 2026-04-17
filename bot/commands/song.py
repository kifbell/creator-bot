"""
/song command — music generation via selected provider.

State range: 20–29
  TYPING_PROMPT = 20
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

from bot.commands.common import BTN_SONG, MAIN_MENU, USER_TEXT, cancel, menu_fallbacks
from bot.credits.manager import CreditManager
from bot.registry import ProviderRegistry

TYPING_PROMPT = 20

_DEFAULT_PROVIDER = "tempolor"


async def song_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    provider = context.user_data.get("music_provider", _DEFAULT_PROVIDER)
    await update.message.reply_text(
        f"🎵 Describe the music you want:\n\n"
        f"_e.g. upbeat electronic pop, cinematic orchestral, lo-fi hip hop_\n\n"
        f"Model: *{provider}*  ·  change via ⚙️ Settings",
        parse_mode="Markdown",
    )
    return TYPING_PROMPT


async def receive_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    prompt = update.message.text.strip()
    provider = context.user_data.get("music_provider", _DEFAULT_PROVIDER)

    user_id = update.message.from_user.id
    cm: CreditManager = context.bot_data["credit_manager"]
    await cm.ensure_user(user_id)

    if not await cm.check_and_deduct(user_id, "song"):
        bal = await cm.get_balance(user_id)
        await update.message.reply_text(
            f"❌ Not enough credits (balance: {bal}).\nTap 💳 Credits to top up.",
            reply_markup=MAIN_MENU,
        )
        return ConversationHandler.END

    await update.message.reply_text("Generating… this may take up to a minute ⏳")
    await update.message.chat.send_action(ChatAction.UPLOAD_VOICE)

    registry: ProviderRegistry = context.bot_data["registry"]
    music = registry.get_music(provider=provider)

    try:
        result = await music.generate(prompt=prompt)
    except Exception as e:
        await cm.refund(user_id, "song")
        await update.message.reply_text(
            f"❌ Generation failed: {e}\nCredits refunded.",
            reply_markup=MAIN_MENU,
        )
        return ConversationHandler.END

    audio_file = io.BytesIO(result.audio_bytes)
    audio_file.name = "song.mp3"
    await update.message.reply_audio(
        audio=audio_file,
        title=prompt[:64],
        reply_markup=MAIN_MENU,
    )

    context.user_data.clear()
    return ConversationHandler.END


def build_song_handler() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[
            CommandHandler("song", song_start),
            MessageHandler(filters.Text([BTN_SONG]), song_start),
        ],
        states={
            TYPING_PROMPT: [MessageHandler(USER_TEXT, receive_prompt)],
        },
        fallbacks=[CommandHandler("cancel", cancel), *menu_fallbacks()],
        per_message=False,
    )
