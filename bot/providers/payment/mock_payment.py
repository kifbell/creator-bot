"""Mock payment provider — multiplies amount by TOPUP_MULTIPLIER."""

from bot.credits.costs import TOPUP_MULTIPLIER
from bot.providers.payment.base_payment import PaymentProvider


class MockPaymentProvider(PaymentProvider):
    async def process(self, user_id: int, amount: int) -> int:
        if amount <= 0:
            raise ValueError("Amount must be positive")
        return amount * TOPUP_MULTIPLIER
