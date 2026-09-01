"""Chan's half-Kelly leverage cap as a non-directional risk perspective."""
from __future__ import annotations

import math

from ._common import absent, base, explicitly_observed, first, number, values

ALGORITHM_ID = "chan_half_kelly_cap"
SOURCES = ("Ernest P. Chan — Algorithmic Trading: Winning Strategies and Their Rationale",)
KEYS = (
    "chan_kelly_p_win",
    "chan_kelly_avg_win_loss_ratio",
    "chan_kelly_max_leverage",
    "chan_kelly_fraction",
    "chan_kelly_data_provenance",
)


def evaluate(state):
    found = values(state, *KEYS)
    missing = [key for key in KEYS if first(state, key) is None]
    if not explicitly_observed(first(state, "chan_kelly_data_provenance"), accepted=("observed", "measured", "timestamped")):
        missing.append("chan_kelly_data_provenance")
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, list(dict.fromkeys(missing)))

    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    result["directional_claim"] = False
    probability = number(first(state, "chan_kelly_p_win"))
    win_loss = number(first(state, "chan_kelly_avg_win_loss_ratio"))
    max_leverage = number(first(state, "chan_kelly_max_leverage"))
    fraction = number(first(state, "chan_kelly_fraction"))
    if (
        probability is None or win_loss is None or max_leverage is None or fraction is None
        or not 0.0 <= probability <= 1.0 or win_loss <= 0 or max_leverage <= 0
        or not 0.0 < fraction <= 0.5 or not all(math.isfinite(v) for v in (probability, win_loss, max_leverage, fraction))
    ):
        result["chan_kelly_assessment"] = "INVALID_KELLY_INPUT"
        result["reasons"] = ["probability, win/loss ratio, leverage cap, and Kelly fraction must be finite and bounded"]
        return result
    full = probability - (1.0 - probability) / win_loss
    recommended = min(max_leverage, max(0.0, full * fraction))
    result["chan_full_kelly_leverage"] = full
    result["chan_recommended_leverage"] = recommended
    result["chan_kelly_assessment"] = "POSITIVE_HALF_KELLY_CAP" if recommended > 0 else "NO_POSITIVE_KELLY_EDGE"
    result["view"] = "WAIT"
    result["reasons"] = ["Kelly is used only as a capped non-directional leverage recommendation"]
    return result
