from telegram import KeyboardButton, ReplyKeyboardMarkup, Update
from telegram.ext import ContextTypes, ConversationHandler

MAIN_MENU = ReplyKeyboardMarkup(
    [
        [KeyboardButton("🎙 Speak"), KeyboardButton("🎤 Voiceover"), KeyboardButton("🎵 Song")],
        [KeyboardButton("ℹ️ Info")],
    ],
    resize_keyboard=True,
    is_persistent=True,
)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "👋 Welcome to *AI Creator Bot*!\n\n"
        "Tap a button below or use a command:\n"
        "• 🎙 *Speak* — Text-to-speech with preset voices\n"
        "• 🎤 *Voiceover* — Clone a voice and speak new text\n"
        "• 🎵 *Song* — Generate a sound/music clip from a text prompt\n"
        "• /cancel — Cancel the current operation",
        parse_mode="Markdown",
        reply_markup=MAIN_MENU,
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "*Commands:*\n"
        "/speak — Pick a voice, send text, get MP3\n"
        "/voiceover — Send a voice sample, then text to clone\n"
        "/song — Song generation _(coming soon)_\n"
        "/cancel — Cancel any active flow",
        parse_mode="Markdown",
        reply_markup=MAIN_MENU,
    )


async def more(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "*AI Creator Bot*\n\n"
        "🎙 *Speak* — Text-to-speech using ElevenLabs preset voices or a custom voice description\n"
        "🎤 *Voiceover* — Upload a voice sample, then generate speech that sounds like it\n"
        "🎵 *Song* — Generate a sound/music clip from a text prompt\n\n"
        "Use /cancel at any time to exit a flow.",
        parse_mode="Markdown",
        reply_markup=MAIN_MENU,
    )


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.clear()
    await update.message.reply_text(
        "Cancelled.",
        reply_markup=MAIN_MENU,
    )
    return ConversationHandler.END
