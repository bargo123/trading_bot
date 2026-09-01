"""Gray--Vogel earnings-momentum alternative (SUE/CAR3) research view."""
from __future__ import annotations

from ._common import absent, base, first, normalized_status, number, side, values, with_direction


ALGORITHM_ID = "gray_vogel_fundamental_momentum"
SOURCES = ("Wesley R. Gray and Jack R. Vogel — Quantitative Momentum",)
KEYS = (
    "side",
    "gray_fundamental_signal",
    "gray_fundamental_score",
    "gray_fundamental_long_cutoff",
    "gray_fundamental_short_cutoff",
    "gray_fundamental_sample_n",
    "gray_fundamental_volatility_scale",
    "gray_fundamental_data_provenance",
)


def _provenance_ok(value) -> bool:
    label = normalized_status(value)
    return bool(label) and not any(token in label for token in ("synthetic", "fixture", "unknown", "unavailable")) and any(
        token in label for token in ("observed", "measured", "historical")
    )


def evaluate(state):
    found = values(state, *KEYS)
    missing = [key for key in KEYS if first(state, key) is None]
    if not _provenance_ok(first(state, "gray_fundamental_data_provenance")):
        missing.append("gray_fundamental_data_provenance")
    missing = list(dict.fromkeys(missing))
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, missing)

    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    signal = normalized_status(first(state, "gray_fundamental_signal")).upper()
    score = number(first(state, "gray_fundamental_score"))
    long_cutoff = number(first(state, "gray_fundamental_long_cutoff"))
    short_cutoff = number(first(state, "gray_fundamental_short_cutoff"))
    sample = number(first(state, "gray_fundamental_sample_n"))
    scale = number(first(state, "gray_fundamental_volatility_scale"))
    if (
        signal not in {"SUE", "CAR3"}
        or any(value is None for value in (score, long_cutoff, short_cutoff, sample, scale))
        or not 0.0 <= score <= 1.0
        or not 0.0 <= short_cutoff < long_cutoff <= 1.0
        or sample <= 0.0
        or scale <= 0.0
    ):
        result["gray_fundamental_assessment"] = "INVALID_FUNDAMENTAL_INPUT"
        result["reasons"] = ["earnings-momentum research needs an explicit SUE/CAR3 signal, bounded percentile cutoffs, sample, and scale"]
        return result
    result["gray_fundamental_signal"] = signal
    if score >= long_cutoff:
        result["gray_fundamental_assessment"] = "FUNDAMENTAL_MOMENTUM_WINNER"
        return with_direction(result, state, "BUY", "the observed earnings-momentum score exceeds the supplied long cutoff")
    if score <= short_cutoff:
        result["gray_fundamental_assessment"] = "FUNDAMENTAL_MOMENTUM_LOSER"
        return with_direction(result, state, "SELL", "the observed earnings-momentum score is below the supplied short cutoff")
    result["gray_fundamental_assessment"] = "NO_FUNDAMENTAL_MOMENTUM_BUCKET"
    result["reasons"] = ["the observed earnings-momentum score is between the supplied cutoffs"]
    return result
