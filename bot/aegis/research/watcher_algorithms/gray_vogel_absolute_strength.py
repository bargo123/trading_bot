"""Gray--Vogel absolute-strength momentum with an explicit capacity check."""
from __future__ import annotations

from ._common import absent, base, first, normalized_status, number, side, values, with_direction


ALGORITHM_ID = "gray_vogel_absolute_strength"
SOURCES = ("Wesley R. Gray and Jack R. Vogel — Quantitative Momentum",)
KEYS = (
    "side",
    "gray_absolute_momentum_return",
    "gray_absolute_winner_cutoff",
    "gray_absolute_loser_cutoff",
    "gray_absolute_cutoff_sample_n",
    "gray_absolute_candidate_count",
    "gray_absolute_portfolio_cap",
    "gray_absolute_data_provenance",
)


def _provenance_ok(value) -> bool:
    label = normalized_status(value)
    return bool(label) and not any(token in label for token in ("synthetic", "fixture", "unknown", "unavailable")) and any(
        token in label for token in ("observed", "measured", "historical")
    )


def evaluate(state):
    found = values(state, *KEYS)
    missing = [key for key in KEYS if first(state, key) is None]
    if not _provenance_ok(first(state, "gray_absolute_data_provenance")):
        missing.append("gray_absolute_data_provenance")
    missing = list(dict.fromkeys(missing))
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, missing)

    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    score = number(first(state, "gray_absolute_momentum_return"))
    winner = number(first(state, "gray_absolute_winner_cutoff"))
    loser = number(first(state, "gray_absolute_loser_cutoff"))
    sample = number(first(state, "gray_absolute_cutoff_sample_n"))
    count = number(first(state, "gray_absolute_candidate_count"))
    cap = number(first(state, "gray_absolute_portfolio_cap"))
    if (
        any(value is None for value in (score, winner, loser, sample, count, cap))
        or winner <= loser
        or sample <= 0.0
        or count < 0.0
        or not count.is_integer()
        or cap <= 0.0
        or not cap.is_integer()
    ):
        result["gray_absolute_assessment"] = "INVALID_ABSOLUTE_INPUT"
        result["reasons"] = ["absolute strength needs finite dynamic cutoffs, a positive historical sample, and integer capacity observations"]
        return result
    result.update({
        "gray_absolute_momentum_return": score,
        "gray_absolute_candidate_count": int(count),
        "gray_absolute_portfolio_cap": int(cap),
    })
    if count > cap:
        result["gray_absolute_assessment"] = "PORTFOLIO_CAPACITY_WARNING"
        result["warnings"] = ["absolute cutoffs can create unstable portfolio sizes; the observed candidate count exceeds the declared capacity"]
        return result
    if score >= winner:
        result["gray_absolute_assessment"] = "ABSOLUTE_WINNER"
        return with_direction(result, state, "BUY", "the observed return exceeds the expanding-sample absolute winner cutoff")
    if score <= loser:
        result["gray_absolute_assessment"] = "ABSOLUTE_LOSER"
        return with_direction(result, state, "SELL", "the observed return is below the expanding-sample absolute loser cutoff")
    result["gray_absolute_assessment"] = "NO_ABSOLUTE_SIGNAL"
    result["reasons"] = ["the observed return is between the dynamic absolute-strength cutoffs"]
    return result
