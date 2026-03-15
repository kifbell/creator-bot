"""
/song command — sound/music generation via ElevenLabs text-to-sound-effects.

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

from bot.commands.common import MAIN_MENU, cancel
from bot.registry import ProviderRegistry

TYPING_PROMPT = 20


async def song_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text(
        "🎵 Describe the sound or music you want:\n\n"
        "_e.g. upbeat electronic intro, cinematic orchestral swell, rain on a rooftop_",
        parse_mode="Markdown",
    )
    return TYPING_PROMPT


async def receive_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    prompt = update.message.text.strip()

    await update.message.chat.send_action(ChatAction.UPLOAD_VOICE)

    registry: ProviderRegistry = context.bot_data["registry"]
    music = registry.get_music()
    result = await music.generate(prompt=prompt)

    audio_file = io.BytesIO(result.audio_bytes)
    audio_file.name = "song.mp3"
    await update.message.reply_audio(
        audio=audio_file,
        title=prompt[:64],
        reply_markup=MAIN_MENU,
    )

    return ConversationHandler.END


def build_song_handler() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[
            CommandHandler("song", song_start),
            MessageHandler(filters.Text(["🎵 Song"]), song_start),
        ],
        states={
            TYPING_PROMPT: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_prompt)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        per_message=False,
    )
