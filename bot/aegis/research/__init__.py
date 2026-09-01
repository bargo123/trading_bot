"""Persistent research loop: registry, fingerprints, gates. Does not place orders."""
from __future__ import annotations

from aegis.research.champion import ChampionStore
from aegis.research.registry import EquivalentExperimentError, ExperimentRegistry

__all__ = ["ChampionStore", "EquivalentExperimentError", "ExperimentRegistry"]
