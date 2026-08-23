"""Dashboard and live monitoring."""
from __future__ import annotations

import json
import logging
import sys
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class Dashboard:
    """Live terminal dashboard for research factory."""

    def __init__(self, state: Any):
        self.state = state
        self.start_time = time.time()
        self.event_log: List[Dict[str, Any]] = []

    def log_event(self, event_type: str, message: str, **kwargs) -> None:
        """Log a live event."""
        event = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event_type": event_type,
            "message": message,
            "data": kwargs,
        }
        self.event_log.append(event)

        # Print to console
        timestamp = datetime.now(timezone.utc).strftime("%H:%M:%S")
        extra = f" | {json.dumps(kwargs, default=str)}" if kwargs else ""
        print(f"[{timestamp}] [{event_type}] {message}{extra}", flush=True)

    def print_dashboard(self, state: Any) -> None:
        """Print live dashboard."""
        champion = state.champion.hypothesis_id if state.champion else "NONE"
        challenger = state.challenger.hypothesis_id if state.challenger else "NONE"

        dashboard = f"""
==============================================================
AEGIS ZERO-LOSS RESEARCH FACTORY
==============================================================
Generation: {state.generation}
Champion: {champion}
Challenger: {challenger}
Dataset: {state.dataset_fingerprint[:16] if state.dataset_fingerprint else 'UNKNOWN'}
Experiments tested: {len(state.experiments)}
Experiments rejected: {len([e for e in state.experiments if e.decision == 'REJECTED'])}
Current hypothesis: {state.challenger.hypothesis_id if state.challenger else 'N/A'}
Claude: {'AVAILABLE' if state.claude_available else 'UNAVAILABLE'}
Codex calls: {state.codex_calls} / {state.codex_budget}
Market: {'CLOSED / WEEKEND_RESEARCH' if state.market_state.value == 'WEEKEND_RESEARCH' else 'OPEN'}
Live trading: DISABLED
==============================================================
"""
        print(dashboard, flush=True)

    def log_event(self, event_type: str, message: str, **kwargs) -> None:
        """Log a live event."""
        event = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event_type": event_type,
            "message": message,
            "data": kwargs,
        }

        # Print formatted event
        timestamp = datetime.now(timezone.utc).strftime("%H:%M:%S")
        extra = f" | {json.dumps(kwargs, default=str)}" if kwargs else ""
        print(f"[{timestamp}] [{event_type}] {message}{extra}", flush=True)