"""
/song command — music generation via selected provider.

State range: 20–29
  TYPING_PROMPT = 20
"""

import io
import logging
import time

from telegram import Update
from telegram.constants import ChatAction
from telegram.ext import (
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

from bot.commands.common import BTN_SONG, MAIN_MENU, USER_TEXT, cancel, get_provider, menu_fallbacks
from bot.credits.manager import CreditManager
from bot.registry import ProviderRegistry

logger = logging.getLogger(__name__)

TYPING_PROMPT = 20

_DEFAULT_PROVIDER = "tempolor"


async def song_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.message.from_user.id
    provider = await get_provider(context, user_id, "music_provider", _DEFAULT_PROVIDER)
    await update.message.reply_text(
        f"🎵 Describe the music you want:\n\n"
        f"_e.g. upbeat electronic pop, cinematic orchestral, lo-fi hip hop_\n\n"
        f"Model: *{provider}*  ·  change via ⚙️ Settings",
        parse_mode="Markdown",
    )
    return TYPING_PROMPT


async def receive_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    prompt = update.message.text.strip()

    user_id = update.message.from_user.id
    provider = await get_provider(context, user_id, "music_provider", _DEFAULT_PROVIDER)
    cm: CreditManager = context.bot_data["credit_manager"]
    await cm.ensure_user(user_id)

    if not prompt:
        await update.message.reply_text(
            "❌ Please type a prompt.", reply_markup=MAIN_MENU,
        )
        context.user_data.clear()
        return ConversationHandler.END

    # Length cap from pricing config — bound worst-case cost
    max_len = cm.cfg.max_length.get("song", 60)
    if len(prompt) > max_len:
        await update.message.reply_text(
            f"❌ Prompt too long ({len(prompt)} chars). Max is {max_len}.",
            reply_markup=MAIN_MENU,
        )
        context.user_data.clear()
        return ConversationHandler.END

    ok, ctx_call = await cm.pre_deduct(user_id, "song", provider)
    if not ok:
        bal = await cm.get_balance(user_id)
        await update.message.reply_text(
            f"❌ Not enough credits (balance: {bal}).\nTap 💳 Credits to top up.",
            reply_markup=MAIN_MENU,
        )
        # Clear ephemeral keys so a future restart can't restore this
        # conversation with stale state.
        context.user_data.clear()
        return ConversationHandler.END

    await update.message.reply_text("Generating… this may take up to a minute ⏳")
    await update.message.chat.send_action(ChatAction.UPLOAD_VOICE)

    registry: ProviderRegistry = context.bot_data["registry"]
    music = registry.get_music(provider=provider)

    _t0 = time.perf_counter()
    try:
        result = await music.generate(prompt=prompt)
    except Exception as e:
        await cm.refund_minimum(ctx_call)
        await update.message.reply_text(
            f"❌ Generation failed: {e}\nCredits refunded.",
            reply_markup=MAIN_MENU,
        )
        context.user_data.clear()
        return ConversationHandler.END
    logger.info(
        "gen_completed command=song provider=%s duration=%.3f prompt_len=%d",
        provider, time.perf_counter() - _t0, len(prompt),
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
    audio_file.name = "song.mp3"
    await update.message.reply_audio(
        audio=audio_file,
        title=prompt[:64],
        caption=cost_line,
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
        persistent=True,
        name="song",
    )
