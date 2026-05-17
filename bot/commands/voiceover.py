"""
/voiceover command — Instant Voice Cloning via ElevenLabs.

State range: 10–19
  WAITING_SAMPLE        = 10
  WAITING_TEXT          = 11
  SAVE_VOICE_SAMPLE     = 12
  NAME_VOICE_SAMPLE     = 13
  CHOOSING_SAVED_SAMPLE = 14
  CHOOSING_DELETE_SAMPLE = 15
"""

import io
import logging
import os
import sqlite3
import time

from telegram import KeyboardButton, ReplyKeyboardMarkup, ReplyKeyboardRemove, Update
from telegram.constants import ChatAction
from telegram.ext import (
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

from bot.commands.common import BTN_VOICEOVER, MAIN_MENU, USER_TEXT, cancel, get_provider, menu_fallbacks
from bot.credits.manager import CreditManager
from bot.db.voices import delete_voice_sample, list_voice_samples, save_voice_sample
from bot.registry import ProviderRegistry
from bot.utils.audio import delete_temp_file, download_telegram_audio, persist_voice_sample

logger = logging.getLogger(__name__)

WAITING_SAMPLE = 10
WAITING_TEXT = 11
SAVE_VOICE_SAMPLE = 12
NAME_VOICE_SAMPLE = 13
CHOOSING_SAVED_SAMPLE = 14
CHOOSING_DELETE_SAMPLE = 15

_RECORD_NEW_LABEL = "🎙️ Record new"
_DELETE_LABEL = "🗑 Delete"
_BACK_LABEL = "⬅️ Back"

_YES_NO_KB = ReplyKeyboardMarkup(
    [[KeyboardButton("Yes"), KeyboardButton("No")]],
    resize_keyboard=True,
    one_time_keyboard=True,
)


async def voiceover_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.message.from_user.id
    saved = await list_voice_samples(user_id)

    if saved:
        mapping = {}
        keyboard = []
        for sample_id, name, file_path in saved:
            label = f"{name}"
            mapping[label] = (sample_id, file_path)
            keyboard.append([KeyboardButton(label)])
        keyboard.append([KeyboardButton(_RECORD_NEW_LABEL), KeyboardButton(_DELETE_LABEL)])

        context.user_data["_saved_sample_map"] = mapping

        await update.message.reply_text(
            "Choose a saved voice sample or record a new one:",
            reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True),
        )
        return CHOOSING_SAVED_SAMPLE

    await update.message.reply_text(
        "Send an audio sample — a voice message or MP3 file.\n"
        "_30–90 seconds of clear speech works best._",
        parse_mode="Markdown",
    )
    return WAITING_SAMPLE


async def saved_sample_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()

    if text == _RECORD_NEW_LABEL:
        context.user_data.pop("_saved_sample_map", None)
        await update.message.reply_text(
            "Send an audio sample — a voice message or MP3 file.\n"
            "_30–90 seconds of clear speech works best._",
            parse_mode="Markdown",
            reply_markup=ReplyKeyboardRemove(),
        )
        return WAITING_SAMPLE

    if text == _DELETE_LABEL:
        mapping = context.user_data.get("_saved_sample_map", {})
        keyboard = [[KeyboardButton(label)] for label in mapping]
        keyboard.append([KeyboardButton(_BACK_LABEL)])
        await update.message.reply_text(
            "Tap a sample to delete:",
            reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True),
        )
        return CHOOSING_DELETE_SAMPLE

    mapping = context.user_data.get("_saved_sample_map", {})
    entry = mapping.get(text)
    if not entry:
        await update.message.reply_text("Please tap one of the buttons.")
        return CHOOSING_SAVED_SAMPLE

    _sample_id, file_path = entry
    context.user_data["sample_path"] = file_path
    context.user_data["_using_saved_sample"] = True
    context.user_data.pop("_saved_sample_map", None)

    await update.message.reply_text(
        f"Using saved sample: *{text}*\n\nSend the text to speak in that voice.",
        parse_mode="Markdown",
        reply_markup=ReplyKeyboardRemove(),
    )
    return WAITING_TEXT


async def delete_sample_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()

    if text == _BACK_LABEL:
        context.user_data.pop("_saved_sample_map", None)
        return await voiceover_start(update, context)

    mapping = context.user_data.get("_saved_sample_map", {})
    entry = mapping.get(text)
    if not entry:
        await update.message.reply_text("Please tap one of the buttons.")
        return CHOOSING_DELETE_SAMPLE

    sample_id, file_path = entry
    user_id = update.message.from_user.id
    await delete_voice_sample(user_id, sample_id)
    delete_temp_file(file_path)
    context.user_data.pop("_saved_sample_map", None)

    await update.message.reply_text(
        f"✅ Sample \"{text}\" deleted.",
        reply_markup=MAIN_MENU,
    )
    return ConversationHandler.END


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
    # Persist the Telegram file_id as a backup recovery path. Samples are now
    # stored under data/voices/uploads/ which survives reboots, but the file_id
    # still lets us re-download if the on-disk file is deleted out of band
    # (e.g. manual cleanup). Telegram retains the file for ~24h.
    context.user_data["sample_file_id"] = file_id

    await message.reply_text("Got it! Now send the text to speak in that voice.")
    return WAITING_TEXT


async def receive_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    sample_path = context.user_data.get("sample_path")
    sample_file_id = context.user_data.get("sample_file_id")
    user_id = update.message.from_user.id

    if not sample_path:
        await update.message.reply_text("Something went wrong. Please start again with /voiceover.")
        context.user_data.clear()
        return ConversationHandler.END

    # Restart-safety: if the local file vanished (e.g. manual cleanup of
    # data/voices/uploads/), re-download from Telegram using the persisted
    # file_id. Only applies to the new-sample flow — saved samples in
    # data/voices/{user_id}/ are expected to be durable.
    if not os.path.exists(sample_path):
        if sample_file_id:
            sample_path = await download_telegram_audio(
                bot=context.bot, file_id=sample_file_id, user_id=user_id
            )
            context.user_data["sample_path"] = sample_path
        else:
            await update.message.reply_text(
                "❌ The voice sample is no longer available. Please start again with /voiceover.",
                reply_markup=MAIN_MENU,
            )
            context.user_data.clear()
            return ConversationHandler.END

    cm: CreditManager = context.bot_data["credit_manager"]
    await cm.ensure_user(user_id)

    if not text:
        await update.message.reply_text(
            "❌ Please type some text.", reply_markup=MAIN_MENU,
        )
        context.user_data.clear()
        return ConversationHandler.END

    # Length cap from pricing config
    max_len = cm.cfg.max_length.get("voiceover", 5000)
    if len(text) > max_len:
        await update.message.reply_text(
            f"❌ Text too long ({len(text)} chars). Max is {max_len}.",
            reply_markup=MAIN_MENU,
        )
        context.user_data.clear()
        return ConversationHandler.END

    provider_name = await get_provider(context, user_id, "voiceover_provider", "elevenlabs")
    ok, ctx_call = await cm.pre_deduct(user_id, "voiceover", provider_name)
    if not ok:
        bal = await cm.get_balance(user_id)
        await update.message.reply_text(
            f"❌ Not enough credits (balance: {bal}).\nTap 💳 Credits to top up.",
            reply_markup=MAIN_MENU,
        )
        # Clear sample_path/sample_file_id so a future restart can't restore
        # WAITING_TEXT state pointing at an unrelated old sample.
        context.user_data.clear()
        return ConversationHandler.END

    await update.message.reply_text("Cloning voice and generating audio…")
    await update.message.chat.send_action(ChatAction.UPLOAD_VOICE)

    registry: ProviderRegistry = context.bot_data["registry"]
    clone_provider = registry.get_voice_clone(provider=provider_name)

    voice_name = f"ivc_{update.message.from_user.id}"
    using_saved = context.user_data.get("_using_saved_sample", False)

    _t0 = time.perf_counter()
    try:
        result = await clone_provider.clone_and_speak(
            sample_path=sample_path,
            text=text,
            voice_name=voice_name,
        )
    except Exception as e:
        if not using_saved:
            delete_temp_file(sample_path)
        await cm.refund_minimum(ctx_call)
        context.user_data.clear()
        await update.message.reply_text(
            f"❌ Voice cloning failed: {e}\nCredits refunded.",
            reply_markup=MAIN_MENU,
        )
        return ConversationHandler.END
    logger.info(
        "gen_completed command=voiceover provider=%s duration=%.3f text_len=%d",
        provider_name, time.perf_counter() - _t0, len(text),
    )

    try:
        settle = await cm.reconcile(ctx_call, result.usage)
        cost_prefix = "Cost" if ctx_call.mode == "vendor" else "~Cost"
        cost_line = f"{cost_prefix}: {settle.actual_credits} credits. Balance: {settle.new_balance}."
    except Exception as e:
        logger.error("pricing_reconcile_failed call_id=%s err=%r", ctx_call.call_id, e)
        bal = await cm.get_balance(user_id)
        cost_line = f"Cost: {ctx_call.minimum} credits. Balance: {bal}."

    audio_file = io.BytesIO(result.audio_bytes)
    audio_file.name = "voiceover.mp3"
    await update.message.reply_audio(
        audio=audio_file,
        title="Voiceover",
        caption=f"Done! The cloned voice has been removed from our servers.\n{cost_line}",
        reply_markup=MAIN_MENU if using_saved else ReplyKeyboardRemove(),
    )

    # If using a saved sample, skip save prompt — don't delete the file
    if using_saved:
        context.user_data.clear()
        return ConversationHandler.END

    # Persist the temp file and offer to save
    try:
        persisted_path = persist_voice_sample(sample_path, user_id)
    except OSError as e:
        delete_temp_file(sample_path)
        context.user_data.clear()
        await update.message.reply_text(
            f"❌ Could not save voice sample: {e}",
            reply_markup=MAIN_MENU,
        )
        return ConversationHandler.END
    delete_temp_file(sample_path)
    context.user_data["_persisted_path"] = persisted_path

    await update.message.reply_text(
        "Would you like to save this voice sample for future use?",
        reply_markup=_YES_NO_KB,
    )
    return SAVE_VOICE_SAMPLE


async def handle_save_voice_sample(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    answer = update.message.text.strip()

    if answer == "No":
        persisted_path = context.user_data.get("_persisted_path")
        if persisted_path:
            delete_temp_file(persisted_path)
        context.user_data.clear()
        await update.message.reply_text("Got it!", reply_markup=MAIN_MENU)
        return ConversationHandler.END

    if answer == "Yes":
        await update.message.reply_text(
            "Enter a name for this voice sample:",
            reply_markup=ReplyKeyboardRemove(),
        )
        return NAME_VOICE_SAMPLE

    await update.message.reply_text("Please tap Yes or No.")
    return SAVE_VOICE_SAMPLE


async def handle_name_voice_sample(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    name = update.message.text.strip()
    user_id = update.message.from_user.id
    persisted_path = context.user_data.get("_persisted_path", "")

    try:
        await save_voice_sample(user_id, name, persisted_path)
    except sqlite3.IntegrityError:
        await update.message.reply_text(
            f"You already have a sample named \"{name}\". Please choose a different name:"
        )
        return NAME_VOICE_SAMPLE

    await update.message.reply_text(
        f"✅ Voice sample \"{name}\" saved! It will appear when you use /voiceover next time.",
        reply_markup=MAIN_MENU,
    )
    context.user_data.clear()
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
            SAVE_VOICE_SAMPLE: [MessageHandler(USER_TEXT, handle_save_voice_sample)],
            NAME_VOICE_SAMPLE: [MessageHandler(USER_TEXT, handle_name_voice_sample)],
            CHOOSING_SAVED_SAMPLE: [MessageHandler(USER_TEXT, saved_sample_chosen)],
            CHOOSING_DELETE_SAMPLE: [MessageHandler(USER_TEXT, delete_sample_chosen)],
        },
        fallbacks=[CommandHandler("cancel", cancel), *menu_fallbacks()],
        per_message=False,
        persistent=True,
        name="voiceover",
    )
