"""
/topup command — credit top-up flow with Mock and YooKassa providers.

State range: 40-49
  CHOOSING_METHOD  = 40
  CHOOSING_AMOUNT  = 41
  WAITING_PAYMENT  = 42
"""

import logging
import uuid
from datetime import datetime, timedelta, timezone

from telegram import KeyboardButton, ReplyKeyboardMarkup, Update
from telegram.ext import (
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

from bot.commands.common import BTN_CREDITS, MAIN_MENU, USER_TEXT, cancel, menu_fallbacks
from bot.credits.costs import TOPUP_BUTTONS, credits_for_rub
from bot.credits.manager import CreditManager
from bot.registry import ProviderRegistry

logger = logging.getLogger(__name__)

CHOOSING_METHOD = 40
CHOOSING_AMOUNT = 41
WAITING_PAYMENT = 42

# Payment-flow button labels — kept distinct from MAIN_MENU labels.
# DO NOT add these to bot/commands/buttons.py:ALL — that would make USER_TEXT
# exclude them and the state handlers would never see the taps.
_BTN_MOCK = "🔧 Mock (test)"
_BTN_YOOKASSA = "💳 YooKassa"
_BTN_RESUME = "✅ Resume"
_BTN_NEW = "🆕 New payment"
_BTN_ABANDON = "🛑 Abandon"
_BTN_CHECK = "✅ Check payment"

_PROVIDER_LABEL_TO_KEY = {_BTN_MOCK: "mock", _BTN_YOOKASSA: "yookassa"}
_GUARD_KEY = "topup_in_progress"
_PAYMENT_LINK_TTL_HOURS = 24


# ── Helpers ───────────────────────────────────────────────────────────

def _clear_guard(context: ContextTypes.DEFAULT_TYPE) -> None:
    context.user_data.pop(_GUARD_KEY, None)
    context.user_data.pop("payment_id", None)
    context.user_data.pop("payment_provider_key", None)
    context.user_data.pop("_idem_keys", None)


def _idempotency_key_for(
    context: ContextTypes.DEFAULT_TYPE, provider_key: str, amount_rub: int
) -> str:
    """Return a stable idempotency key for (provider, amount) within this conversation.
    Re-tapping the same amount after a transient error reuses the same key,
    so YooKassa returns the same payment instead of creating a duplicate."""
    cache_key = f"{provider_key}:{amount_rub}"
    cache = context.user_data.setdefault("_idem_keys", {})
    if cache_key not in cache:
        cache[cache_key] = uuid.uuid4().hex
    return cache[cache_key]


def _amount_keyboard() -> ReplyKeyboardMarkup:
    rows = [[KeyboardButton(f"{rub} ₽ ({credits_for_rub(rub)} credits)")] for rub in TOPUP_BUTTONS]
    return ReplyKeyboardMarkup(rows, resize_keyboard=True, one_time_keyboard=True)


def _waiting_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [[KeyboardButton(_BTN_CHECK)], [KeyboardButton(_BTN_ABANDON)]],
        resize_keyboard=True,
    )


def _parse_amount(text: str) -> int | None:
    """Extract RUB int from a label like '100 ₽ (1000 credits)'."""
    try:
        return int(text.split()[0])
    except (ValueError, IndexError):
        return None


def _is_link_expired(created_at_iso: str) -> bool:
    try:
        created = datetime.fromisoformat(created_at_iso)
    except ValueError:
        return False
    return datetime.now(timezone.utc) - created > timedelta(hours=_PAYMENT_LINK_TTL_HOURS)


# ── Entry: /topup ─────────────────────────────────────────────────────

async def topup_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    # Re-entry guard: with concurrent_updates=True, a second simultaneous tap
    # could otherwise spawn a parallel topup flow.
    if context.user_data.get(_GUARD_KEY):
        await update.message.reply_text(
            "⚠️ You already have a payment flow in progress. Tap /cancel first.",
            reply_markup=MAIN_MENU,
        )
        return ConversationHandler.END

    cm: CreditManager = context.bot_data["credit_manager"]
    user_id = update.message.from_user.id
    await cm.ensure_user(user_id)
    balance = await cm.get_balance(user_id)

    # Resume Payment UX: if there's an orphan pending payment, offer to resume.
    from bot.db import credits as db
    pending = await db.get_pending_payment_for_user(user_id)
    if pending:
        if _is_link_expired(pending["created_at"]):
            # Auto-cancel and proceed to fresh method picker.
            await db.mark_payment_status(pending["payment_id"], "canceled")
            logger.info(f"Auto-canceled expired pending payment {pending['payment_id']}")
        else:
            context.user_data[_GUARD_KEY] = True
            context.user_data["payment_id"] = pending["payment_id"]
            context.user_data["payment_provider_key"] = pending["provider"]
            kb = ReplyKeyboardMarkup(
                [[KeyboardButton(_BTN_RESUME)], [KeyboardButton(_BTN_NEW)], [KeyboardButton(_BTN_ABANDON)]],
                resize_keyboard=True,
            )
            await update.message.reply_text(
                f"💳 *Balance: {balance} credits*\n\n"
                f"⏳ You have a pending payment from {pending['created_at']}\n"
                f"({pending['amount_rub']} ₽ → {pending['credits']} credits, via {pending['provider']}).\n\n"
                f"Resume to check it, abandon to cancel, or start a new one.",
                parse_mode="Markdown",
                reply_markup=kb,
            )
            return WAITING_PAYMENT

    # No orphan — show method picker.
    context.user_data[_GUARD_KEY] = True
    registry: ProviderRegistry = context.bot_data["registry"]
    available = registry.payment_providers()
    rows = []
    if "mock" in available:
        rows.append([KeyboardButton(_BTN_MOCK)])
    if "yookassa" in available:
        rows.append([KeyboardButton(_BTN_YOOKASSA)])

    if not rows:
        _clear_guard(context)
        await update.message.reply_text(
            "❌ No payment methods configured.",
            reply_markup=MAIN_MENU,
        )
        return ConversationHandler.END

    await update.message.reply_text(
        f"💳 *Balance: {balance} credits*\n\nChoose a payment method:",
        parse_mode="Markdown",
        reply_markup=ReplyKeyboardMarkup(rows, resize_keyboard=True, one_time_keyboard=True),
    )
    return CHOOSING_METHOD


# ── State 40: method choice ───────────────────────────────────────────

async def method_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    label = update.message.text.strip()
    provider_key = _PROVIDER_LABEL_TO_KEY.get(label)
    if provider_key is None:
        await update.message.reply_text("Please tap one of the method buttons.")
        return CHOOSING_METHOD

    registry: ProviderRegistry = context.bot_data["registry"]
    if provider_key not in registry.payment_providers():
        await update.message.reply_text(
            f"❌ Provider '{provider_key}' is not configured.",
            reply_markup=MAIN_MENU,
        )
        _clear_guard(context)
        return ConversationHandler.END

    context.user_data["payment_provider_key"] = provider_key
    await update.message.reply_text(
        f"Selected: *{label}*\n\nChoose an amount:",
        parse_mode="Markdown",
        reply_markup=_amount_keyboard(),
    )
    return CHOOSING_AMOUNT


# ── State 41: amount choice ───────────────────────────────────────────

async def amount_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    amount_rub = _parse_amount(text)
    if amount_rub is None or amount_rub not in TOPUP_BUTTONS:
        await update.message.reply_text("Please tap one of the amount buttons.")
        return CHOOSING_AMOUNT

    user_id = update.message.from_user.id
    provider_key = context.user_data.get("payment_provider_key")
    if not provider_key:
        await update.message.reply_text("Something went wrong. Start again with /topup.", reply_markup=MAIN_MENU)
        _clear_guard(context)
        return ConversationHandler.END

    registry: ProviderRegistry = context.bot_data["registry"]
    cm: CreditManager = context.bot_data["credit_manager"]
    provider = registry.get_payment(provider_key)

    idempotency_key = _idempotency_key_for(context, provider_key, amount_rub)

    try:
        payment_id, url = await cm.create_pending_payment(
            user_id=user_id,
            provider_key=provider_key,
            provider=provider,
            amount_rub=amount_rub,
            idempotency_key=idempotency_key,
        )
    except RuntimeError as e:
        # Keep the idempotency key in user_data so the next retry reuses it.
        logger.warning(
            "create_payment_retry_eligible user_id=%s provider=%s amount=%s err=%s",
            user_id, provider_key, amount_rub, e,
        )
        await update.message.reply_text(
            f"❌ Could not create payment: {e}\nTry again or pick another amount.",
        )
        return CHOOSING_AMOUNT

    context.user_data["payment_id"] = payment_id
    credits = credits_for_rub(amount_rub)

    # Mock has empty URL → confirm immediately.
    if not url:
        return await _confirm_payment(update, context)

    await update.message.reply_text(
        f"💳 Payment created: *{amount_rub} ₽ → {credits} credits*\n\n"
        f"1. Open this link to pay:\n{url}\n\n"
        f"2. After paying, tap ✅ Check payment.\n"
        f"Tap 🛑 Abandon to cancel.",
        parse_mode="Markdown",
        reply_markup=_waiting_keyboard(),
        disable_web_page_preview=False,
    )
    return WAITING_PAYMENT


# ── State 42: waiting (Check / Abandon / Resume / New) ────────────────

async def _confirm_payment(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Poll provider, update DB, credit if succeeded, end the conversation."""
    payment_id = context.user_data.get("payment_id")
    provider_key = context.user_data.get("payment_provider_key")
    if not payment_id or not provider_key:
        await update.message.reply_text("No active payment. Start again with /topup.", reply_markup=MAIN_MENU)
        _clear_guard(context)
        return ConversationHandler.END

    registry: ProviderRegistry = context.bot_data["registry"]
    cm: CreditManager = context.bot_data["credit_manager"]
    provider = registry.get_payment(provider_key)

    try:
        status, new_balance = await cm.confirm_pending_payment(provider, payment_id)
    except RuntimeError as e:
        await update.message.reply_text(
            f"⏳ Could not check status right now: {e}\nTap ✅ Check payment again shortly.",
            reply_markup=_waiting_keyboard(),
        )
        return WAITING_PAYMENT

    if status == "succeeded":
        await update.message.reply_text(
            f"✅ Payment confirmed!\nNew balance: *{new_balance}* credits.",
            parse_mode="Markdown",
            reply_markup=MAIN_MENU,
        )
        _clear_guard(context)
        return ConversationHandler.END
    if status == "already_credited":
        bal = await cm.get_balance(update.message.from_user.id)
        await update.message.reply_text(
            f"✅ Payment already confirmed.\nBalance: *{bal}* credits.",
            parse_mode="Markdown",
            reply_markup=MAIN_MENU,
        )
        _clear_guard(context)
        return ConversationHandler.END
    if status == "canceled":
        await update.message.reply_text(
            "❌ Payment canceled or expired.",
            reply_markup=MAIN_MENU,
        )
        _clear_guard(context)
        return ConversationHandler.END
    # status == "pending"
    await update.message.reply_text(
        "⏳ Still waiting for payment. Pay via the link, then tap ✅ Check payment again.",
        reply_markup=_waiting_keyboard(),
    )
    return WAITING_PAYMENT


async def waiting_action(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()

    if text in (_BTN_CHECK, _BTN_RESUME):
        # Check expiration before confirming.
        from bot.db import credits as db
        payment_id = context.user_data.get("payment_id")
        if payment_id:
            row = await db.get_pending_payment(payment_id)
            if row and row["status"] == "pending" and _is_link_expired(row["created_at"]):
                await db.mark_payment_status(payment_id, "canceled")
                await update.message.reply_text(
                    "⌛ Payment link expired (>24h). Start a new one with /topup.",
                    reply_markup=MAIN_MENU,
                )
                _clear_guard(context)
                return ConversationHandler.END
        return await _confirm_payment(update, context)

    if text == _BTN_ABANDON:
        payment_id = context.user_data.get("payment_id")
        provider_key = context.user_data.get("payment_provider_key")
        if payment_id and provider_key:
            cm: CreditManager = context.bot_data["credit_manager"]
            registry: ProviderRegistry = context.bot_data["registry"]
            provider = registry.get_payment(provider_key)
            # Defensive: re-poll the provider before abandoning. If user
            # already paid externally, credit them instead of forfeiting.
            status, balance = await cm.abandon_pending_payment(provider, payment_id)
            if status == "succeeded":
                await update.message.reply_text(
                    f"✅ Payment was already completed!\nNew balance: *{balance}* credits.",
                    parse_mode="Markdown",
                    reply_markup=MAIN_MENU,
                )
            elif status == "already_credited":
                bal = await cm.get_balance(update.message.from_user.id)
                await update.message.reply_text(
                    f"✅ Payment was already credited.\nBalance: *{bal}* credits.",
                    parse_mode="Markdown",
                    reply_markup=MAIN_MENU,
                )
            else:
                await update.message.reply_text("🛑 Payment abandoned.", reply_markup=MAIN_MENU)
        else:
            await update.message.reply_text("🛑 Payment abandoned.", reply_markup=MAIN_MENU)
        _clear_guard(context)
        return ConversationHandler.END

    if text == _BTN_NEW:
        # Defensively abandon the orphan pending payment, then re-enter the flow.
        payment_id = context.user_data.get("payment_id")
        provider_key = context.user_data.get("payment_provider_key")
        if payment_id and provider_key:
            cm: CreditManager = context.bot_data["credit_manager"]
            registry: ProviderRegistry = context.bot_data["registry"]
            provider = registry.get_payment(provider_key)
            await cm.abandon_pending_payment(provider, payment_id)
        _clear_guard(context)
        return await topup_start(update, context)

    await update.message.reply_text("Please tap one of the buttons.")
    return WAITING_PAYMENT


# ── Entry-point cancel handler — clears the re-entry guard ────────────

async def topup_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    _clear_guard(context)
    return await cancel(update, context)


def build_topup_handler() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[
            CommandHandler("topup", topup_start),
            MessageHandler(filters.Text([BTN_CREDITS]), topup_start),
        ],
        states={
            CHOOSING_METHOD: [MessageHandler(USER_TEXT, method_chosen)],
            CHOOSING_AMOUNT: [MessageHandler(USER_TEXT, amount_chosen)],
            WAITING_PAYMENT: [MessageHandler(
                filters.Text([_BTN_CHECK, _BTN_RESUME, _BTN_ABANDON, _BTN_NEW]),
                waiting_action,
            )],
        },
        fallbacks=[CommandHandler("cancel", topup_cancel), *menu_fallbacks()],
        per_message=False,
        persistent=True,
        name="topup",
    )
