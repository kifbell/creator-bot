"""
/topup command — credit top-up flow.

State range: 40–49
  TYPING_AMOUNT = 40
"""

from telegram import Update
from telegram.ext import (
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

from bot.commands.common import BTN_CREDITS, MAIN_MENU, USER_TEXT, cancel, menu_fallbacks
from bot.credits.manager import CreditManager

TYPING_AMOUNT = 40


async def topup_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    cm: CreditManager = context.bot_data["credit_manager"]
    user_id = update.message.from_user.id
    await cm.ensure_user(user_id)
    balance = await cm.get_balance(user_id)

    await update.message.reply_text(
        f"💳 *Balance: {balance} credits*\n\n"
        "Send a number to top up (e.g. `100` → 100 credits):",
        parse_mode="Markdown",
    )
    return TYPING_AMOUNT


async def receive_amount(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    raw = update.message.text.strip()

    try:
        amount = int(raw)
        if amount <= 0:
            raise ValueError
    except ValueError:
        await update.message.reply_text("Please send a positive whole number, e.g. `100`.", parse_mode="Markdown")
        return TYPING_AMOUNT

    cm: CreditManager = context.bot_data["credit_manager"]
    user_id = update.message.from_user.id

    try:
        credits_added, new_balance = await cm.top_up(user_id, amount)
    except ValueError as e:
        await update.message.reply_text(f"❌ {e}", reply_markup=MAIN_MENU)
        return ConversationHandler.END

    await update.message.reply_text(
        f"✅ Added *{credits_added}* credits.\nNew balance: *{new_balance}* credits.",
        parse_mode="Markdown",
        reply_markup=MAIN_MENU,
    )
    return ConversationHandler.END


def build_topup_handler() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[
            CommandHandler("topup", topup_start),
            MessageHandler(filters.Text([BTN_CREDITS]), topup_start),
        ],
        states={
            TYPING_AMOUNT: [MessageHandler(USER_TEXT, receive_amount)],
        },
        fallbacks=[CommandHandler("cancel", cancel), *menu_fallbacks()],
        per_message=False,
    )
