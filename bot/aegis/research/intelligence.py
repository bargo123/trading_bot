"""Research-only composition of market state, book evidence, and experience."""
from __future__ import annotations

from dataclasses import replace
from typing import Sequence

from aegis.research.books_index import BookIndex
from aegis.research.knowledge import hypotheses_for_market, search_full_book_knowledge
from aegis.research.market_state import MarketState
from aegis.research.thesis import EvidenceItem, Thesis, calibrate_outcomes


def form_research_thesis(
    *,
    thesis_id: str,
    symbol: str,
    side: str,
    setup: str,
    state: MarketState,
    historical_outcomes: Sequence[float],
    book_query: str,
    index: BookIndex,
    invalidation: str,
    expected_duration: str,
    outcome_scope: str = "unattributed",
) -> Thesis:
    """Compose an explainable, non-executing thesis from observable inputs."""
    regime = str(state.regime.get("label") or "unknown")
    sources = search_full_book_knowledge(index, book_query)
    available_data = {"broker_tick_volume_proxy"}
    if state.execution.get("l2") is True:
        available_data.add("mt5_l2")
    proposals = hypotheses_for_market(
        sources,
        regime=regime,
        required_data=available_data,
    )
    support = tuple(
        EvidenceItem(
            source=f"book:{proposal.source.filename}",
            concept=proposal.source.title or proposal.source.filename,
            supports=True,
            detail=proposal.falsifiable_claim,
            provenance={"file_hash": proposal.source.file_hash, "hypothesis_id": proposal.hypothesis_id},
        )
        for proposal in proposals
        if proposal.label != "unavailable"
    )
    structural = state.structure.get("M15") or {}
    contradictions: tuple[EvidenceItem, ...] = tuple(
        EvidenceItem(
            source=f"book:{proposal.source.filename}",
            concept=proposal.source.title or proposal.source.filename,
            supports=False,
            detail=(
                "not used as support: required data unavailable "
                f"({', '.join(proposal.market_conditions['data_requirements']) or 'unspecified'})"
            ),
            provenance={"file_hash": proposal.source.file_hash},
        )
        for proposal in proposals
        if proposal.label == "unavailable"
    )
    if structural.get("kind") in {"failure", "unavailable"}:
        contradictions += (
            EvidenceItem(
                source="market_state",
                concept="M15 structure",
                supports=False,
                detail=f"structure event is {structural.get('kind')}",
            ),
        )
    calibration = calibrate_outcomes(historical_outcomes)
    if outcome_scope != "state_matched":
        calibration = replace(
            calibration,
            uncertainty=f"{outcome_scope}_outcomes_not_market_state_matched",
            eligible=False,
        )
    return Thesis(
        thesis_id=thesis_id,
        symbol=symbol,
        side=side,
        setup=setup,
        market_state=state.as_dict(),
        supporting_evidence=support,
        contradicting_evidence=contradictions,
        invalidation=invalidation,
        expected_duration=expected_duration,
        calibrated_evidence=calibration,
        book_provenance=tuple(
            {
                "filename": proposal.source.filename,
                "file_hash": proposal.source.file_hash,
                "data_available": proposal.market_conditions["data_available"],
            }
            for proposal in proposals
        ),
        historical_analogue_query={
            "regime": regime,
            "symbol": symbol,
            "setup": setup,
            "outcome_count": len(historical_outcomes),
            "outcome_scope": outcome_scope,
        },
    )
