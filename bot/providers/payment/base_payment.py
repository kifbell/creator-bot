"""Abstract base class for payment providers."""

from abc import ABC, abstractmethod


class PaymentProvider(ABC):
    @abstractmethod
    async def create_payment(
        self,
        user_id: int,
        amount_rub: int,
        credits: int,
        idempotency_key: str | None = None,
    ) -> tuple[str, str]:
        """Create a payment.

        Returns (payment_id, payment_url).
        - Mock: payment_url is empty string (instant-succeeded provider).
        - YooKassa: payment_url is the redirect URL the user opens to pay.

        ``idempotency_key`` (YooKassa-only): if set, the SDK uses it as the
        ``Idempotence-Key`` header. If a previous request with the same key
        succeeded server-side, YooKassa returns the SAME payment instead of
        creating a duplicate. Callers should reuse the same key on retry
        after transient failures (network errors, timeouts) to prevent
        double-charges. If ``None``, the provider generates a fresh key.
        """

    @abstractmethod
    async def check_payment(self, payment_id: str) -> str:
        """Check payment status.

        Returns one of: 'pending' | 'succeeded' | 'canceled'.
        """
