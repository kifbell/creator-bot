"""Tests for bot.credits.manager — pre_deduct / reconcile / refund_minimum.

Arithmetic tests are pure (no I/O). Integration tests use monkeypatch
to substitute the db layer with simple in-memory fakes so the manager
can be exercised without touching a real SQLite database.
"""

import os

import pytest

# Set BOT_ENV before importing bot modules
os.environ.setdefault("BOT_ENV", "test")
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "stub")

from bot.credits.manager import CreditManager, _compute_charge
from bot.credits.pricing_schema import PricingConfig


# ─── _compute_charge: pure arithmetic ─────────────────────────────────


def test_compute_charge_vendor() -> None:
    # 1000 vendor chars × 2.0 = 2000
    assert _compute_charge("vendor", 2.0, 1000, None) == 2000


def test_compute_charge_input_length() -> None:
    # 100 chars × 0.05 × 2.0 = 10.0 → ceil → 10
    assert _compute_charge("input_length", 2.0, 100, 0.05) == 10


def test_compute_charge_input_length_ceils_partial() -> None:
    # 7 chars × 0.05 × 2.0 = 0.7 → ceil → 1
    assert _compute_charge("input_length", 2.0, 7, 0.05) == 1


def test_compute_charge_zero_units_raises() -> None:
    with pytest.raises(ValueError):
        _compute_charge("vendor", 2.0, 0, None)


def test_compute_charge_negative_units_raises() -> None:
    with pytest.raises(ValueError):
        _compute_charge("vendor", 2.0, -10, None)


def test_compute_charge_input_length_missing_rate_raises() -> None:
    with pytest.raises(ValueError):
        _compute_charge("input_length", 2.0, 100, None)


def test_compute_charge_unknown_mode_raises() -> None:
    with pytest.raises(ValueError):
        _compute_charge("magic", 2.0, 100, 0.05)


# ─── Integration with monkeypatched db ────────────────────────────────


@pytest.fixture
def cfg() -> PricingConfig:
    return PricingConfig.model_validate({
        "version": 1,
        "rub_to_credits": 10,
        "providers": {
            "elevenlabs": {
                "mode": "vendor",
                "multiplier": 2.0,
                "pre_deduct_minimum_credits": 50,
                "feature_minimums": {"speak": 50},
            },
            "openai": {
                "mode": "input_length",
                "multiplier": 2.0,
                "credits_per_input_unit": 0.05,
                "input_unit": "char",
                "pre_deduct_minimum_credits": 5,
                "feature_minimums": {"speak": 5},
            },
            "yookassa": {
                "mode": "payment",
                "multiplier": 1.0,
            },
        },
    })


class FakeDB:
    """Minimal in-memory substitute for bot.db.credits used in unit tests."""
    def __init__(self, starting_balance: int = 100) -> None:
        self.balance = starting_balance
        self.transactions: list[dict] = []

    async def check_and_deduct_credits(
        self, user_id: int, amount: int, reason: str, meta: str | None = None,
    ) -> bool:
        if self.balance < amount:
            return False
        self.balance -= amount
        self.transactions.append({
            "user_id": user_id, "delta": -amount, "reason": reason, "meta": meta,
        })
        return True

    async def add_credits(
        self, user_id: int, delta: int, reason: str, meta: str | None = None,
    ) -> int:
        self.balance += delta
        self.transactions.append({
            "user_id": user_id, "delta": delta, "reason": reason, "meta": meta,
        })
        return self.balance

    async def get_balance(self, user_id: int) -> int:
        return self.balance


@pytest.fixture
def fake_db(monkeypatch) -> FakeDB:
    db = FakeDB(starting_balance=200)
    from bot.db import credits as db_credits
    monkeypatch.setattr(db_credits, "check_and_deduct_credits", db.check_and_deduct_credits)
    monkeypatch.setattr(db_credits, "add_credits", db.add_credits)
    monkeypatch.setattr(db_credits, "get_balance", db.get_balance)
    return db


@pytest.mark.asyncio
async def test_pre_deduct_writes_pre_row_with_call_id(cfg: PricingConfig, fake_db: FakeDB) -> None:
    cm = CreditManager(cfg)
    ok, ctx = await cm.pre_deduct(user_id=42, feature="speak", provider_key="elevenlabs")
    assert ok is True
    assert ctx is not None
    assert ctx.feature == "speak"
    assert ctx.provider_key == "elevenlabs"
    assert ctx.mode == "vendor"
    assert ctx.minimum == 50
    assert fake_db.balance == 150  # 200 - 50
    assert len(fake_db.transactions) == 1
    assert fake_db.transactions[0]["reason"] == f"pre:{ctx.call_id}"
    assert fake_db.transactions[0]["delta"] == -50


@pytest.mark.asyncio
async def test_pre_deduct_insufficient_returns_false(cfg: PricingConfig, monkeypatch) -> None:
    db = FakeDB(starting_balance=10)  # less than 50 minimum
    from bot.db import credits as db_credits
    monkeypatch.setattr(db_credits, "check_and_deduct_credits", db.check_and_deduct_credits)
    monkeypatch.setattr(db_credits, "get_balance", db.get_balance)
    cm = CreditManager(cfg)
    ok, ctx = await cm.pre_deduct(user_id=42, feature="speak", provider_key="elevenlabs")
    assert ok is False
    assert ctx is None
    assert db.balance == 10  # untouched
    assert len(db.transactions) == 0


@pytest.mark.asyncio
async def test_pre_deduct_rejects_payment_provider(cfg: PricingConfig, fake_db: FakeDB) -> None:
    cm = CreditManager(cfg)
    with pytest.raises(ValueError):
        await cm.pre_deduct(user_id=42, feature="speak", provider_key="yookassa")


@pytest.mark.asyncio
async def test_reconcile_overage_writes_negative_delta(cfg: PricingConfig, fake_db: FakeDB) -> None:
    cm = CreditManager(cfg)
    _, ctx = await cm.pre_deduct(user_id=42, feature="speak", provider_key="elevenlabs")
    assert ctx is not None
    # Vendor reports 100 chars × 2.0 multiplier = 200 actual; minimum was 50; overage 150
    usage = {"mode": "vendor", "units": 100, "source": "vendor_history"}
    settle = await cm.reconcile(ctx, usage)
    assert settle.actual_credits == 200
    assert settle.minimum_charged == 50
    assert settle.delta == 150
    assert fake_db.balance == 0  # 200 - 50 - 150
    assert len(fake_db.transactions) == 2
    assert fake_db.transactions[1]["reason"].startswith("reconcile_overage:")


@pytest.mark.asyncio
async def test_reconcile_refund_writes_positive_delta(cfg: PricingConfig, fake_db: FakeDB) -> None:
    cm = CreditManager(cfg)
    _, ctx = await cm.pre_deduct(user_id=42, feature="speak", provider_key="elevenlabs")
    assert ctx is not None
    # Vendor reports 10 chars × 2.0 = 20 actual; minimum was 50; refund 30
    usage = {"mode": "vendor", "units": 10, "source": "vendor_history"}
    settle = await cm.reconcile(ctx, usage)
    assert settle.actual_credits == 20
    assert settle.delta == -30
    assert fake_db.balance == 180  # 200 - 50 + 30
    assert fake_db.transactions[1]["reason"].startswith("reconcile_refund:")


@pytest.mark.asyncio
async def test_reconcile_fallback_min_no_extra_row(cfg: PricingConfig, fake_db: FakeDB) -> None:
    cm = CreditManager(cfg)
    _, ctx = await cm.pre_deduct(user_id=42, feature="speak", provider_key="elevenlabs")
    assert ctx is not None
    usage = {"mode": "vendor", "units": 0, "source": "fallback_min"}
    settle = await cm.reconcile(ctx, usage)
    # billed minimum, no overage, no refund — single pre-deduct row only
    assert settle.actual_credits == 50
    assert settle.delta == 0
    assert len(fake_db.transactions) == 1


@pytest.mark.asyncio
async def test_reconcile_zero_delta_no_extra_row(cfg: PricingConfig, fake_db: FakeDB) -> None:
    cm = CreditManager(cfg)
    _, ctx = await cm.pre_deduct(user_id=42, feature="speak", provider_key="elevenlabs")
    assert ctx is not None
    # Vendor reports 25 chars × 2.0 = 50 actual == minimum
    usage = {"mode": "vendor", "units": 25, "source": "vendor_history"}
    settle = await cm.reconcile(ctx, usage)
    assert settle.delta == 0
    assert len(fake_db.transactions) == 1


@pytest.mark.asyncio
async def test_refund_minimum_returns_balance(cfg: PricingConfig, fake_db: FakeDB) -> None:
    cm = CreditManager(cfg)
    _, ctx = await cm.pre_deduct(user_id=42, feature="speak", provider_key="elevenlabs")
    assert ctx is not None
    new_balance = await cm.refund_minimum(ctx)
    assert new_balance == 200  # back to starting
    assert fake_db.transactions[-1]["reason"].startswith("refund:")
