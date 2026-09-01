"""Truthful, deterministic evaluation of book-derived strategy evidence."""
from __future__ import annotations

import hashlib
import json
import math
import re
from typing import Any, Mapping

_DIRECT_KEYS = frozenset({
    "timestamp", "symbol", "side", "mechanism", "horizon_s", "session", "regime",
    "structure", "bid", "ask", "spread", "spread_pips", "quote_age_s", "volatility",
    "volatility_context", "short_returns", "tick_velocity", "tick_direction",
    "m1_context", "m5_context", "m15_context", "provenance", "schema_version",
})
_SAFE_DERIVED_KEYS = frozenset({
    "entry", "timeframe", "family", "setup_family", "trend", "m1_trend", "m5_trend",
    "m15_trend", "h1_trend", "higher_timeframe", "momentum", "momentum_context",
    "momentum_persistence", "momentum_decay", "price_acceleration", "spread_change",
    "spread_acceleration", "micro_volatility", "realized_vol_60s", "realized_volatility",
    "volatility_expansion", "volatility_state", "volatility_percentile", "compression",
    "expansion", "impulse", "follow_through", "tick_persistence", "imbalance",
    "bid_ask_imbalance", "queue_imbalance", "order_flow", "tick_activity", "tick_count",
    "tick_activity_ratio", "volume", "volume_ratio", "relative_volume", "tick_volume",
    "bar_range", "price_change", "effort_result", "range_state", "range_position",
    "range_high", "range_low", "range_width", "range_expansion", "breakout", "breakout_state",
    "breakout_confirmation", "retest", "pullback", "retracement", "rejection", "support",
    "resistance", "support_level", "resistance_level", "level_role", "level_state",
    "distance_to_support", "distance_to_resistance", "channel_state", "channel_direction",
    "channel_upper", "channel_lower", "channel_position", "channel_breakout", "price_position",
    "trend_channel", "pattern", "chart_pattern", "pattern_state", "pattern_confirmation",
    "failure_state", "measured_move", "pattern_direction", "pattern_detection_provenance", "candle", "candle_pattern", "signal_bar", "bar_pattern",
    "reversal_bar", "closed_bar", "candle_body", "candle_upper_wick", "candle_lower_wick", "candle_data_provenance", "rsi", "stochastic", "stoch",
    "oscillator", "oscillator_state", "rsi_state", "stochastic_k", "stochastic_state", "overbought", "oversold", "divergence",
    "price_oscillator_divergence", "momentum_divergence", "rsi_divergence", "macd_divergence",
    "hidden_divergence", "exhaustion", "climax", "ma_fast", "ma_slow", "ema_fast", "ema_slow",
    "sma_fast", "sma_slow", "ma_cross", "ema_cross", "ma_slope", "ema_fast_slope",
    "moving_average_state", "market_profile", "value_area", "poc", "opening_drive", "opening_type",
    "bollinger_middle", "bollinger_upper", "bollinger_lower", "bollinger_width", "bollinger_bandwidth",
    "bollinger_position", "bollinger_state", "bollinger_window_n", "macd_line", "macd_signal",
    "macd_histogram", "macd_state", "macd_cross", "macd_observation_n", "atr_14", "atr_percent",
    "atr_state", "atr_observation_n",
    "fib_retracement", "fib_retracement_zone", "fib_direction", "fib_236", "fib_382", "fib_500",
    "fib_618", "fib_786", "fib_data_provenance", "previous_session_high", "previous_session_low",
    "previous_session_close", "pivot", "pivot_r1", "pivot_s1", "pivot_r2", "pivot_s2", "pivot_relation",
    "pivot_data_provenance",
    "donchian_high", "donchian_low", "donchian_width", "donchian_state", "donchian_data_provenance",
    "adx", "di_plus", "di_minus", "adx_state", "adx_direction", "adx_observation_n",
    "keltner_middle", "keltner_upper", "keltner_lower", "keltner_width", "keltner_state", "keltner_observation_n",
    "tenkan_sen", "kijun_sen", "senkou_span_a", "senkou_span_b", "ichimoku_state", "ichimoku_observation_n",
    "cci", "cci_state", "cci_observation_n", "williams_r", "williams_state", "williams_observation_n",
    "vwap_proxy", "vwap_relation", "vwap_data_provenance", "obv_proxy", "obv_direction", "obv_data_provenance",
    "volume_observation_n",
    "roc", "roc_1", "roc_3", "roc_5", "roc_10", "roc_20", "roc_1s", "roc_3s", "roc_5s", "roc_10s", "roc_20s", "roc_state", "roc_direction",
    "roc_observation_provenance", "parabolic_sar", "sar", "sar_state", "sar_direction",
    "sar_flip", "sar_observation_n", "sar_data_provenance", "elliott_wave_state", "wave_state",
    "wave_count", "wave_direction", "wave_confirmation", "harmonic_pattern", "harmonic_direction",
    "harmonic_confirmation", "harmonic_ratios", "pattern_completion", "gann_state", "gann_direction",
    "gann_confirmation", "gann_level", "gann_angle", "gann_data_provenance", "pair_signal",
    "kalman_state", "kalman_residual", "kalman_zscore", "kalman_confirmation", "kalman_hedge_ratio",
    "seasonal_state", "seasonal_direction", "seasonal_expectancy", "seasonal_sample_n", "seasonal_period",
    "seasonal_validation", "seasonal_data_provenance", "order_book_imbalance", "depth_levels", "order_book_age_s",
    "fractional_diff_value", "fractional_diff_d", "fractional_diff_stationarity", "fractional_diff_observation_n",
    "fractional_diff_variance_ratio", "fractional_diff_data_provenance",
    "kalman_state", "kalman_residual", "kalman_zscore", "kalman_confirmation", "kalman_observation_n",
    "kalman_data_provenance",
    "garch_forecast", "garch_alpha", "garch_beta", "garch_model_status", "garch_observation_n", "garch_data_provenance",
    "stochastic_volatility_forecast", "stochastic_volatility_persistence", "stochastic_volatility_status",
    "stochastic_volatility_observation_n", "stochastic_volatility_data_provenance",
    "hawkes_buy_intensity", "hawkes_sell_intensity", "hawkes_model_status", "hawkes_confirmation",
    "hawkes_observation_n", "hawkes_data_provenance",
    "order_book_data_provenance", "bid_depth", "ask_depth", "volume_profile", "volume_profile_state",
    "volume_profile_direction", "volume_profile_data_provenance", "vah", "val",
    "macro_bias", "macro_event_risk", "macro_confirmation", "macro_data_provenance",
    "interest_rate_differential", "economic_surprise", "sentiment_bias", "positioning_bias",
    "sentiment_confirmation", "sentiment_data_provenance", "sentiment_sample_n", "crowding",
    "forecast_price", "forecast_current_price", "forecast_horizon_s", "forecast_model",
    "forecast_oos_status", "forecast_uncertainty", "ml_prediction", "ml_probability",
    "ml_artifact_status", "ml_calibration_status", "ml_authorized_symbols", "ml_horizon_s",
    "ml_feature_timestamp", "portfolio_state", "portfolio_impact", "marginal_risk",
    "correlation_to_open", "portfolio_bias", "portfolio_limit",
    "auction_state", "balance", "initiative", "opening_range_state", "opening_range_breakout",
    "initial_balance", "session_open", "opening_gap", "session_state", "liquidity", "market_open",
    "market_state", "news_state", "event_risk", "calendar_state", "high_impact_news",
    "scheduled_event", "spread_around_news", "macro_event", "liquidity_sweep", "stop_run",
    "equal_highs", "equal_lows", "sweep_state", "reclaim", "wick_rejection", "correlation",
    "correlation_state", "cross_asset", "intermarket", "beta", "hedge_ratio", "basket_direction",
    "risk_on_off", "dollar_index", "pair", "spread_zscore", "residual", "cointegration",
    "stationarity", "relative_value", "expected_net_ev", "commission_usd", "slippage_usd",
    "feature_provenance", "provenance",
    "pair_stationarity", "pair_zscore", "bollinger_entry_zscore", "bollinger_exit_zscore",
    "breakout_lookback", "breakout_high_10", "breakout_low_10", "breakout_sd", "breakout_buffer_sd",
    "current_price", "primary_trend", "intermediate_oscillator", "short_trigger",
    "vsa_pattern", "vsa_confirmation", "vsa_volume_ratio", "vsa_bar_spread", "vsa_data_provenance",
    "volume_context", "volume_data_provenance", "volume_provenance",
    "candlestick_pattern", "candlestick_confirmation", "initial_balance_high", "initial_balance_low",
    "profile_state", "initial_balance_status", "momentum_rank_percentile", "rank_universe_n",
    "momentum_direction", "ranking_as_of", "primary_signal", "meta_probability",
    "meta_calibration_status", "meta_oos_status", "meta_horizon_s", "force_index",
    "force_index_direction", "force_index_confirmation", "force_index_data_provenance", "ema_slope",
    "macd_histogram_slope", "impulse_state", "market_maker_signal", "inventory_state", "microprice",
    "mid_price", "spread_price", "forecast_values", "forecast_weights", "forecast_model",
    "forecast_oos_status", "forecast_current_price", "forecast_uncertainty", "forecast_oos_n",
    "forecast_mae", "forecast_rmse", "forecast_training_n", "forecast_training_last_time",
    "forecast_data_provenance",
    "label_entry_price", "upper_barrier", "lower_barrier", "label_horizon_s", "label_policy",
    "purge_gap_s", "max_label_horizon_s", "embargo_s", "validation_splits", "realized_volatility_window_s",
    "realized_volatility_observation_n", "fractional_diff_d", "fractional_diff_stationarity",
    "fractional_diff_observation_n", "risk_parity_weights", "risk_parity_covariance_status",
    "risk_parity_budget_status", "vwap_reference", "execution_average_price", "execution_side",
    "execution_volume", "vwap_data_provenance", "twap_reference", "schedule_elapsed_fraction",
    "schedule_status", "target_participation_rate", "actual_participation_rate", "market_volume",
    "ewma_fast", "ewma_slow", "ewmac_fast_lookback", "ewmac_slow_lookback", "ewmac_forecast",
    "carry_return_pct", "carry_funding_cost_pct", "carry_signal", "carry_data_provenance",
    "ab_mode", "ab_a", "ab_b", "ab_entry_price", "ab_deviation", "ab_high_since_entry", "ab_low_since_entry",
    "wyckoff_event", "wyckoff_confirmation", "wyckoff_volume_confirmation", "squeeze_state", "squeeze_direction",
    "squeeze_momentum", "squeeze_confirmation", "second_entry_direction", "second_entry_number",
    "second_entry_context", "second_entry_confirmation", "tail_direction", "tail_context", "tail_confirmation",
    "tail_wick_ratio", "relative_strength_ratio", "relative_strength_direction", "relative_strength_benchmark",
    "relative_strength_as_of", "pnf_pattern", "pnf_direction", "pnf_confirmation", "pnf_box_size",
    "pnf_reversal_boxes", "pnf_column_count", "pnf_observation_n", "pnf_data_provenance",
    "second_entry_bar_end_time", "second_entry_data_provenance", "cycle_state", "cycle_direction",
    "cycle_period", "cycle_confidence", "cycle_observation_n", "cycle_data_provenance",
    "factor_signal", "factor_score", "factor_rank_percentile", "factor_as_of", "signal_breadth",
    "information_coefficient", "transfer_coefficient", "fundamental_law_status", "order_size",
    "average_daily_volume", "estimated_market_impact", "impact_model_status", "garch_forecast",
    "garch_model_status", "garch_observation_n", "hawkes_buy_intensity", "hawkes_sell_intensity",
    "hawkes_model_status", "hawkes_confirmation",
    "turtle_entry_lookback", "turtle_exit_lookback", "turtle_high", "turtle_low", "turtle_confirmation",
    "target_volatility", "volatility_scalar", "volatility_target_status", "risk_budget_usd", "stop_distance",
    "value_per_price_unit", "sizing_status",
    "rf_prediction", "rf_probability", "rf_model_status", "rf_symbol", "rf_horizon_s",
    "bayesian_pair_status", "bayesian_spread_zscore", "bayesian_pair_signal", "bayesian_posterior_uncertainty",
    "pca_status", "pca_explained_variance", "pca_loading", "pca_portfolio_name", "bet_probability",
    "bet_payoff_ratio", "bet_sizing_cap", "bet_sizing_status", "feature_importance_stability",
    "feature_importance_oos_status", "feature_importance_observation_n", "stochastic_volatility_forecast",
    "stochastic_volatility_status", "stochastic_volatility_observation_n",
})
_NESTED_KEYS = frozenset({"context", "entry_state", "decision_snapshot", "candidate_details"})
_NUMERIC_OPS = {"gte": ">=", "gt": ">", "lte": "<=", "lt": "<", "eq": "=="}
_SUFFIX_RE = re.compile(r"^(?P<field>[a-z0-9_]+)_(?P<op>gte|gt|lte|lt|eq)$")

_REQUIRED_FEATURE_ALIASES = {
    "spread": ("spread", "spread_pips"),
    "moving_average": (
        "moving_average", "moving_average_state", "ma_fast", "ma_slow",
        "ema_fast", "ema_slow", "sma_fast", "sma_slow", "ma_cross", "ema_cross", "ma_slope",
    ),
    "oscillator": (
        "oscillator", "oscillator_state", "rsi", "stochastic", "stoch",
        "macd_line", "macd_state", "macd_histogram", "cci", "williams_r",
    ),
    "momentum": (
        "momentum", "momentum_context", "momentum_persistence", "roc", "roc_5",
        "roc_5s", "tick_velocity", "price_acceleration",
    ),
    "structure": (
        "structure", "structure_state", "breakout", "breakout_state", "range_state",
        "channel_state", "pattern_state",
    ),
    "volume": (
        "volume", "volume_ratio", "relative_volume", "tick_volume", "tick_activity",
        "tick_activity_ratio", "vsa_volume_ratio", "obv_proxy",
    ),
    "volatility": (
        "volatility", "realized_volatility", "micro_volatility", "volatility_state",
        "volatility_expansion", "atr", "atr_14",
    ),
}


def _finite(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return number if math.isfinite(number) else None


def _clean(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _clean(item) for key, item in value.items() if str(key) not in {"future_quote", "quotes", "counterfactual_quotes"}}
    if isinstance(value, (list, tuple)):
        return [_clean(item) for item in value]
    number = _finite(value)
    if isinstance(value, (int, float)) and number is not None:
        return number
    return value


def compact_context_event(event: Mapping[str, Any]) -> dict[str, Any]:
    """Keep only pre-entry fields and hash their canonical representation."""
    source: dict[str, Any] = {}
    for key, value in event.items():
        if key in _DIRECT_KEYS or key in _SAFE_DERIVED_KEYS or key.startswith("return_"):
            source[key] = value
        elif key in _NESTED_KEYS and isinstance(value, Mapping):
            for nested_key, nested_value in value.items():
                if (
                    nested_key in _DIRECT_KEYS
                    or nested_key in _SAFE_DERIVED_KEYS
                    or nested_key.startswith("return_")
                    or nested_key.startswith("tick_")
                ):
                    source.setdefault(nested_key, nested_value)
    if "spread" not in source and "spread_pips" in source:
        source["spread"] = source["spread_pips"]
    snapshot = _clean(source)
    if not isinstance(snapshot, dict):  # defensive; source is always a dict
        snapshot = {}
    encoded = json.dumps(snapshot, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)
    snapshot["context_hash"] = hashlib.sha256(encoded.encode("utf-8")).hexdigest()
    return snapshot


def _lookup(context: Mapping[str, Any], field: str) -> Any:
    if field in context:
        return context[field]
    for key in ("m1_context", "m5_context", "m15_context", "short_returns", "volatility_context"):
        nested = context.get(key)
        if isinstance(nested, Mapping) and field in nested:
            return nested[field]
    return None


def _has_value(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, Mapping):
        return bool(value)
    return True


def _required_feature_present(context: Mapping[str, Any], feature: Any) -> bool:
    normalized = re.sub(r"[\s-]+", "_", str(feature or "").strip().lower())
    aliases = _REQUIRED_FEATURE_ALIASES.get(normalized, (normalized,))
    if normalized == "volume" and _volume_is_explicit_proxy(context):
        return False
    return bool(normalized) and any(_has_value(_lookup(context, alias)) for alias in aliases)


def _volume_is_explicit_proxy(context: Mapping[str, Any]) -> bool:
    nested = context.get("volume_context")
    if isinstance(nested, Mapping):
        if nested.get("is_real_volume") is False:
            return True
        sources = (nested.get("source"), nested.get("provenance"), nested.get("data_provenance"))
    else:
        sources = ()
    sources = (*sources, context.get("volume_data_provenance"), context.get("volume_provenance"))
    for source in sources:
        label = str(source or "").strip().lower()
        if any(token in label for token in ("proxy", "tick volume", "tick_activity", "tick activity")):
            return True
    return False


def _split_rule(key: str, value: Any) -> tuple[str, str, Any]:
    match = _SUFFIX_RE.match(key)
    if match:
        return match.group("field"), match.group("op"), value
    if key.endswith("_max"):
        return key[:-4], "lte", value
    if key.endswith("_min"):
        return key[:-4], "gte", value
    if key.endswith("_in"):
        return key[:-3], "in", value
    return key, "eq", value


def _comparison(actual: Any, op: str, expected: Any) -> tuple[bool, str | None]:
    if op in _NUMERIC_OPS:
        left = _finite(actual)
        right = _finite(expected)
        if left is None or right is None:
            if op == "eq":
                return str(actual).lower() == str(expected).lower(), None
            return False, "non_numeric_value"
        if op == "gte":
            return left >= right, None
        if op == "gt":
            return left > right, None
        if op == "lte":
            return left <= right, None
        if op == "lt":
            return left < right, None
        return left == right, None
    if op == "in":
        expected_values = expected if isinstance(expected, (list, tuple, set, frozenset)) else [expected]
        return str(actual).lower() in {str(item).lower() for item in expected_values}, None
    if isinstance(actual, str) or isinstance(expected, str):
        return str(actual).lower() == str(expected).lower(), None
    return actual == expected, None


def evaluate_compiled_strategy(strategy: Mapping[str, Any], context: Mapping[str, Any]) -> dict[str, Any]:
    """Evaluate an allow-listed compiled rule without execution authority."""
    status = str(strategy.get("status") or "").upper()
    result: dict[str, Any] = {
        "evidence_status": status or "UNCLASSIFIED",
        "execution_authority": False,
        "uses_future_data": False,
        "failed_predicates": [],
        "missing": [],
    }
    if status != "CODED_EXACT":
        result.update({"status": "CONTEXT_ONLY", "evaluation_status": "CONTEXT_ONLY", "reason": "non_exact_strategy"})
        return result
    side_rule = str(strategy.get("side_rule") or "").upper()
    current_side = str(_lookup(context, "side") or "").upper()
    if side_rule and current_side and side_rule != current_side:
        result["failed_predicates"].append("side_rule")
    elif side_rule and not current_side:
        result["missing"].append("side")
    algorithm = strategy.get("algorithm")
    compiled = algorithm.get("compiled_entry_predicates") if isinstance(algorithm, Mapping) else None
    if not isinstance(compiled, Mapping):
        compiled = strategy.get("compiled_rule")
    if not isinstance(compiled, Mapping):
        result.update({"status": "EVALUATION_ERROR", "evaluation_status": "COMPILE_ERROR", "reason": "missing_compiled_rule"})
        return result
    required_features = strategy.get("required_features") or ()
    if isinstance(required_features, str):
        required_features = (required_features,)
    for feature in required_features:
        feature_name = str(feature).strip().lower()
        if feature_name and not _required_feature_present(context, feature_name):
            result["missing"].append(feature_name)
    for key, expected in compiled.items():
        field, op, target = _split_rule(str(key), expected)
        actual = _lookup(context, field)
        if actual is None or actual == "":
            result["missing"].append(field)
            continue
        passed, error = _comparison(actual, op, target)
        if error:
            result["failed_predicates"].append(f"{key}:{error}")
        elif not passed:
            result["failed_predicates"].append(key)
    result["missing"] = list(dict.fromkeys(result["missing"]))
    if result["missing"]:
        result.update({"status": "MISSING_INPUT", "evaluation_status": "MISSING_INPUT", "reason": "missing_required_input"})
    elif result["failed_predicates"]:
        result.update({"status": "NO_MATCH", "evaluation_status": "NO_MATCH", "reason": "predicate_failed"})
    else:
        result.update({"status": "MATCH", "evaluation_status": "MATCH", "reason": "all_predicates_satisfied"})
    return result


def evaluate_strategy_evidence(
    record: Mapping[str, Any],
    state: Mapping[str, Any],
    *,
    context_snapshot: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Evaluate one record, reusing a row snapshot when replaying groups."""
    snapshot = (
        context_snapshot
        if isinstance(context_snapshot, Mapping)
        else compact_context_event(state)
    )
    strategy_status = str(record.get("status") or record.get("validation_status") or "UNCLASSIFIED").upper()
    if strategy_status != "CODED_EXACT":
        return {
            "evaluation_status": "CONTEXT_ONLY",
            "evidence_status": strategy_status,
            "reason": "non_exact_strategy",
            "context_hash": snapshot["context_hash"],
            "execution_authority": False,
            "uses_future_data": False,
        }
    result = evaluate_compiled_strategy(record, snapshot)
    result["context_hash"] = snapshot["context_hash"]
    return result


__all__ = ["compact_context_event", "evaluate_compiled_strategy", "evaluate_strategy_evidence"]
