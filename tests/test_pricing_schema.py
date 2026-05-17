"""Tests for bot.credits.pricing_schema — validation + hash stability."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from bot.credits.pricing_schema import PricingConfig, load


def _base_config() -> dict:
    return {
        "version": 1,
        "rub_to_credits": 10,
        "providers": {
            "elevenlabs": {
                "mode": "vendor",
                "multiplier": 2.0,
                "pre_deduct_minimum_credits": 50,
            },
            "yookassa": {
                "mode": "payment",
                "multiplier": 1.0,
            },
        },
    }


def test_loads_example_config_with_stable_hash(tmp_path: Path) -> None:
    """Round-trip the bundled config and ensure hash is stable."""
    cfg_path = Path(__file__).parent.parent / "config" / "pricing.json"
    if not cfg_path.exists():
        pytest.skip("config/pricing.json not present")
    cfg = load(cfg_path)
    assert cfg.version == 1
    assert cfg.config_hash != ""
    assert len(cfg.config_hash) == 12
    cfg2 = load(cfg_path)
    assert cfg.config_hash == cfg2.config_hash


def test_invalid_multiplier_below_one_rejects() -> None:
    data = _base_config()
    data["providers"]["elevenlabs"]["multiplier"] = 0.5
    with pytest.raises(ValidationError):
        PricingConfig.model_validate(data)


def test_invalid_multiplier_above_ten_rejects() -> None:
    data = _base_config()
    data["providers"]["elevenlabs"]["multiplier"] = 11.0
    with pytest.raises(ValidationError):
        PricingConfig.model_validate(data)


def test_input_length_without_rate_rejects() -> None:
    data = _base_config()
    data["providers"]["openai"] = {
        "mode": "input_length",
        "multiplier": 2.0,
        # missing credits_per_input_unit
        "input_unit": "char",
        "pre_deduct_minimum_credits": 5,
    }
    with pytest.raises(ValidationError):
        PricingConfig.model_validate(data)


def test_input_length_negative_rate_rejects() -> None:
    data = _base_config()
    data["providers"]["openai"] = {
        "mode": "input_length",
        "multiplier": 2.0,
        "credits_per_input_unit": -1.0,
        "input_unit": "char",
        "pre_deduct_minimum_credits": 5,
    }
    with pytest.raises(ValidationError):
        PricingConfig.model_validate(data)


def test_at_least_one_payment_provider_required() -> None:
    data = _base_config()
    del data["providers"]["yookassa"]
    with pytest.raises(ValidationError):
        PricingConfig.model_validate(data)


def test_vendor_provider_extra_field_forbidden() -> None:
    data = _base_config()
    data["providers"]["elevenlabs"]["unknown_field"] = "x"
    with pytest.raises(ValidationError):
        PricingConfig.model_validate(data)


def test_minimum_for_falls_back_to_default() -> None:
    cfg = PricingConfig.model_validate(_base_config())
    assert cfg.minimum_for("speak", "elevenlabs") == 50


def test_minimum_for_uses_feature_specific() -> None:
    data = _base_config()
    data["providers"]["elevenlabs"]["feature_minimums"] = {"speak": 81, "voiceover": 108}
    cfg = PricingConfig.model_validate(data)
    assert cfg.minimum_for("speak", "elevenlabs") == 81
    assert cfg.minimum_for("voiceover", "elevenlabs") == 108
    assert cfg.minimum_for("song", "elevenlabs") == 50


def test_minimum_for_payment_provider_raises() -> None:
    cfg = PricingConfig.model_validate(_base_config())
    with pytest.raises(ValueError):
        cfg.minimum_for("speak", "yookassa")


def test_credits_for_rub() -> None:
    cfg = PricingConfig.model_validate(_base_config())
    assert cfg.credits_for_rub(100) == 1000
    assert cfg.credits_for_rub(0) == 0


def test_unknown_input_unit_rejected() -> None:
    data = _base_config()
    data["providers"]["openai"] = {
        "mode": "input_length",
        "multiplier": 2.0,
        "credits_per_input_unit": 0.05,
        "input_unit": "tokens",  # not in Literal["char", "second"]
        "pre_deduct_minimum_credits": 5,
    }
    with pytest.raises(ValidationError):
        PricingConfig.model_validate(data)


def test_unknown_mode_rejected() -> None:
    data = _base_config()
    data["providers"]["elevenlabs"]["mode"] = "magic"
    with pytest.raises(ValidationError):
        PricingConfig.model_validate(data)
