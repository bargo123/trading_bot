"""Immutable, pre-registered Firehose mechanism contracts.

These specifications describe research hypotheses only.  They do not grant a
runtime permission; replay and promotion still require executable evidence.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Mapping


@dataclass(frozen=True)
class FirehoseMechanismSpec:
    mechanism_id: str
    source_kind: str
    source_refs: tuple[str, ...]
    passage_hashes: tuple[str, ...]
    rule_fingerprint: str
    entry_rule: Mapping[str, object]
    exit_rule: Mapping[str, object]
    falsification: str


def _source_hash(ref: str, excerpt: str) -> str:
    return hashlib.sha256(f"{ref}\n{excerpt}".encode("utf-8")).hexdigest()


def built_in_mechanisms() -> dict[str, FirehoseMechanismSpec]:
    """Return the small, explicit research registry for the first two studies."""
    ponsi_ref = "docs/trading/NEW_BOOKS_PONSI_DAMIR_DRAKOLN_THOMAS_AFSHARI_WINDSOR.md:16-24"
    ponsi_excerpt = "Match technique to regime; multi-timeframe structure + risk first; squeeze break is a testable setup."
    chan_ref = "docs/trading/NEW_BOOKS_KAUFMAN_VOLMAN_JOHNSON_CHAN.md:17-21"
    chan_excerpt = "Chan mean-reversion Bollinger prototypes require costs and are not trade-as-is."
    specs = (
        FirehoseMechanismSpec(
            mechanism_id="failed_breakout_fade_v1",
            source_kind="BOOK_DERIVED",
            source_refs=(ponsi_ref,),
            passage_hashes=(_source_hash(ponsi_ref, ponsi_excerpt),),
            rule_fingerprint=_source_hash("failed_breakout_fade_v1", "M1 pierce, close back inside M15 range edge"),
            entry_rule={"trigger": "completed_m1_failed_break_of_confirmed_m15_edge", "side": "fade"},
            exit_rule={"target": "range_mid_or_opposite_edge", "stop": "failed_break_extreme_plus_atr_buffer"},
            falsification="net OOS expectancy remains non-positive after measured spread, slippage, and commission",
        ),
        FirehoseMechanismSpec(
            mechanism_id="bollinger_midpoint_reversion_v1",
            source_kind="BOOK_DERIVED",
            source_refs=(chan_ref,),
            passage_hashes=(_source_hash(chan_ref, chan_excerpt),),
            rule_fingerprint=_source_hash("bollinger_midpoint_reversion_v1", "completed bar outside band, target midpoint"),
            entry_rule={"trigger": "completed_bar_outside_bollinger_band", "side": "fade"},
            exit_rule={"target": "bollinger_midpoint", "stop": "outside_band_atr_buffer"},
            falsification="costed walk-forward and sealed OOS expectancy is non-positive or tail loss fails",
        ),
    )
    return {spec.mechanism_id: spec for spec in specs}
