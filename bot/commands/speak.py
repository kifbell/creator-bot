"""
/speak command — TTS with preset ElevenLabs voices or a described voice.

State range: 0–9
  CHOOSING_VOICE        = 0
  TYPING_TEXT           = 1
  TYPING_DESCRIPTION    = 2
  TYPING_DESCRIBED_TEXT = 3
"""

import io

from telegram import KeyboardButton, ReplyKeyboardMarkup, ReplyKeyboardRemove, Update
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

CHOOSING_VOICE = 0
TYPING_TEXT = 1
TYPING_DESCRIPTION = 2
TYPING_DESCRIBED_TEXT = 3

_VOICES_CACHE_KEY = "elevenlabs_voices"
_DESCRIBE_LABEL = "✏️ Describe a voice"


async def speak_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    registry: ProviderRegistry = context.bot_data["registry"]
    tts = registry.get_tts()

    if _VOICES_CACHE_KEY not in context.bot_data:
        voices = await tts.list_voices()
        context.bot_data[_VOICES_CACHE_KEY] = voices
    else:
        voices = context.bot_data[_VOICES_CACHE_KEY]

    keyboard = [[KeyboardButton(v.name)] for v in voices[:10]]
    keyboard.append([KeyboardButton(_DESCRIBE_LABEL)])

    await update.message.reply_text(
        "Choose a voice:",
        reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True),
    )
    return CHOOSING_VOICE


async def voice_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()

    if text == _DESCRIBE_LABEL:
        await update.message.reply_text(
            "Describe the voice you want:\n\n_e.g. deep calm British male, energetic young woman_",
            parse_mode="Markdown",
            reply_markup=ReplyKeyboardRemove(),
        )
        return TYPING_DESCRIPTION

    voices = context.bot_data.get(_VOICES_CACHE_KEY, [])
    voice = next((v for v in voices if v.name == text), None)

    if not voice:
        await update.message.reply_text("Please tap one of the voice buttons.")
        return CHOOSING_VOICE

    context.user_data["voice_id"] = voice.voice_id
    context.user_data["voice_name"] = voice.name

    await update.message.reply_text(
        f"Voice: *{voice.name}*\n\nWhat text should I read aloud?",
        parse_mode="Markdown",
        reply_markup=ReplyKeyboardRemove(),
    )
    return TYPING_TEXT


async def receive_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    voice_id = context.user_data.get("voice_id")

    if not voice_id:
        await update.message.reply_text("Something went wrong. Please start again with /speak.")
        return ConversationHandler.END

    await update.message.chat.send_action(ChatAction.UPLOAD_VOICE)

    registry: ProviderRegistry = context.bot_data["registry"]
    tts = registry.get_tts()
    result = await tts.synthesize(text=text, voice_id=voice_id)

    audio_file = io.BytesIO(result.audio_bytes)
    audio_file.name = "speech.mp3"
    await update.message.reply_audio(
        audio=audio_file,
        title=f"Speech — {context.user_data.get('voice_name', '')}",
        reply_markup=MAIN_MENU,
    )

    context.user_data.clear()
    return ConversationHandler.END


async def describe_voice_received(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["voice_description"] = update.message.text.strip()
    await update.message.reply_text("What text should I read aloud?")
    return TYPING_DESCRIBED_TEXT


async def receive_described_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    description = context.user_data.get("voice_description")

    if not description:
        await update.message.reply_text("Something went wrong. Please start again with /speak.")
        return ConversationHandler.END

    await update.message.chat.send_action(ChatAction.UPLOAD_VOICE)

    registry: ProviderRegistry = context.bot_data["registry"]
    tts = registry.get_tts()
    result = await tts.synthesize_described(text=text, description=description)

    audio_file = io.BytesIO(result.audio_bytes)
    audio_file.name = "speech.mp3"
    await update.message.reply_audio(
        audio=audio_file,
        title=f"Speech — {description}",
        reply_markup=MAIN_MENU,
    )

    context.user_data.clear()
    return ConversationHandler.END


def build_speak_handler() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[
            CommandHandler("speak", speak_start),
            MessageHandler(filters.Text(["🎙 Speak"]), speak_start),
        ],
        states={
            CHOOSING_VOICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, voice_chosen)],
            TYPING_TEXT: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_text)],
            TYPING_DESCRIPTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, describe_voice_received)],
            TYPING_DESCRIBED_TEXT: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_described_text)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        per_message=False,
    )
