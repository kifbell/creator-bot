"""
/settings command — select model per function.

State range: 30–39
  CHOOSING_FUNCTION = 30
  CHOOSING_MODEL    = 31
"""

from telegram import KeyboardButton, ReplyKeyboardMarkup, ReplyKeyboardRemove, Update
from telegram.ext import (
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

from bot.commands.common import BTN_SETTINGS, MAIN_MENU, USER_TEXT, cancel, menu_fallbacks

CHOOSING_FUNCTION = 30
CHOOSING_MODEL = 31

# Map function label → available models
_FUNCTION_MODELS: dict[str, list[str]] = {
    "🎵 Music": ["TemPolor v4.0", "ElevenLabs"],
}

# Map model label → provider key used in registry
_MODEL_TO_PROVIDER: dict[str, str] = {
    "TemPolor v4.0": "tempolor",
    "ElevenLabs": "elevenlabs",
}

_SETTING_KEY = "music_provider"


async def settings_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    functions = list(_FUNCTION_MODELS.keys())
    keyboard = [[KeyboardButton(f)] for f in functions]
    await update.message.reply_text(
        "⚙️ *Settings* — select a function to configure:",
        parse_mode="Markdown",
        reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True, is_persistent=True),
    )
    return CHOOSING_FUNCTION


async def function_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    fn = update.message.text.strip()
    if fn not in _FUNCTION_MODELS:
        await update.message.reply_text("Please tap one of the function buttons.")
        return CHOOSING_FUNCTION

    context.user_data["settings_function"] = fn
    models = _FUNCTION_MODELS[fn]
    keyboard = [[KeyboardButton(m)] for m in models]
    await update.message.reply_text(
        f"Select a model for *{fn}*:",
        parse_mode="Markdown",
        reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True, is_persistent=True),
    )
    return CHOOSING_MODEL


async def model_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    model = update.message.text.strip()
    fn = context.user_data.get("settings_function", "🎵 Music")
    valid_models = _FUNCTION_MODELS.get(fn, [])

    if model not in valid_models:
        await update.message.reply_text("Please tap one of the model buttons.")
        return CHOOSING_MODEL

    provider_key = _MODEL_TO_PROVIDER[model]
    context.user_data[_SETTING_KEY] = provider_key

    await update.message.reply_text(
        f"✅ *{fn}* will now use *{model}*.",
        parse_mode="Markdown",
        reply_markup=MAIN_MENU,
    )
    context.user_data.pop("settings_function", None)
    return ConversationHandler.END


def build_settings_handler() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[
            CommandHandler("settings", settings_start),
            MessageHandler(filters.Text([BTN_SETTINGS]), settings_start),
        ],
        states={
            CHOOSING_FUNCTION: [MessageHandler(USER_TEXT, function_chosen)],
            CHOOSING_MODEL: [MessageHandler(USER_TEXT, model_chosen)],
        },
        fallbacks=[CommandHandler("cancel", cancel), *menu_fallbacks()],
        per_message=False,
    )
