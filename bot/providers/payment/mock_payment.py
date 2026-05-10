"""Mock payment provider — instantly returns 'succeeded' for testing."""

import uuid

from bot.providers.payment.base_payment import PaymentProvider


class MockPaymentProvider(PaymentProvider):
    """Returns instant-succeeded payments. No real billing.

    Useful for testing the credit flow without hitting YooKassa.
    """

    async def create_payment(
        self,
        user_id: int,
        amount_rub: int,
        credits: int,
        idempotency_key: str | None = None,
    ) -> tuple[str, str]:
        if amount_rub <= 0 or credits <= 0:
            raise ValueError("Amount and credits must be positive")
        # idempotency_key is ignored — Mock has no remote state to deduplicate against.
        # Random payment_id; empty URL signals "no payment needed, just check".
        payment_id = f"mock_{uuid.uuid4().hex}"
        return (payment_id, "")

    async def check_payment(self, payment_id: str) -> str:
        # Mock always succeeds the first time the user checks.
        return "succeeded"
