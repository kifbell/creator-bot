"""Abstract base class for payment providers."""

from abc import ABC, abstractmethod


class PaymentProvider(ABC):
    @abstractmethod
    async def process(self, user_id: int, amount: int) -> int:
        """Validate and process payment. Returns credits to add."""
