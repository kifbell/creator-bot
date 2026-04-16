"""
/info command — About & Data Processing Agreement.

State range: 50–59
  INFO_MENU      = 50
"""

from telegram import KeyboardButton, ReplyKeyboardMarkup, Update
from telegram.ext import (
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

from bot.commands.common import BTN_INFO, MAIN_MENU, cancel, menu_fallbacks
from bot.config import settings

INFO_MENU = 50

_ABOUT_LABEL = "📖 About"
_AGREEMENT_LABEL = "📋 Agreement"
_BACK_LABEL = "⬅️ Back"

_INFO_KB = ReplyKeyboardMarkup(
    [
        [KeyboardButton(_ABOUT_LABEL), KeyboardButton(_AGREEMENT_LABEL)],
        [KeyboardButton(_BACK_LABEL)],
    ],
    resize_keyboard=True,
)

_ABOUT_TEXT = (
    f"*AI Creator Bot*  ·  `{settings.bot_env}`\n\n"
    "🎙 *Speak* — Text-to-speech using ElevenLabs preset voices or a custom voice description\n"
    "🎤 *Voiceover* — Upload a voice sample, then generate speech that sounds like it\n"
    "🎵 *Song* — Generate a sound/music clip from a text prompt\n\n"
    "Use /cancel at any time to exit a flow."
)

_AGREEMENT_TEXT = (
    "*Data Processing Information*\n\n"
    "This bot transmits your data to third-party services to provide its features:\n\n"
    "🎙 *Speak / Voiceover*\n"
    "• Your text and voice descriptions are sent to ElevenLabs (elevenlabs.io)\n"
    "• Voice samples uploaded for cloning are sent to ElevenLabs for processing\n"
    "• Cloned voices are deleted from ElevenLabs servers immediately after use\n\n"
    "🎵 *Song*\n"
    "• Your text prompts are sent to ElevenLabs or Tempolor (tempolor.com) "
    "depending on your selected provider\n\n"
    "💳 *Credits (planned)*\n"
    "• Payment data will be processed by YooKassa (yookassa.ru)\n"
    "• The bot does not store payment card details\n\n"
    "*Stored locally:*\n"
    "• Voice descriptions and sample files are stored on the bot server\n"
    "• Credit balance and transaction history are stored on the bot server\n"
    "• No data is shared between users\n\n"
    "*Third-party privacy policies:*\n"
    "• ElevenLabs: elevenlabs.io/privacy\n"
    "• Tempolor: tempolor.com/privacy\n"
    "• YooKassa: yookassa.ru/privacy"
)


async def info_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text(
        _ABOUT_TEXT,
        parse_mode="Markdown",
        reply_markup=_INFO_KB,
    )
    return INFO_MENU


async def info_menu_choice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()

    if text == _ABOUT_LABEL:
        await update.message.reply_text(
            _ABOUT_TEXT,
            parse_mode="Markdown",
            reply_markup=_INFO_KB,
        )
        return INFO_MENU

    if text == _AGREEMENT_LABEL:
        await update.message.reply_text(
            _AGREEMENT_TEXT,
            parse_mode="Markdown",
            reply_markup=_INFO_KB,
        )
        return INFO_MENU

    if text == _BACK_LABEL:
        await update.message.reply_text("👋 Back to menu", reply_markup=MAIN_MENU)
        return ConversationHandler.END

    await update.message.reply_text("Please tap one of the buttons.")
    return INFO_MENU


def build_info_handler() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[
            MessageHandler(filters.Text([BTN_INFO]), info_start),
        ],
        states={
            INFO_MENU: [MessageHandler(
                filters.Text([_ABOUT_LABEL, _AGREEMENT_LABEL, _BACK_LABEL]),
                info_menu_choice,
            )],
        },
        fallbacks=[CommandHandler("cancel", cancel), *menu_fallbacks()],
        per_message=False,
    )
