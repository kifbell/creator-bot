"""YooKassa payment provider — wraps the synchronous yookassa SDK in asyncio.to_thread.

NOTE: yookassa SDK uses module-level Configuration (Configuration.account_id /
Configuration.secret_key). Only one YooKassaPaymentProvider should exist per
process. Configuration is set in bot/main.py at startup.
"""

import asyncio
import logging
import uuid

import requests
from yookassa import Payment
from yookassa.domain.exceptions import (
    ApiError,
    BadRequestError,
    NotFoundError,
    UnauthorizedError,
)

from bot.providers.payment.base_payment import PaymentProvider

logger = logging.getLogger(__name__)

# Placeholder return URL — we use polling, so this URL is never actually visited
# by the bot. YooKassa redirects the user here after payment, but the bot
# confirms via the user-tapped "Check payment" button.
_RETURN_URL = "https://example.com/payment-complete"


def _format_amount(amount_rub: int) -> str:
    """Convert int RUB to YooKassa string format (e.g. 100 -> '100.00')."""
    if amount_rub <= 0:
        raise ValueError(f"Amount must be positive, got {amount_rub}")
    return f"{amount_rub}.00"


class YooKassaPaymentProvider(PaymentProvider):
    async def create_payment(
        self,
        user_id: int,
        amount_rub: int,
        credits: int,
        idempotency_key: str | None = None,
    ) -> tuple[str, str]:
        # Reuse caller-provided key on retry — prevents double-charge if
        # the previous request reached YooKassa but the response was lost.
        idempotence_key = idempotency_key or uuid.uuid4().hex
        amount_str = _format_amount(amount_rub)

        def _create():
            payment = Payment.create(
                {
                    "amount": {"value": amount_str, "currency": "RUB"},
                    "confirmation": {"type": "redirect", "return_url": _RETURN_URL},
                    "capture": True,
                    "description": f"Top-up for user {user_id}: {credits} credits",
                    "metadata": {
                        "user_id": str(user_id),
                        "credits": str(credits),
                    },
                },
                idempotence_key,
            )
            return payment.id, payment.confirmation.confirmation_url

        try:
            payment_id, url = await asyncio.to_thread(_create)
            logger.info(
                "yookassa_payment_created user_id=%s amount_rub=%s payment_id=%s",
                user_id, amount_rub, payment_id,
            )
            return payment_id, url
        except UnauthorizedError:
            logger.error(
                "yookassa_auth_failed user_id=%s — check YOOKASSA_SHOP_ID/SECRET_KEY",
                user_id, exc_info=True,
            )
            raise RuntimeError("Payment provider misconfigured")
        except BadRequestError as e:
            logger.error(
                "yookassa_bad_request user_id=%s amount_rub=%s err=%s",
                user_id, amount_rub, e, exc_info=True,
            )
            raise RuntimeError(f"Invalid payment request: {e}")
        except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as e:
            logger.warning(
                "yookassa_network_error_create user_id=%s amount_rub=%s err=%s",
                user_id, amount_rub, e,
            )
            raise RuntimeError("Payment service unreachable — try again")
        except ApiError as e:
            logger.error(
                "yookassa_api_error_create user_id=%s amount_rub=%s err=%s",
                user_id, amount_rub, e, exc_info=True,
            )
            raise RuntimeError(f"Payment service error: {e}")

    async def check_payment(self, payment_id: str) -> str:
        def _find():
            return Payment.find_one(payment_id).status

        try:
            status = await asyncio.to_thread(_find)
        except NotFoundError:
            logger.warning("yookassa_payment_not_found payment_id=%s", payment_id)
            return "canceled"
        except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as e:
            logger.warning(
                "yookassa_network_error_check payment_id=%s err=%s",
                payment_id, e,
            )
            raise RuntimeError("Payment service unreachable — try again")
        except ApiError as e:
            logger.error(
                "yookassa_api_error_check payment_id=%s err=%s",
                payment_id, e, exc_info=True,
            )
            raise RuntimeError(f"Payment service error: {e}")

        # Map YooKassa statuses to our 3-value enum.
        # waiting_for_capture only appears when capture=False; defensive map.
        if status in ("pending", "waiting_for_capture"):
            return "pending"
        if status == "succeeded":
            return "succeeded"
        if status == "canceled":
            return "canceled"
        logger.warning(f"Unknown YooKassa status '{status}' for {payment_id}, treating as pending")
        return "pending"
