"""Shared constructors for the per-call `usage` dict that every provider
returns inside its `*Result`.
"""


def input_length_usage(units: int) -> dict[str, object]:
    """For providers whose API does not report per-call billing — i.e. the
    response carries neither a usage payload nor a request-ID we can use
    to look it up later. `units` is what the caller self-counted (typically
    `len(text)` for TTS/voice-clone and `len(prompt)` for music).
    """
    return {"mode": "input_length", "units": int(units), "source": "input_length"}


def vendor_usage(units: int, source: str) -> dict[str, object]:
    """For providers whose response carries authoritative billing data
    (usage payload or correlating request-ID). No live caller as of this
    commit — kept defined so a future such provider has a one-line path
    to the same shape.
    """
    return {"mode": "vendor", "units": int(units), "source": source}
