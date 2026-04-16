from itertools import groupby

from telegram import KeyboardButton, ReplyKeyboardMarkup, Update
from telegram.ext import CommandHandler, ContextTypes, ConversationHandler, MessageHandler, filters

from bot.commands.buttons import ALL, FallbackAction, MenuButton
from bot.config import settings

# Convenience re-exports so command files can do:
#   from bot.commands.common import BTN_SPEAK
# without changing their import lines.
from bot.commands import buttons as _b
BTN_SPEAK     = _b.SPEAK.label
BTN_VOICEOVER = _b.VOICEOVER.label
BTN_SONG      = _b.SONG.label
BTN_SETTINGS  = _b.SETTINGS.label
BTN_INFO      = _b.INFO.label
BTN_CREDITS   = _b.CREDITS.label
BTN_CANCEL    = _b.CANCEL.label


# ── Handlers referenced by FallbackAction ────────────────────────────────────

async def more(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        f"*AI Creator Bot*  ·  `{settings.bot_env}`\n\n"
        "🎙 *Speak* — Text-to-speech using ElevenLabs preset voices or a custom voice description\n"
        "🎤 *Voiceover* — Upload a voice sample, then generate speech that sounds like it\n"
        "🎵 *Song* — Generate a sound/music clip from a text prompt\n\n"
        "Use /cancel at any time to exit a flow.",
        parse_mode="Markdown",
        reply_markup=MAIN_MENU,
    )


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.clear()
    await update.message.reply_text("Cancelled.", reply_markup=MAIN_MENU)
    return ConversationHandler.END


async def _cancel_flow(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.clear()
    # Re-queue the update so the tapped button's own handler can process it
    # (e.g. tapping Credits mid-song should open the credits flow, not be swallowed)
    await context.application.update_queue.put(update)
    return ConversationHandler.END


_FALLBACK_HANDLERS = {
    FallbackAction.CANCEL_SILENT:  _cancel_flow,
    FallbackAction.CANCEL_MESSAGE: cancel,
    FallbackAction.SHOW_INFO:      more,
}


# ── Derived menu primitives ───────────────────────────────────────────────────

def _build_rows(buttons: list[MenuButton]) -> list[list[KeyboardButton]]:
    rows = []
    for _, group in groupby(buttons, key=lambda b: b.row):
        rows.append([KeyboardButton(b.label) for b in group])
    return rows


MAIN_MENU = ReplyKeyboardMarkup(
    _build_rows(ALL),
    resize_keyboard=True,
    is_persistent=True,
)

USER_TEXT = filters.TEXT & ~filters.COMMAND & ~filters.Text([b.label for b in ALL])


def menu_fallbacks() -> list:
    """Fallbacks for all ConversationHandlers — derived from buttons.ALL."""
    return [
        MessageHandler(filters.Text([b.label]), _FALLBACK_HANDLERS[b.fallback])
        for b in ALL
    ]


# ── Standalone command handlers ───────────────────────────────────────────────

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
        "/song — Song generation\n"
        "/settings — Select model per function\n"
        "/cancel — Cancel any active flow",
        parse_mode="Markdown",
        reply_markup=MAIN_MENU,
    )
