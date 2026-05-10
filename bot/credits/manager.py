"""CreditManager — high-level credit operations using the DB layer.

Payment flow:
  1. create_pending_payment(...) → records DB row + returns (payment_id, url)
  2. ... user pays externally (or instantly for Mock) ...
  3. confirm_pending_payment(...) → polls provider, marks status, credits if succeeded
  4. abandon_pending_payment(...) → defensive: re-checks provider before marking canceled,
     so a user who paid then tapped Abandon still gets credited.
"""

import logging

from bot.credits.costs import COSTS, WELCOME_BONUS, credits_for_rub
from bot.db import credits as db
from bot.providers.payment.base_payment import PaymentProvider

_logger = logging.getLogger(__name__)


class CreditManager:
    """Holds no payment provider — handlers pass providers per-call from the registry."""

    async def ensure_user(self, user_id: int) -> None:
        """Idempotent: create user row with WELCOME_BONUS only if missing.
        Safe under concurrency thanks to atomic INSERT OR IGNORE in db.create_user()."""
        await db.create_user(user_id, WELCOME_BONUS, "welcome")

    async def get_balance(self, user_id: int) -> int:
        await self.ensure_user(user_id)
        return await db.get_balance(user_id)

    async def check_and_deduct(self, user_id: int, feature: str) -> bool:
        """Deduct COSTS[feature] if balance is sufficient. Returns False if not enough credits."""
        cost = COSTS[feature]
        return await db.check_and_deduct_credits(user_id, cost, feature)

    async def refund(self, user_id: int, feature: str) -> int:
        """Refund credits for a feature that couldn't be completed (e.g. API failure)."""
        cost = COSTS[feature]
        new_balance = await db.add_credits(user_id, cost, f"refund_{feature}")
        _logger.info(
            "credit_refunded user_id=%s feature=%s amount=%s new_balance=%s",
            user_id, feature, cost, new_balance,
        )
        return new_balance

    # ── Payment flow ─────────────────────────────────────────────────

    async def create_pending_payment(
        self,
        user_id: int,
        provider_key: str,
        provider: PaymentProvider,
        amount_rub: int,
        idempotency_key: str | None = None,
    ) -> tuple[str, str]:
        """Create a pending payment via the given provider, persist it in DB.
        ``idempotency_key`` is forwarded to the provider; reusing the same key
        across retries prevents double-charges on transient network errors.
        Returns (payment_id, payment_url)."""
        credits = credits_for_rub(amount_rub)
        payment_id, url = await provider.create_payment(
            user_id, amount_rub, credits, idempotency_key=idempotency_key
        )
        await db.record_pending_payment(
            payment_id=payment_id,
            user_id=user_id,
            provider=provider_key,
            amount_rub=amount_rub,
            credits=credits,
        )
        _logger.info(
            "topup_initiated user_id=%s provider=%s amount_rub=%s credits=%s payment_id=%s",
            user_id, provider_key, amount_rub, credits, payment_id,
        )
        return payment_id, url

    async def confirm_pending_payment(
        self,
        provider: PaymentProvider,
        payment_id: str,
    ) -> tuple[str, int]:
        """Poll the provider, update DB status, atomically credit if succeeded.
        Returns (status, new_balance) where status is one of
        'pending' / 'succeeded' / 'canceled' / 'already_credited'.
        new_balance is meaningful only on first 'succeeded' transition; otherwise -1."""
        status = await provider.check_payment(payment_id)
        _logger.info("payment_polled payment_id=%s provider_status=%s", payment_id, status)
        if status == "succeeded":
            await db.mark_payment_status(payment_id, "succeeded")
            credited, balance = await db.credit_pending_payment(payment_id)
            if credited:
                return ("succeeded", balance)
            return ("already_credited", -1)
        if status == "canceled":
            await db.mark_payment_status(payment_id, "canceled")
            return ("canceled", -1)
        return ("pending", -1)

    async def abandon_pending_payment(
        self,
        provider: PaymentProvider,
        payment_id: str,
    ) -> tuple[str, int]:
        """Defensive abandon: re-check provider status before marking canceled.
        If the user already paid, credit them instead of forfeiting the payment.

        YooKassa does not support API-side cancellation of `pending` payments —
        the link stays live for 24h. This re-check protects against the case
        where a user pays externally, then taps Abandon by mistake.

        Returns (final_status, new_balance) — same shape as confirm_pending_payment.
        """
        try:
            status = await provider.check_payment(payment_id)
        except RuntimeError as e:
            _logger.warning(
                "abandon_status_check_failed payment_id=%s err=%s — proceeding with abandon",
                payment_id, e,
            )
            await db.mark_payment_status(payment_id, "canceled")
            _logger.info("payment_abandoned payment_id=%s status=canceled", payment_id)
            return ("canceled", -1)

        if status == "succeeded":
            _logger.info(
                "abandon_recovered_succeeded payment_id=%s — crediting instead of canceling",
                payment_id,
            )
            await db.mark_payment_status(payment_id, "succeeded")
            credited, balance = await db.credit_pending_payment(payment_id)
            if credited:
                return ("succeeded", balance)
            return ("already_credited", -1)

        await db.mark_payment_status(payment_id, "canceled")
        _logger.info("payment_abandoned payment_id=%s status=canceled", payment_id)
        return ("canceled", -1)
