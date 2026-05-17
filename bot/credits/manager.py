"""CreditManager — usage-based pricing.

Two metering modes per provider, declared in `config/pricing.json` and
validated by `bot.credits.pricing_schema.PricingConfig`:

    vendor         — `charge = ceil(vendor_units × multiplier)`
                     (ElevenLabs via History endpoint)
    input_length   — `charge = ceil(input × credits_per_input_unit × multiplier)`
                     (OpenAI, Tempolor)

Flow:
    1. `pre_deduct(user, feature, provider)` — atomically deduct the
       per-(feature, provider) minimum, return a frozen `CallContext`.
    2. provider.generate() — returns `result.usage` = {"mode","units","source"}.
    3. Either `reconcile(ctx, usage)` on success, or `refund_minimum(ctx)`
       on API failure. Both write a paired transaction row using the same
       `call_id` as the pre_deduct.

`source == "fallback_min"` means the vendor's per-call meter (e.g.
ElevenLabs History) was unreachable; `reconcile` bills the minimum and
neither charges overage nor refunds.
"""

from __future__ import annotations

import json
import logging
import math
import uuid
from dataclasses import dataclass
from typing import Literal

from bot.credits.pricing_schema import PricingConfig
from bot.db import credits as db
from bot.providers.payment.base_payment import PaymentProvider as PaymentProviderBase

_logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CallContext:
    """Snapshot of the rate used for one (pre_deduct, reconcile) pair.

    Frozen so a config change between pre_deduct and reconcile cannot
    silently alter either side of the paired charge.
    """
    call_id: str
    user_id: int
    feature: str
    provider_key: str
    mode: Literal["vendor", "input_length", "payment"]
    multiplier: float
    credits_per_input_unit: float | None
    minimum: int
    config_hash: str


@dataclass(frozen=True)
class ReconcileResult:
    minimum_charged: int
    actual_credits: int
    delta: int           # positive = overage; negative = refund; zero = no-op
    new_balance: int
    call_id: str


def _compute_charge(
    mode: str,
    multiplier: float,
    units: int,
    credits_per_input_unit: float | None,
) -> int:
    """Single `ceil` at the integer boundary; exact integer math thereafter."""
    if units <= 0:
        raise ValueError(f"units must be positive, got {units}")
    if mode == "vendor":
        return math.ceil(units * multiplier)
    if mode == "input_length":
        if credits_per_input_unit is None:
            raise ValueError("input_length mode requires credits_per_input_unit")
        return math.ceil(units * credits_per_input_unit * multiplier)
    raise ValueError(f"unknown mode {mode!r}")


def _meta_json(ctx: CallContext, usage: dict | None = None) -> str:
    payload = {
        "feature": ctx.feature,
        "provider": ctx.provider_key,
        "mode": ctx.mode,
        "multiplier": ctx.multiplier,
        "credits_per_input_unit": ctx.credits_per_input_unit,
        "minimum": ctx.minimum,
        "config_hash": ctx.config_hash,
    }
    if usage is not None:
        payload["usage"] = usage
    return json.dumps(payload, separators=(",", ":"), sort_keys=True)


class CreditManager:
    def __init__(self, cfg: PricingConfig) -> None:
        self._cfg = cfg

    @property
    def cfg(self) -> PricingConfig:
        """Read-only access to the pricing config (used by handlers for
        max_length lookups, etc.)."""
        return self._cfg

    # ── User account housekeeping ────────────────────────────────────

    async def ensure_user(self, user_id: int) -> None:
        await db.create_user(user_id, self._cfg.welcome_bonus, "welcome")

    async def get_balance(self, user_id: int) -> int:
        await self.ensure_user(user_id)
        bal = await db.get_balance(user_id)
        return bal if bal is not None else 0

    # ── Usage-based generation path ───────────────────────────────────

    async def pre_deduct(
        self, user_id: int, feature: str, provider_key: str,
    ) -> tuple[bool, CallContext | None]:
        """Deduct the per-(feature, provider) minimum atomically.

        Returns (False, None) if the user has insufficient balance — caller
        must abort before any external API call.
        """
        provider = self._cfg.providers[provider_key]
        if provider.mode == "payment":
            raise ValueError(f"pre_deduct called for payment provider {provider_key!r}")
        minimum = self._cfg.minimum_for(feature, provider_key)
        ctx = CallContext(
            call_id=uuid.uuid4().hex,
            user_id=user_id,
            feature=feature,
            provider_key=provider_key,
            mode=provider.mode,
            multiplier=provider.multiplier,
            credits_per_input_unit=getattr(provider, "credits_per_input_unit", None),
            minimum=minimum,
            config_hash=self._cfg.config_hash,
        )
        meta = _meta_json(ctx)
        ok = await db.check_and_deduct_credits(
            user_id, minimum,
            reason=f"pre:{ctx.call_id}",
            meta=meta,
        )
        if not ok:
            balance = await db.get_balance(user_id) or 0
            _logger.info(
                "pricing_pre_deduct_denied user_id=%s feature=%s provider=%s "
                "minimum=%s balance=%s call_id=%s",
                user_id, feature, provider_key, minimum, balance, ctx.call_id,
            )
            return False, None
        new_balance = await db.get_balance(user_id) or 0
        _logger.info(
            "pricing_pre_deduct_ok user_id=%s feature=%s provider=%s "
            "minimum=%s call_id=%s new_balance=%s",
            user_id, feature, provider_key, minimum, ctx.call_id, new_balance,
        )
        return True, ctx

    async def refund_minimum(self, ctx: CallContext) -> int:
        """Refund the pre-deducted minimum on provider failure.
        Returns new balance."""
        new_balance = await db.add_credits(
            ctx.user_id, ctx.minimum,
            reason=f"refund:{ctx.call_id}",
            meta=_meta_json(ctx),
        )
        _logger.info(
            "pricing_refund_min user_id=%s feature=%s provider=%s "
            "amount=%s new_balance=%s call_id=%s",
            ctx.user_id, ctx.feature, ctx.provider_key,
            ctx.minimum, new_balance, ctx.call_id,
        )
        return new_balance

    async def reconcile(self, ctx: CallContext, usage: dict) -> ReconcileResult:
        """Settle the difference between the pre-deducted minimum and
        the actual cost computed from `usage`.

        `usage` shape: {"mode": str, "units": int, "source": str}.
        `source == "fallback_min"` → bill the minimum (no overage, no refund).
        """
        if usage.get("source") == "fallback_min":
            _logger.warning(
                "pricing_vendor_query_failed user_id=%s provider=%s "
                "fallback=fallback_min call_id=%s",
                ctx.user_id, ctx.provider_key, ctx.call_id,
            )
            bal = await db.get_balance(ctx.user_id) or 0
            return ReconcileResult(
                minimum_charged=ctx.minimum,
                actual_credits=ctx.minimum,
                delta=0,
                new_balance=bal,
                call_id=ctx.call_id,
            )

        actual = _compute_charge(
            ctx.mode, ctx.multiplier, usage["units"], ctx.credits_per_input_unit,
        )
        delta = actual - ctx.minimum

        if delta == 0:
            bal = await db.get_balance(ctx.user_id) or 0
            self._log_reconciled(ctx, usage, actual, 0, bal)
            return ReconcileResult(ctx.minimum, actual, 0, bal, ctx.call_id)

        reason_prefix = "reconcile_overage" if delta > 0 else "reconcile_refund"
        new_balance = await db.add_credits(
            ctx.user_id, -delta,
            reason=f"{reason_prefix}:{ctx.call_id}",
            meta=_meta_json(ctx, usage),
        )
        self._log_reconciled(ctx, usage, actual, delta, new_balance)
        return ReconcileResult(ctx.minimum, actual, delta, new_balance, ctx.call_id)

    def _log_reconciled(
        self, ctx: CallContext, usage: dict, actual: int, delta: int, new_balance: int,
    ) -> None:
        _logger.info(
            "pricing_reconciled user_id=%s feature=%s provider=%s mode=%s "
            "units=%s minimum=%s actual=%s delta=%s new_balance=%s "
            "source=%s call_id=%s",
            ctx.user_id, ctx.feature, ctx.provider_key, ctx.mode,
            usage.get("units"), ctx.minimum, actual, delta, new_balance,
            usage.get("source"), ctx.call_id,
        )

    # ── Payment flow (unchanged in shape, uses PricingConfig for FX) ──

    async def create_pending_payment(
        self,
        user_id: int,
        provider_key: str,
        provider: PaymentProviderBase,
        amount_rub: int,
        idempotency_key: str | None = None,
    ) -> tuple[str, str]:
        credits = self._cfg.credits_for_rub(amount_rub)
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
        self, provider: PaymentProviderBase, payment_id: str,
    ) -> tuple[str, int]:
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
        self, provider: PaymentProviderBase, payment_id: str,
    ) -> tuple[str, int]:
        try:
            status = await provider.check_payment(payment_id)
        except RuntimeError as e:
            _logger.warning(
                "abandon_status_check_failed payment_id=%s err=%s — proceeding with abandon",
                payment_id, e,
            )
            await db.mark_payment_status(payment_id, "canceled")
            return ("canceled", -1)

        if status == "succeeded":
            await db.mark_payment_status(payment_id, "succeeded")
            credited, balance = await db.credit_pending_payment(payment_id)
            if credited:
                return ("succeeded", balance)
            return ("already_credited", -1)

        await db.mark_payment_status(payment_id, "canceled")
        return ("canceled", -1)
