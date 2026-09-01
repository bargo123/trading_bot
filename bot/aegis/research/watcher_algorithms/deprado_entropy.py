"""López de Prado Shannon-entropy context diagnostic."""
from __future__ import annotations

import math
from collections import Counter

from ._common import absent, base, explicitly_observed, first, values
from ._deprado_common import provenance_ok

ALGORITHM_ID = "deprado_entropy"
SOURCES = ("Marcos López de Prado — Advances in Financial Machine Learning",)
KEYS = ("deprado_entropy_symbols", "deprado_entropy_data_provenance")


def _symbols(value):
    if not isinstance(value, (list, tuple)) or isinstance(value, (str, bytes)) or not value:
        return None
    symbols = []
    for item in value:
        if isinstance(item, float) and not math.isfinite(item):
            return None
        if isinstance(item, (list, tuple, dict, set)):
            return None
        try:
            hash(item)
        except TypeError:
            return None
        symbols.append(item)
    return symbols


def evaluate(state):
    symbols = _symbols(first(state, "deprado_entropy_symbols"))
    found = values(state, *KEYS)
    missing = []
    if symbols is None:
        missing.append("deprado_entropy_symbols")
    provenance = first(state, "deprado_entropy_data_provenance")
    if not explicitly_observed(provenance, accepted=("observed", "measured", "replay")) or not provenance_ok(provenance):
        missing.append("deprado_entropy_data_provenance")
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, list(dict.fromkeys(missing)))

    counts = Counter(symbols)
    sample_n = len(symbols)
    entropy = -sum((count / sample_n) * math.log2(count / sample_n) for count in counts.values())
    maximum = math.log2(len(counts)) if len(counts) > 1 else 0.0
    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found], view="WAIT")
    result["directional_claim"] = False
    result["analysis_stage"] = "causal_context"
    result["deprado_shannon_entropy_bits"] = entropy
    result["deprado_entropy_normalized"] = entropy / maximum if maximum else 0.0
    result["deprado_entropy_sample_n"] = sample_n
    result["deprado_entropy_unique_symbols"] = len(counts)
    result["deprado_entropy_symbol_counts"] = [
        {"symbol": str(symbol), "count": count, "probability": count / sample_n}
        for symbol, count in counts.items()
    ]
    result["deprado_entropy_assessment"] = "ENTROPY_MEASURED"
    result["warnings"] = ["entropy measures information content; it is not a directional win probability"]
    return result
