"""Fail-closed promotion boundary for external research DAG output.

External tools and book algorithms can create evidence.  Only this module can
compile that evidence into the small immutable bundle consumed by the runtime.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
import math
import re
from types import MappingProxyType
from typing import Any, Mapping

from aegis.research.watcher_algorithms import ALGORITHM_MODULES

from .catalog import REQUIRED_EXTERNAL_TOOLS
from .contracts import ResearchBundle, canonical_json, content_hash


_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_MIN_TRADES = 20
_MIN_LOSSES = 5


class ExecutionBundleRejected(ValueError):
    """Research evidence is not allowed to become runtime authority."""


def _json_copy(value: Any) -> Any:
    return json.loads(canonical_json(value))


def _freeze(value: Any) -> Any:
    if isinstance(value, dict):
        return MappingProxyType({str(key): _freeze(item) for key, item in value.items()})
    if isinstance(value, list):
        return tuple(_freeze(item) for item in value)
    return value


@dataclass(frozen=True)
class PromotionDecision:
    status: str
    reasons: tuple[str, ...]

    @property
    def authorized(self) -> bool:
        return self.status == "EXECUTION_CANDIDATE" and not self.reasons


@dataclass(frozen=True)
class ExecutionBundle:
    research_bundle_hash: str
    dataset_hash: str
    validation_hash: str
    model_artifact_hash: str
    target_definition: str
    authorized_symbols: tuple[str, ...]
    authorized_horizons_s: tuple[int, ...]
    models: Mapping[str, Any]
    validation: Mapping[str, Any]
    book_context: Mapping[str, Any]
    book_algorithm_count: int
    created_at: float
    expires_at: float
    promotion_status: str = "EXECUTION_CANDIDATE"
    schema_version: str = "aegis.execution_bundle.v1"
    bundle_hash: str = ""

    def __post_init__(self) -> None:
        for field in (
            "research_bundle_hash",
            "dataset_hash",
            "validation_hash",
            "model_artifact_hash",
        ):
            value = str(getattr(self, field) or "").lower()
            if not _SHA256.fullmatch(value):
                raise ValueError(f"{field} must be a SHA-256 digest")
            object.__setattr__(self, field, value)
        if self.schema_version != "aegis.execution_bundle.v1":
            raise ValueError("unsupported execution bundle schema")
        if not str(self.target_definition or "").strip():
            raise ValueError("execution bundle target_definition is required")
        if self.promotion_status != "EXECUTION_CANDIDATE":
            raise ValueError("execution bundle is not execution candidate")
        symbols = tuple(str(value).upper().strip() for value in self.authorized_symbols)
        if not symbols or any(not value for value in symbols) or len(set(symbols)) != len(symbols):
            raise ValueError("authorized_symbols must be non-empty and unique")
        horizons = tuple(int(value) for value in self.authorized_horizons_s)
        if not horizons or any(value <= 0 for value in horizons) or len(set(horizons)) != len(horizons):
            raise ValueError("authorized_horizons_s must be positive and unique")
        object.__setattr__(self, "authorized_symbols", symbols)
        object.__setattr__(self, "authorized_horizons_s", horizons)
        created_at = _finite_number(self.created_at)
        expires_at = _finite_number(self.expires_at)
        if created_at is None or expires_at is None or expires_at <= created_at:
            raise ValueError("execution bundle validity interval is invalid")
        object.__setattr__(self, "created_at", created_at)
        object.__setattr__(self, "expires_at", expires_at)
        models = _freeze(_json_copy(self.models))
        validation = _freeze(_json_copy(self.validation))
        book_context = _freeze(_json_copy(self.book_context))
        object.__setattr__(self, "models", models)
        object.__setattr__(self, "validation", validation)
        object.__setattr__(self, "book_context", book_context)
        material = self._material()
        digest = content_hash(material)
        if self.bundle_hash and self.bundle_hash != digest:
            raise ValueError("execution bundle hash mismatch")
        object.__setattr__(self, "bundle_hash", digest)

    def validate_for_runtime(self) -> None:
        """Reject model identities that escape the bundle authorization scope."""
        if not isinstance(self.book_context, Mapping):
            raise ValueError("book context is invalid")
        if str(self.book_context.get("status") or "").upper() != "AVAILABLE":
            raise ValueError("book context is unavailable")
        if self.book_context.get("compiled_from_artifact") is not True:
            raise ValueError("book context is not compiled from artifact")
        if self.book_context.get("execution_authority") is not False:
            raise ValueError("book context claimed broker authority")
        if self.book_context.get("research_only") is not True:
            raise ValueError("book context is not research-only")
        if self.book_context.get("no_lookahead") is not True:
            raise ValueError("book context is not causal")
        if self.book_context.get("order_intent") is not False:
            raise ValueError("book context contains order intent")
        if not _integer_matches(self.book_algorithm_count, len(ALGORITHM_MODULES)):
            raise ValueError("book algorithm coverage count is invalid")
        expected_registry_hash = content_hash(tuple(ALGORITHM_MODULES))
        if str(self.book_context.get("book_registry_hash") or "").lower() != expected_registry_hash:
            raise ValueError("book context registry mismatch")
        artifact_hash = str(self.book_context.get("artifact_hash") or "").lower()
        state_hash = str(self.book_context.get("state_hash") or "").lower()
        if not _SHA256.fullmatch(artifact_hash):
            raise ValueError("book context artifact hash is invalid")
        if not _SHA256.fullmatch(state_hash):
            raise ValueError("book context state hash is invalid")
        algorithm_ids = self.book_context.get("algorithm_ids")
        normalized_ids = tuple(str(value) for value in algorithm_ids) if isinstance(algorithm_ids, (list, tuple)) else ()
        if (
            len(normalized_ids) != len(ALGORITHM_MODULES)
            or len(set(normalized_ids)) != len(normalized_ids)
            or set(normalized_ids) != set(ALGORITHM_MODULES)
            or int(self.book_context.get("algorithm_count") or 0) != len(ALGORITHM_MODULES)
        ):
            raise ValueError("book context algorithm coverage is incomplete")
        partitions: list[tuple[str, ...]] = []
        for key in ("supporting_algorithms", "opposing_algorithms", "missing_data_algorithms"):
            raw = self.book_context.get(key)
            if not isinstance(raw, (list, tuple)):
                raise ValueError("book context partitions are invalid")
            partitions.append(tuple(str(value) for value in raw))
        flattened = tuple(value for partition in partitions for value in partition)
        if (
            len(set(flattened)) != len(flattened)
            or set(flattened) != set(ALGORITHM_MODULES)
            or self.book_context.get("absolute_views") is not True
        ):
            raise ValueError("book context partitions are invalid")
        if any(
            int(self.book_context.get(count_key) or 0) != len(partition)
            for count_key, partition in zip(
                ("supporting_count", "opposing_count", "missing_data_count"), partitions
            )
        ):
            raise ValueError("book context partition counts are invalid")
        provenance = self.validation.get("research_provenance") if isinstance(self.validation, Mapping) else None
        if not isinstance(provenance, Mapping) or not isinstance(provenance.get("nodes"), (list, tuple)):
            raise ValueError("research provenance is required")
        nodes = provenance["nodes"]
        if not nodes:
            raise ValueError("research provenance is empty")
        tool_ids: list[str] = []
        book_nodes: list[Mapping[str, Any]] = []
        for node in nodes:
            if not isinstance(node, Mapping) or node.get("execution_authority") is not False:
                raise ValueError("research provenance claimed broker authority")
            if str(node.get("status") or "").upper() != "SUCCESS":
                raise ValueError("research provenance node not successful")
            tool_id = str(node.get("tool_id") or "").strip()
            if not tool_id:
                raise ValueError("research provenance tool identity is missing")
            tool_ids.append(tool_id)
            if tool_id == "aegis-book-algorithms":
                book_nodes.append(node)
            hashes = node.get("artifact_hashes") or ()
            if any(not _SHA256.fullmatch(str(value).lower()) for value in hashes):
                raise ValueError("research provenance artifact hash is invalid")
        expected_tools = set(REQUIRED_EXTERNAL_TOOLS) | {"aegis-book-algorithms"}
        if set(tool_ids) != expected_tools or len(tool_ids) != len(expected_tools):
            raise ValueError("research provenance tool coverage is incomplete")
        if str(provenance.get("book_registry_hash") or "").lower() != expected_registry_hash:
            raise ValueError("research provenance book registry hash is invalid")
        if (
            len(book_nodes) != 1
            or artifact_hash not in {str(value).lower() for value in (book_nodes[0].get("artifact_hashes") or ())}
        ):
            raise ValueError("book context artifact is not in research provenance")
        for prefix, key in (
            ("chronological", "chronological_test"),
            ("validation", "validation_oos"),
            ("sealed", "sealed_oos"),
        ):
            split_errors: list[str] = []
            _check_split(prefix, self.validation.get(key), split_errors)
            if split_errors:
                raise ValueError(f"{prefix} validation metrics invalid:{','.join(split_errors)}")
        # Selected exact-strategy evidence is required at the research-to-
        # execution promotion boundary (`assess_execution_readiness`).  Keep
        # runtime loading backwards-compatible with older, already-issued
        # bundles that predate that provenance field; no new bundle can be
        # created without the selected gate above.
        authorized_symbols = set(self.authorized_symbols)
        authorized_horizons = set(self.authorized_horizons_s)
        if not isinstance(self.models, Mapping) or not self.models:
            raise ValueError("validated models are missing")
        for symbol, per_side in self.models.items():
            symbol_key = str(symbol).upper().strip()
            if symbol_key not in authorized_symbols:
                raise ValueError(f"model_symbol_not_authorized:{symbol_key}")
            if not isinstance(per_side, Mapping):
                raise ValueError(f"model_side_scope_invalid:{symbol_key}")
            for side, per_mechanism in per_side.items():
                side_key = str(side).upper().strip()
                if side_key not in {"BUY", "SELL"} or not isinstance(per_mechanism, Mapping):
                    raise ValueError(f"model_side_scope_invalid:{symbol_key}:{side}")
                for mechanism, per_horizon in per_mechanism.items():
                    if not str(mechanism).strip() or not isinstance(per_horizon, Mapping):
                        raise ValueError(f"model_mechanism_scope_invalid:{symbol_key}:{side_key}")
                    for horizon, metrics in per_horizon.items():
                        try:
                            horizon_s = int(horizon)
                        except (TypeError, ValueError) as exc:
                            raise ValueError(
                                f"model_horizon_scope_invalid:{symbol_key}:{side_key}:{horizon}"
                            ) from exc
                        if horizon_s not in authorized_horizons:
                            raise ValueError(
                                f"model_horizon_not_authorized:{symbol_key}:{side_key}:{horizon_s}"
                            )
                        if not isinstance(metrics, Mapping):
                            raise ValueError(
                                f"model_metrics_invalid:{symbol_key}:{side_key}:{horizon_s}"
                            )

    def _material(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "research_bundle_hash": self.research_bundle_hash,
            "dataset_hash": self.dataset_hash,
            "validation_hash": self.validation_hash,
            "model_artifact_hash": self.model_artifact_hash,
            "target_definition": self.target_definition,
            "authorized_symbols": list(self.authorized_symbols),
            "authorized_horizons_s": list(self.authorized_horizons_s),
            "models": _json_copy(self.models),
            "validation": _json_copy(self.validation),
            "book_context": _json_copy(self.book_context),
            "book_algorithm_count": self.book_algorithm_count,
            "created_at": self.created_at,
            "expires_at": self.expires_at,
            "promotion_status": self.promotion_status,
        }

    def as_dict(self) -> dict[str, Any]:
        return {**self._material(), "bundle_hash": self.bundle_hash}

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "ExecutionBundle":
        return cls(
            research_bundle_hash=str(raw.get("research_bundle_hash") or ""),
            dataset_hash=str(raw.get("dataset_hash") or ""),
            validation_hash=str(raw.get("validation_hash") or ""),
            model_artifact_hash=str(raw.get("model_artifact_hash") or ""),
            target_definition=str(raw.get("target_definition") or ""),
            authorized_symbols=tuple(raw.get("authorized_symbols") or ()),
            authorized_horizons_s=tuple(raw.get("authorized_horizons_s") or ()),
            models=raw.get("models") or {},
            validation=raw.get("validation") or {},
            book_context=raw.get("book_context") or {},
            book_algorithm_count=int(raw.get("book_algorithm_count") or 0),
            created_at=float(raw.get("created_at") or 0.0),
            expires_at=float(raw.get("expires_at") or 0.0),
            promotion_status=str(raw.get("promotion_status") or ""),
            schema_version=str(raw.get("schema_version") or ""),
            bundle_hash=str(raw.get("bundle_hash") or ""),
        )


def _finite_number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _integer_matches(value: Any, expected: int) -> bool:
    number = _finite_number(value)
    return number is not None and number.is_integer() and int(number) == int(expected)


def _check_split(prefix: str, raw: Any, reasons: list[str]) -> None:
    if not isinstance(raw, Mapping):
        reasons.append(f"missing_{prefix}_metrics")
        return
    expectancy = _finite_number(raw.get("expectancy"))
    profit_factor = _finite_number(raw.get("profit_factor"))
    n_trades = _finite_number(raw.get("n_trades"))
    n_losses = _finite_number(raw.get("n_losses"))
    if expectancy is None or expectancy <= 0:
        reasons.append(f"{prefix}_expectancy_not_positive")
    if profit_factor is None or profit_factor <= 1:
        reasons.append(f"{prefix}_profit_factor_not_above_one")
    if n_trades is None or int(n_trades) < _MIN_TRADES:
        reasons.append(f"{prefix}_observations_insufficient")
    if n_losses is None or int(n_losses) < _MIN_LOSSES:
        reasons.append(f"{prefix}_loss_observations_insufficient")


def _exact_metric_is_positive(raw: Any) -> bool:
    """Return whether one exact identity clears the after-cost evidence gate."""
    if not isinstance(raw, Mapping):
        return False
    # ``rejection_adjusted_expectancy`` is emitted by the selected replay and
    # is the only metric accepted for promotion: its base return already
    # includes executable spread/slippage/commission/latency costs, while the
    # adjustment applies the observed runner rejection rate.
    expectancy = _finite_number(raw.get("rejection_adjusted_expectancy"))
    profit_factor = _finite_number(raw.get("profit_factor"))
    samples = _finite_number(raw.get("signal_samples"))
    losses = _finite_number(raw.get("losses"))
    return (
        expectancy is not None
        and expectancy > 0.0
        and profit_factor is not None
        and profit_factor > 1.0
        and samples is not None
        and samples.is_integer()
        and int(samples) >= _MIN_TRADES
        and losses is not None
        and losses.is_integer()
        and int(losses) >= _MIN_LOSSES
    )


def _cost_model_provenance_is_complete(raw: Any, *, expected_rows: int | None = None) -> bool:
    """Require explicit per-row executable cost provenance before promotion."""
    if not isinstance(raw, Mapping):
        return False
    if (
        raw.get("schema") != "aegis.shadow_cost_model.v1"
        or str(raw.get("status") or "").upper() != "COMPLETE"
        or raw.get("per_row") is not True
        or raw.get("spread") != "executable_bid_ask_entry_and_liquidation"
        or raw.get("outcome_units")
        != "captured_exit_return is broker-unit-normalized after-cost return"
    ):
        return False
    checked = _finite_number(raw.get("rows_checked"))
    complete = _finite_number(raw.get("rows_complete"))
    if (
        checked is None
        or complete is None
        or not checked.is_integer()
        or not complete.is_integer()
        or checked <= 0
        or complete != checked
        or (expected_rows is not None and int(checked) != int(expected_rows))
    ):
        return False
    for field in (
        "slippage_bps",
        "commission_round_trip_usd",
        "entry_latency_s",
        "close_latency_s",
    ):
        value = _finite_number(raw.get(field))
        if value is None or value < 0.0:
            return False
    conversion = _finite_number(raw.get("usd_per_price_unit"))
    return conversion is not None and conversion > 0.0


def _check_selected_strategy_evidence(
    evidence: Mapping[str, Any],
    reasons: list[str],
) -> None:
    """Require one exact symbol/side/mechanism/horizon positive OOS identity."""
    raw_ids = evidence.get("selected_strategy_ids")
    if not isinstance(raw_ids, (list, tuple)):
        reasons.append("selected_strategy_evidence_missing")
        return
    selected_ids = tuple(str(value).strip() for value in raw_ids)
    if (
        not 1 <= len(selected_ids) <= 10
        or any(not value for value in selected_ids)
        or len(set(selected_ids)) != len(selected_ids)
    ):
        reasons.append("selected_strategy_ids_invalid")
        return
    selected_validation = evidence.get("selected_strategy_validation")
    if not isinstance(selected_validation, Mapping):
        reasons.append("selected_strategy_validation_missing")
        return
    if (
        selected_validation.get("no_lookahead") is not True
        or selected_validation.get("research_only") is not True
        or selected_validation.get("execution_authority") is not False
        or tuple(str(value).strip() for value in (selected_validation.get("algorithm_ids") or ()))
        != selected_ids
    ):
        reasons.append("selected_strategy_validation_not_causal")
        return
    adjustment = selected_validation.get("rejection_adjustment")
    if not isinstance(adjustment, Mapping) or adjustment.get("applied_to_expectancy") is not True:
        reasons.append("selected_strategy_rejection_costs_missing")
        return
    cost_provenance = selected_validation.get("cost_model_provenance")
    expected_rows = _finite_number(selected_validation.get("rows_replayed"))
    expected_row_count = (
        int(expected_rows)
        if expected_rows is not None and expected_rows.is_integer()
        else None
    )
    if not isinstance(cost_provenance, Mapping):
        reasons.append("selected_strategy_cost_model_missing")
    elif not _cost_model_provenance_is_complete(
        cost_provenance, expected_rows=expected_row_count
    ):
        reasons.append("selected_strategy_cost_model_incomplete")
    raw_symbols = evidence.get("authorized_symbols")
    authorized_symbols = (
        {str(value).upper().strip() for value in raw_symbols if str(value).strip()}
        if isinstance(raw_symbols, (list, tuple))
        else set()
    )
    raw_horizons = evidence.get("authorized_horizons_s")
    try:
        authorized_horizons = (
            {int(value) for value in raw_horizons}
            if isinstance(raw_horizons, (list, tuple))
            else set()
        )
    except (TypeError, ValueError):
        authorized_horizons = set()
    split_replay = selected_validation.get("split_replay")
    if not isinstance(split_replay, Mapping):
        reasons.append("selected_exact_strategy_oos_missing")
        return
    split_exact: dict[str, Mapping[str, Any]] = {}
    for split_name in ("validation", "sealed"):
        split = split_replay.get(split_name)
        exact = split.get("exact_strategies") if isinstance(split, Mapping) else None
        if not isinstance(exact, Mapping):
            reasons.append(f"selected_{split_name}_exact_metrics_missing")
            continue
        for key, metric in exact.items():
            key_text = str(key)
            parts = key_text.split("|")
            if len(parts) != 5 or parts[0] not in selected_ids:
                continue
            symbol, side, horizon_text, mechanism = parts[1].upper().strip(), parts[2].upper().strip(), parts[3], parts[4].strip()
            try:
                horizon_s = int(horizon_text)
            except (TypeError, ValueError):
                continue
            if (
                symbol not in authorized_symbols
                or side not in {"BUY", "SELL"}
                or horizon_s not in authorized_horizons
                or not mechanism
            ):
                continue
            if not isinstance(metric, Mapping):
                continue
            # Only identities that are present in both forward OOS splits can
            # be promoted.  Their symbol/side/horizon/mechanism identity is
            # retained verbatim in the execution-bundle provenance.
            split_exact[f"{split_name}:{key_text}"] = metric
    candidates: set[str] = set()
    for prefix, metric in split_exact.items():
        _, key = prefix.split(":", 1)
        if prefix.startswith("validation:") and _exact_metric_is_positive(metric):
            candidates.add(key)
    sealed_exact = {
        prefix.split(":", 1)[1]: metric
        for prefix, metric in split_exact.items()
        if prefix.startswith("sealed:")
    }
    if not any(
        key in sealed_exact and _exact_metric_is_positive(sealed_exact[key])
        for key in candidates
    ):
        reasons.append("selected_exact_strategy_oos_not_positive")


def _check_book_context(
    research_bundle: ResearchBundle,
    evidence: Mapping[str, Any],
    reasons: list[str],
) -> None:
    """Require book evidence compiled from the successful authoritative node."""
    context = evidence.get("book_context")
    if not isinstance(context, Mapping) or not context:
        reasons.append("book_context_missing_or_invalid")
        return
    if str(context.get("status") or "").upper() != "AVAILABLE":
        reasons.append("book_context_missing_or_invalid")
    if context.get("execution_authority") is not False:
        reasons.append("book_context_not_read_only")
    if context.get("research_only") is not True:
        reasons.append("book_context_not_research_only")
    if context.get("no_lookahead") is not True:
        reasons.append("book_context_not_causal")
    if context.get("order_intent") is not False:
        reasons.append("book_context_order_intent_not_disabled")
    if context.get("compiled_from_artifact") is not True:
        reasons.append("book_context_not_compiled")
    expected_registry_hash = content_hash(tuple(ALGORITHM_MODULES))
    supplied_registry_hash = str(context.get("book_registry_hash") or "").lower()
    if supplied_registry_hash != expected_registry_hash:
        reasons.append("book_context_registry_mismatch")

    book_result = next(
        (row for row in research_bundle.node_results if row.tool_id == "aegis-book-algorithms"),
        None,
    )
    artifact_hash = str(context.get("artifact_hash") or "").lower()
    if (
        book_result is None
        or book_result.status != "SUCCESS"
        or not _SHA256.fullmatch(artifact_hash)
        or artifact_hash not in {str(value).lower() for value in book_result.artifact_hashes}
    ):
        reasons.append("book_context_artifact_not_from_book_node")
    state_hash = str(context.get("state_hash") or "").lower()
    if not _SHA256.fullmatch(state_hash):
        reasons.append("book_context_state_invalid")

    algorithm_ids = context.get("algorithm_ids")
    normalized_ids = tuple(str(value) for value in algorithm_ids) if isinstance(algorithm_ids, (list, tuple)) else ()
    if (
        len(normalized_ids) != len(ALGORITHM_MODULES)
        or len(set(normalized_ids)) != len(normalized_ids)
        or set(normalized_ids) != set(ALGORITHM_MODULES)
        or not _integer_matches(context.get("algorithm_count"), len(ALGORITHM_MODULES))
    ):
        reasons.append("book_context_algorithm_coverage_incomplete")

    partitions: list[tuple[str, ...]] = []
    for key in ("supporting_algorithms", "opposing_algorithms", "missing_data_algorithms"):
        raw = context.get(key)
        if not isinstance(raw, (list, tuple)):
            reasons.append("book_context_partition_invalid")
            return
        partitions.append(tuple(str(value) for value in raw))
    flattened = tuple(value for partition in partitions for value in partition)
    if (
        len(set(flattened)) != len(flattened)
        or set(flattened) != set(ALGORITHM_MODULES)
        or any(value not in set(ALGORITHM_MODULES) for value in flattened)
        or context.get("absolute_views") is not True
        or any(
            not _integer_matches(context.get(count_key), len(partition))
            for count_key, partition in zip(
                ("supporting_count", "opposing_count", "missing_data_count"), partitions
            )
        )
    ):
        reasons.append("book_context_partition_invalid")


def assess_execution_readiness(
    research_bundle: ResearchBundle,
    evidence: Mapping[str, Any],
) -> PromotionDecision:
    """Assess execution eligibility without defaulting missing evidence."""
    reasons: list[str] = []
    results = {row.tool_id: row for row in research_bundle.node_results}
    required = set(REQUIRED_EXTERNAL_TOOLS) | {"aegis-book-algorithms"}
    if not research_bundle.complete:
        reasons.append("research_bundle_incomplete")
    for tool_id in sorted(required):
        row = results.get(tool_id)
        if row is None:
            reasons.append(f"required_node_missing:{tool_id}")
        elif row.status != "SUCCESS":
            reasons.append("required_node_not_successful")
            break
    _check_book_context(research_bundle, evidence, reasons)

    if evidence.get("target_definition") != "captured_exit_replay":
        reasons.append("target_not_executable_captured_exit_replay")
    for field in ("dataset_hash", "validation_hash", "model_artifact_hash", "book_registry_hash"):
        value = str(evidence.get(field) or "").lower()
        if not _SHA256.fullmatch(value):
            reasons.append(f"invalid_{field}")
    expected_book_registry_hash = content_hash(tuple(ALGORITHM_MODULES))
    supplied_book_registry_hash = str(evidence.get("book_registry_hash") or "").lower()
    if (
        _SHA256.fullmatch(supplied_book_registry_hash)
        and supplied_book_registry_hash != expected_book_registry_hash
    ):
        reasons.append("book_registry_hash_mismatch")
    created_at = _finite_number(evidence.get("created_at"))
    expires_at = _finite_number(evidence.get("expires_at"))
    if created_at is None or expires_at is None or expires_at <= created_at:
        reasons.append("invalid_execution_validity_interval")

    _check_split("chronological", evidence.get("chronological_test"), reasons)
    _check_split("validation", evidence.get("validation_oos"), reasons)
    _check_split("sealed", evidence.get("sealed_oos"), reasons)
    _check_selected_strategy_evidence(evidence, reasons)

    for field in ("calibration_ece", "p95_loss", "p99_loss", "abstain_rate"):
        value = _finite_number(evidence.get(field))
        if value is None or value < 0:
            reasons.append(f"missing_or_invalid_{field}")
    if str(evidence.get("perturbation_status") or "").upper() != "STABLE":
        reasons.append("perturbation_not_stable")
    if str(evidence.get("replay_parity_status") or "").upper() != "MATCHED":
        reasons.append("replay_parity_not_matched")

    if not _integer_matches(evidence.get("book_algorithm_count"), len(ALGORITHM_MODULES)):
        reasons.append("book_algorithm_coverage_incomplete")

    symbols = evidence.get("authorized_symbols")
    horizons = evidence.get("authorized_horizons_s")
    if not isinstance(symbols, (list, tuple)) or not symbols:
        reasons.append("authorized_symbols_missing")
        symbol_set: set[str] = set()
    else:
        symbol_set = {str(symbol).upper().strip() for symbol in symbols if str(symbol).strip()}
        if len(symbol_set) != len(symbols):
            reasons.append("authorized_symbols_invalid")
    if not isinstance(horizons, (list, tuple)) or not horizons:
        reasons.append("authorized_horizons_missing")
        horizon_set: set[int] = set()
    else:
        try:
            horizon_set = {int(value) for value in horizons}
        except (TypeError, ValueError):
            horizon_set = set()
        if len(horizon_set) != len(horizons) or any(value <= 0 for value in horizon_set):
            reasons.append("authorized_horizons_invalid")

    models = evidence.get("models")
    if not isinstance(models, Mapping) or not models:
        reasons.append("validated_models_missing")
    else:
        for symbol, per_side in models.items():
            if str(symbol).upper() not in symbol_set or not isinstance(per_side, Mapping):
                reasons.append("model_outside_authorized_scope")
                continue
            for side, per_mechanism in per_side.items():
                if str(side).upper() not in {"BUY", "SELL"} or not isinstance(per_mechanism, Mapping):
                    reasons.append("model_outside_authorized_scope")
                    continue
                for mechanism, per_horizon in per_mechanism.items():
                    if not str(mechanism).strip() or not isinstance(per_horizon, Mapping):
                        reasons.append("model_outside_authorized_scope")
                        continue
                    for horizon, metrics in per_horizon.items():
                        try:
                            horizon_s = int(horizon)
                        except (TypeError, ValueError):
                            reasons.append("model_outside_authorized_scope")
                            continue
                        probability = (
                            metrics.get("p_captured_win")
                            if isinstance(metrics, Mapping) else None
                        )
                        p_win = _finite_number(probability)
                        threshold = _finite_number(
                            metrics.get("threshold") if isinstance(metrics, Mapping) else None
                        )
                        expected_net = _finite_number(
                            metrics.get("expected_net_pnl") if isinstance(metrics, Mapping) else None
                        )
                        expected_lcb = _finite_number(
                            metrics.get("expected_net_pnl_lcb95") if isinstance(metrics, Mapping) else None
                        )
                        evidence_n = _finite_number(
                            metrics.get("evidence_n") if isinstance(metrics, Mapping) else None
                        )
                        evidence_losses = _finite_number(
                            metrics.get("evidence_losses") if isinstance(metrics, Mapping) else None
                        )
                        if (
                            horizon_s not in horizon_set
                            or p_win is None
                            or not 0 <= p_win <= 1
                            or threshold is None
                            or not 0 < threshold < 1
                            or expected_net is None
                            or expected_net <= 0
                            or expected_lcb is None
                            or expected_lcb <= 0
                            or not bool(metrics.get("decision"))
                            or str(metrics.get("calibration_status") or "").upper() != "CALIBRATED"
                            or evidence_n is None
                            or int(evidence_n) < _MIN_TRADES
                            or evidence_losses is None
                            or int(evidence_losses) < _MIN_LOSSES
                        ):
                            reasons.append("model_outside_authorized_scope")

    unique_reasons = tuple(dict.fromkeys(reasons))
    return PromotionDecision(
        status="EXECUTION_CANDIDATE" if not unique_reasons else "SHADOW_ONLY",
        reasons=unique_reasons,
    )


def build_execution_bundle(
    research_bundle: ResearchBundle,
    evidence: Mapping[str, Any],
) -> ExecutionBundle:
    decision = assess_execution_readiness(research_bundle, evidence)
    if not decision.authorized:
        raise ExecutionBundleRejected(",".join(decision.reasons))
    symbols = tuple(str(value).upper().strip() for value in evidence["authorized_symbols"])
    horizons = tuple(int(value) for value in evidence["authorized_horizons_s"])
    validation = {
        "chronological_test": evidence["chronological_test"],
        "validation_oos": evidence["validation_oos"],
        "sealed_oos": evidence["sealed_oos"],
        "calibration_ece": evidence["calibration_ece"],
        "p95_loss": evidence["p95_loss"],
        "p99_loss": evidence["p99_loss"],
        "abstain_rate": evidence["abstain_rate"],
        "perturbation_status": evidence["perturbation_status"],
        "replay_parity_status": evidence["replay_parity_status"],
        "selected_strategy_ids": list(evidence.get("selected_strategy_ids") or ()),
        "selected_strategy_validation": evidence.get("selected_strategy_validation") or {},
        "research_provenance": {
            "book_registry_hash": str(evidence["book_registry_hash"]).lower(),
            "nodes": [
                {
                    "node_id": str(result.node_id),
                    "tool_id": str(result.tool_id),
                    "status": str(result.status),
                    "request_id": str(result.request_id),
                    "artifact_hashes": list(result.artifact_hashes),
                    "execution_authority": False,
                }
                for result in research_bundle.node_results
            ],
        },
    }
    return ExecutionBundle(
        research_bundle_hash=research_bundle.bundle_hash,
        dataset_hash=str(evidence["dataset_hash"]).lower(),
        validation_hash=str(evidence["validation_hash"]).lower(),
        model_artifact_hash=str(evidence["model_artifact_hash"]).lower(),
        target_definition="captured_exit_replay",
        authorized_symbols=symbols,
        authorized_horizons_s=horizons,
        models=evidence["models"],
        validation=validation,
        book_context=evidence.get("book_context") or {},
        book_algorithm_count=int(evidence["book_algorithm_count"]),
        created_at=float(evidence["created_at"]),
        expires_at=float(evidence["expires_at"]),
    )


__all__ = [
    "ExecutionBundle",
    "ExecutionBundleRejected",
    "PromotionDecision",
    "assess_execution_readiness",
    "build_execution_bundle",
]
