"""CreditManager — high-level credit operations using the DB layer."""

from bot.credits.costs import COSTS, WELCOME_BONUS
from bot.db import credits as db
from bot.providers.payment.base_payment import PaymentProvider


class CreditManager:
    def __init__(self, payment_provider: PaymentProvider) -> None:
        self._payment = payment_provider

    async def ensure_user(self, user_id: int) -> None:
        """Create user row with WELCOME_BONUS if this is their first interaction."""
        balance = await db.get_balance(user_id)
        if balance is None:
            await db.create_user(user_id, WELCOME_BONUS, "welcome")

    async def get_balance(self, user_id: int) -> int:
        await self.ensure_user(user_id)
        return await db.get_balance(user_id)

    async def check_and_deduct(self, user_id: int, feature: str) -> bool:
        """Deduct COSTS[feature] if balance is sufficient. Returns False if not enough credits."""
        cost = COSTS[feature]
        balance = await db.get_balance(user_id)
        if balance is None or balance < cost:
            return False
        await db.deduct_credits(user_id, cost, feature)
        return True

    async def top_up(self, user_id: int, amount: int) -> tuple[int, int]:
        """Process payment and credit account. Returns (credits_added, new_balance)."""
        credits = await self._payment.process(user_id, amount)
        new_balance = await db.add_credits(user_id, credits, "topup")
        return credits, new_balance
