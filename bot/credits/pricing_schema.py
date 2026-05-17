"""Pricing-config schema.

One pydantic v2 discriminated union over `mode`. Validated at startup.
The whole config lives in JSON (`config/pricing.json`); the schema here
is the single source of truth for what that file may contain.

Three provider modes:
    vendor         — vendor returns per-call usage (e.g. ElevenLabs)
    input_length   — we self-meter on len(input) (e.g. OpenAI, Tempolor)
    payment        — payment provider (e.g. YooKassa); no per-call meter

`load(path)` parses, validates, and stamps a 12-char content hash that
is carried with the config and recorded in every transaction's `meta`
column.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class _ProviderBase(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class VendorMeteredProvider(_ProviderBase):
    mode: Literal["vendor"]
    multiplier: Annotated[float, Field(gt=1.0, lt=10.0)]
    pre_deduct_minimum_credits: int = Field(ge=0)
    feature_minimums: dict[str, int] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _minimums_non_negative(self) -> "VendorMeteredProvider":
        for feat, val in self.feature_minimums.items():
            if val < 0:
                raise ValueError(f"feature_minimum {feat}={val} must be >= 0")
        return self


class InputLengthProvider(_ProviderBase):
    mode: Literal["input_length"]
    multiplier: Annotated[float, Field(gt=1.0, lt=10.0)]
    credits_per_input_unit: float = Field(gt=0)
    input_unit: Literal["char", "second"]
    pre_deduct_minimum_credits: int = Field(ge=0)
    feature_minimums: dict[str, int] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _minimums_non_negative(self) -> "InputLengthProvider":
        for feat, val in self.feature_minimums.items():
            if val < 0:
                raise ValueError(f"feature_minimum {feat}={val} must be >= 0")
        return self


class PaymentProvider(_ProviderBase):
    mode: Literal["payment"]
    multiplier: float = 1.0


ProviderConfig = Annotated[
    VendorMeteredProvider | InputLengthProvider | PaymentProvider,
    Field(discriminator="mode"),
]


class PricingConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    version: Literal[1]
    rub_to_credits: int = Field(gt=0)
    providers: dict[str, ProviderConfig]
    max_length: dict[str, int] = Field(default_factory=dict)
    welcome_bonus: int = Field(ge=0, default=0)
    topup_buttons: list[int] = Field(default_factory=lambda: [100, 500, 1000, 5000])

    config_hash: str = ""

    @model_validator(mode="after")
    def _at_least_one_payment_provider(self) -> "PricingConfig":
        if not any(p.mode == "payment" for p in self.providers.values()):
            raise ValueError("at least one provider must have mode='payment'")
        return self

    def minimum_for(self, feature: str, provider_key: str) -> int:
        """Return per-(feature, provider) credit minimum, with fallback to
        the provider's `pre_deduct_minimum_credits`."""
        provider = self.providers[provider_key]
        if provider.mode == "payment":
            raise ValueError(f"payment provider {provider_key!r} has no minimum")
        return provider.feature_minimums.get(
            feature, provider.pre_deduct_minimum_credits
        )

    def credits_for_rub(self, amount_rub: int) -> int:
        """Convert a RUB top-up amount to credits."""
        return amount_rub * self.rub_to_credits


def load(path: Path) -> PricingConfig:
    """Parse JSON, validate, stamp a 12-char content hash."""
    raw_bytes = path.read_bytes()
    data = json.loads(raw_bytes)
    cfg = PricingConfig.model_validate(data)
    digest = hashlib.sha256(raw_bytes).hexdigest()[:12]
    return cfg.model_copy(update={"config_hash": digest})
