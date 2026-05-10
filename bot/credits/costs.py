"""Credit costs and top-up pricing constants."""

COSTS: dict[str, int] = {
    "speak":     10,
    "voiceover": 50,
    "song":      30,
}

WELCOME_BONUS = 0

# Pricing for top-ups: 1 RUB = 10 credits → 100 RUB = 1000 credits (~ 1 USD).
RUB_TO_CREDITS = 10

# Predefined RUB amounts shown as buttons in the /topup conversation.
TOPUP_BUTTONS = [100, 500, 1000, 5000]


def credits_for_rub(amount_rub: int) -> int:
    """Convert a RUB top-up amount to credits."""
    return amount_rub * RUB_TO_CREDITS
