"""Constructors for the per-call `usage` dict returned by every provider's `*Result`."""


def input_length_usage(units: int) -> dict[str, object]:
    """Usage shape for providers that report no per-call billing.

    `units` is what the caller self-counted (typically `len(text)` for
    TTS/voice-clone and `len(prompt)` for music).
    """
    return {"mode": "input_length", "units": int(units), "source": "input_length"}


def vendor_usage(units: int, source: str) -> dict[str, object]:
    """Usage shape for providers whose response carries authoritative billing data."""
    return {"mode": "vendor", "units": int(units), "source": source}
