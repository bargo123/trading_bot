"""Data pipeline for research factory."""
from __future__ import annotations

import json
import hashlib
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class DataSource:
    """An immutable reference to a persisted market-data source."""

    path: Path
    symbol: str
    timeframe: str
    source_kind: str
    quality: str
    metadata_path: Optional[Path]


_KNOWN_TIMEFRAMES = frozenset({"1m", "5m", "15m", "30m", "1h", "4h", "1d"})


def _identity_from_filename(path: Path) -> Tuple[Optional[str], Optional[str]]:
    parts = path.stem.split("_")
    timeframe = next((part for part in parts if part in _KNOWN_TIMEFRAMES), None)
    symbol = parts[0] if parts and parts[0] else None
    return symbol, timeframe


def discover_csv_sources(roots: Sequence[Path]) -> List[DataSource]:
    """Discover persisted CSV sources without inventing fallback data."""
    paths = sorted(
        {csv_path for root in roots for csv_path in Path(root).rglob("*.csv")},
        key=lambda path: str(path),
    )
    sources = []
    for csv_path in paths:
        metadata_path = csv_path.with_suffix(".json")
        metadata: Dict[str, Any] = {}
        if metadata_path.is_file():
            try:
                loaded = json.loads(metadata_path.read_text(encoding="utf-8"))
                if not isinstance(loaded, dict):
                    raise ValueError("metadata must be a JSON object")
                metadata = loaded
            except (OSError, UnicodeError, ValueError) as exc:
                logger.warning("Failed to read metadata %s: %s", metadata_path, exc)
                continue

        filename_symbol, filename_timeframe = _identity_from_filename(csv_path)
        symbol = metadata.get("symbol") or filename_symbol
        timeframe = (
            metadata.get("timeframe")
            or metadata.get("actual_interval")
            or metadata.get("requested_interval")
            or filename_timeframe
        )
        if not symbol or timeframe not in _KNOWN_TIMEFRAMES:
            logger.warning("Could not identify source %s", csv_path)
            continue

        sources.append(
            DataSource(
                path=csv_path,
                symbol=str(symbol),
                timeframe=str(timeframe),
                source_kind=str(metadata.get("source") or "csv"),
                quality=str(metadata.get("quality") or "unknown"),
                metadata_path=metadata_path if metadata_path.is_file() else None,
            )
        )
    return sources


@dataclass
class DatasetSplit:
    """Chronological data split."""
    train: pd.DataFrame
    validation: pd.DataFrame
    test: pd.DataFrame
    sealed_holdout: pd.DataFrame
    split_info: Dict[str, Any]


@dataclass
class FeatureSet:
    """Engineered feature set."""
    features: pd.DataFrame
    labels: pd.DataFrame
    feature_names: List[str]
    label_names: List[str]
    feature_metadata: Dict[str, Any]


class DataPipeline:
    """Canonical point-in-time data pipeline."""

    def __init__(
        self,
        train_ratio: float = 0.6,
        validation_ratio: float = 0.2,
        test_ratio: float = 0.15,
        sealed_ratio: float = 0.05,
        min_train_size: int = 1000,
    ):
        self.train_ratio = train_ratio
        self.validation_ratio = validation_ratio
        self.test_ratio = test_ratio
        self.sealed_ratio = sealed_ratio
        self.min_train_size = min_train_size

        # Verify ratios sum to 1
        total = train_ratio + validation_ratio + test_ratio + sealed_ratio
        if abs(total - 1.0) > 1e-6:
            raise ValueError(f"Ratios must sum to 1.0, got {total}")

    def load_raw_data(
        self,
        data_dir: Path,
        symbols: Optional[List[str]] = None,
        timeframes: Optional[List[str]] = None,
    ) -> pd.DataFrame:
        """Load and combine all available historical data."""
        sources = discover_csv_sources([data_dir])
        if symbols:
            sources = [source for source in sources if source.symbol in symbols]
        if timeframes:
            sources = [source for source in sources if source.timeframe in timeframes]
        return self.load_sources(sources)

    def load_sources(self, sources: Sequence[DataSource]) -> pd.DataFrame:
        """Load real source rows with point-in-time provenance."""
        frames = []

        for source in sources:
            try:
                df = pd.read_csv(source.path)
                if "time" not in df.columns:
                    raise ValueError("missing time column")
                df["time"] = pd.to_datetime(df["time"], utc=True, errors="coerce")
                df = df.dropna(subset=["time"])
                if df.empty:
                    continue
                df["source_file"] = str(source.path)
                df["source_kind"] = source.source_kind
                df["source_quality"] = source.quality
                df["symbol"] = source.symbol
                df["timeframe"] = source.timeframe
                frames.append(df)
                logger.info("Loaded %s: %s rows", source.path.name, len(df))

            except (OSError, UnicodeError, ValueError, pd.errors.ParserError) as exc:
                logger.warning("Failed to load %s: %s", source.path, exc)

        if not frames:
            logger.warning("No data files loaded")
            return pd.DataFrame()

        combined = pd.concat(frames, ignore_index=True)
        combined = combined.sort_values(
            ["symbol", "timeframe", "time"], kind="stable"
        ).reset_index(drop=True)

        logger.info(f"Loaded {len(combined)} total rows from {len(frames)} files")
        return combined

    def create_splits(
        self,
        df: pd.DataFrame,
        time_column: str = "time",
    ) -> DatasetSplit:
        """Create chronological train/validation/test/sealed splits."""
        if df.empty:
            raise ValueError("Cannot split empty DataFrame")

        if time_column not in df.columns:
            raise ValueError(f"Time column '{time_column}' not found")

        df = df.sort_values(time_column).reset_index(drop=True)
        n = len(df)

        if n < self.min_train_size:
            raise ValueError(f"Dataset too small: {n} rows, minimum {self.min_train_size}")

        # Calculate split indices
        train_end = int(len(df) * self.train_ratio)
        val_end = train_end + int(len(df) * self.validation_ratio)
        test_end = val_end + int(len(df) * self.test_ratio)

        train = df.iloc[:train_end].copy()
        validation = df.iloc[train_end:train_end + int(len(df) * self.validation_ratio)].copy()
        test = df.iloc[train_end + int(len(df) * self.validation_ratio):test_end].copy()
        sealed_holdout = df.iloc[test_end:].copy()

        split_info = {
            "total_rows": len(df),
            "train_rows": len(train),
            "validation_rows": len(validation),
            "test_rows": len(test),
            "sealed_rows": len(sealed_holdout),
            "train_date_range": f"{train[time_column].min()} to {train[time_column].max()}" if len(train) > 0 else "empty",
            "validation_date_range": f"{validation[time_column].min()} to {validation[time_column].max()}" if len(validation) > 0 else "empty",
            "test_date_range": f"{test[time_column].min()} to {test[time_column].max()}" if len(test) > 0 else "empty",
            "sealed_date_range": f"{sealed_holdout[time_column].min()} to {sealed_holdout[time_column].max()}" if len(sealed_holdout) > 0 else "empty",
        }

        logger.info(f"Data splits: {split_info}")

        return DatasetSplit(
            train=train,
            validation=validation,
            test=test,
            sealed_holdout=sealed_holdout,
            split_info=split_info,
        )

    def verify_no_lookahead(self, df: pd.DataFrame, time_column: str = "time") -> bool:
        """Verify no lookahead in features."""
        if "time" not in df.columns:
            return True

        # Check that all features at time t only use data available at or before t
        # This is a simplified check - in practice would need feature-specific validation
        df = df.sort_values(time_column).reset_index(drop=True)

        # Check for future timestamps in features
        future_cols = [c for c in df.columns if "future" in c.lower() or "forward" in c.lower()]
        if future_cols:
            logger.warning(f"Potential lookahead columns found: {future_cols}")
            return False

        return True

    def compute_dataset_fingerprint(self, df: pd.DataFrame) -> str:
        """Compute deterministic fingerprint of dataset."""
        if df.empty:
            return "empty"

        columns = sorted(df.columns, key=str)
        canonical = df.loc[:, columns].copy()
        for column in columns:
            if pd.api.types.is_datetime64_any_dtype(canonical[column].dtype):
                canonical[column] = pd.to_datetime(
                    canonical[column], utc=True, errors="coerce"
                ).astype("datetime64[ns, UTC]")

        schema = json.dumps(
            [(str(column), str(canonical[column].dtype)) for column in columns],
            separators=(",", ":"),
        ).encode("utf-8")
        row_hashes = np.sort(
            pd.util.hash_pandas_object(canonical, index=False).to_numpy()
        )

        digest = hashlib.sha256()
        digest.update(schema)
        digest.update(row_hashes.tobytes())
        return digest.hexdigest()[:16]


class FeatureEngineer:
    """Point-in-time feature engineering."""

    def __init__(self):
        self.feature_names: List[str] = []
        self.feature_metadata: Dict[str, Dict[str, Any]] = {}

    def engineer(
        self,
        df: pd.DataFrame,
        label_horizon: int = 20,
        fit_scalers: bool = True,
        scaler_dict: Optional[Dict[str, Any]] = None,
    ) -> FeatureSet:
        """Engineer features with point-in-time correctness."""
        if df.empty:
            return FeatureSet(
                features=pd.DataFrame(),
                labels=pd.DataFrame(),
                feature_names=[],
                label_names=[],
                feature_metadata={},
            )

        df = df.copy()

        # Ensure time column
        if "time" not in df.columns:
            raise ValueError("DataFrame must have 'time' column")

        df["time"] = pd.to_datetime(df["time"], utc=True)
        df = df.sort_values("time").reset_index(drop=True)

        features_df = df.copy()
        labels_df = pd.DataFrame(index=df.index)

        # Price features
        self._add_price_features(features_df)
        # Volatility features
        self._add_volatility_features(features_df)
        # Structure features
        self._add_structure_features(features_df)
        # Multi-timeframe features
        self._add_multitimeframe_features(features_df)
        # Time/session features
        self._add_time_features(features_df)
        # Microstructure features (if available)
        self._add_microstructure_features(features_df)

        # Create labels with lookahead
        labels_df = self._create_labels(features_df, horizon=label_horizon)

        # Store feature names (exclude metadata columns)
        exclude_cols = {"time", "source_file", "symbol", "timeframe"}
        feature_cols = [c for c in features_df.columns if c not in labels_df.columns and c not in {"time", "source_file", "symbol", "timeframe"}]
        label_cols = list(labels_df.columns)

        self.feature_names = feature_cols
        self.feature_metadata = {
            name: {"type": str(features_df[name].dtype), "description": ""}
            for name in feature_cols
        }

        # Handle NaN/Inf
        features_clean = features_df[feature_cols].replace([np.inf, -np.inf], np.nan).fillna(0)

        return FeatureSet(
            features=features_clean,
            labels=labels_df[label_cols],
            feature_names=feature_cols,
            label_names=label_cols,
            feature_metadata=self.feature_metadata,
        )

    def _add_price_features(self, df: pd.DataFrame) -> None:
        """Add price-based features."""
        # Returns
        df["returns"] = df.groupby("symbol")["close"].pct_change()
        df["log_returns"] = np.log(df["close"] / df.groupby("symbol")["close"].shift(1))

        # Momentum
        for window in [1, 3, 5, 10, 15, 30]:
            df[f"momentum_{window}"] = df.groupby("symbol")["close"].pct_change(window)

        # Acceleration
        df["acceleration"] = df.groupby("symbol")["returns"].diff()

        # Distance from open
        df["dist_from_open"] = (df["close"] - df["open"]) / df["open"].replace(0, np.nan)

    def _add_volatility_features(self, df: pd.DataFrame) -> None:
        """Add volatility features."""
        df["range"] = (df["high"] - df["low"]) / df["close"].replace(0, np.nan)
        df["body_size"] = abs(df["close"] - df["open"]) / df["close"].replace(0, np.nan)
        df["upper_wick"] = (df["high"] - df[["open", "close"]].max(axis=1)) / df["close"].replace(0, np.nan)
        df["lower_wick"] = (df[["open", "close"]].min(axis=1) - df["low"]) / df["close"].replace(0, np.nan)

        # ATR
        df["tr"] = np.maximum(
            df["high"] - df["low"],
            np.maximum(
                abs(df["high"] - df.groupby("symbol")["close"].shift(1)),
                abs(df["low"] - df.groupby("symbol")["close"].shift(1))
            )
        )
        for window in [14, 30]:
            df[f"atr_{window}"] = df.groupby("symbol")["tr"].rolling(window).mean().reset_index(level=0, drop=True)

        # Realized volatility
        for window in [10, 20, 50]:
            df[f"realized_vol_{window}"] = df.groupby("symbol")["returns"].rolling(window).std().reset_index(level=0, drop=True)

    def _add_structure_features(self, df: pd.DataFrame) -> None:
        """Add market structure features."""
        # Range position
        df["range_position"] = (df["close"] - df["low"]) / (df["high"] - df["low"]).replace(0, np.nan)

        # Distance from high/low
        df["dist_from_high"] = (df["high"] - df["close"]) / df["close"].replace(0, np.nan)
        df["dist_from_low"] = (df["close"] - df["low"]) / df["close"].replace(0, np.nan)

        # Rolling support/resistance
        for window in [20, 50, 100]:
            df[f"resistance_{window}"] = df.groupby("symbol")["high"].rolling(window).max().reset_index(level=0, drop=True)
            df[f"support_{window}"] = df.groupby("symbol")["low"].rolling(window).min().reset_index(level=0, drop=True)
            df[f"dist_to_resistance_{window}"] = (df[f"resistance_{window}"] - df["close"]) / df["close"]
            df[f"dist_to_support_{window}"] = (df["close"] - df[f"support_{window}"]) / df["close"]

    def _add_multitimeframe_features(self, df: pd.DataFrame) -> None:
        """Add multi-timeframe features using rolling windows."""
        for window in [5, 15, 30, 60, 120, 240]:
            # SMA
            df[f"sma_{window}"] = df.groupby("symbol")["close"].rolling(window).mean().reset_index(level=0, drop=True)
            df[f"ema_{window}"] = df.groupby("symbol")["close"].ewm(span=window).mean().reset_index(level=0, drop=True)

            # Distance from MA
            df[f"dist_sma_{window}"] = (df["close"] - df[f"sma_{window}"]) / df[f"sma_{window}"]
            df[f"dist_ema_{window}"] = (df["close"] - df[f"ema_{window}"]) / df[f"ema_{window}"]

            # MA slope
            df[f"sma_slope_{window}"] = df.groupby("symbol")[f"sma_{window}"].diff()

    def _add_time_features(self, df: pd.DataFrame) -> None:
        """Add time/session features."""
        if "time" not in df.columns:
            return

        dt = pd.to_datetime(df["time"])
        df["hour"] = dt.dt.hour
        df["day_of_week"] = dt.dt.dayofweek
        df["day_of_month"] = dt.dt.day
        df["month"] = dt.dt.month
        df["quarter"] = dt.dt.quarter
        df["is_month_end"] = dt.dt.is_month_end.astype(int)
        df["is_quarter_end"] = dt.dt.is_quarter_end.astype(int)

        # Session
        def get_session(hour):
            if 0 <= hour < 8:
                return "asia"
            elif 8 <= hour < 16:
                return "london"
            else:
                return "newyork"

        df["session"] = df["hour"].apply(get_session)

        # Session progress (0-1 within session)
        session_start = df["session"].map({"asia": 0, "london": 8, "newyork": 16})
        df["session_progress"] = (df["hour"] - session_start) / 8

        # Session transitions
        df["session_transition"] = (df["session"] != df["session"].shift(1)).astype(int)

    def _add_microstructure_features(self, df: pd.DataFrame) -> None:
        """Add microstructure features if spread/bid/ask available."""
        if "spread" in df.columns:
            df["spread_pct"] = df["spread"] / df["close"]
            df["spread_zscore"] = df.groupby("symbol")["spread"].transform(
                lambda x: (x - x.rolling(100).mean()) / x.rolling(100).std()
            )

        if "bid" in df.columns and "ask" in df.columns:
            df["mid_price"] = (df["bid"] + df["ask"]) / 2
            df["spread_abs"] = df["ask"] - df["bid"]

        if "volume" in df.columns:
            df["volume_zscore"] = df.groupby("symbol")["volume"].transform(
                lambda x: (x - x.rolling(100).mean()) / x.rolling(100).std()
            )
            df["volume_change"] = df.groupby("symbol")["volume"].pct_change()

    def _create_labels(self, df: pd.DataFrame, horizon: int = 20) -> pd.DataFrame:
        """Create outcome labels with no lookahead bias."""
        labels = pd.DataFrame(index=df.index)

        # Get symbol for grouping
        symbols = df["symbol"] if "symbol" in df.columns else pd.Series("UNKNOWN", index=df.index)

        # Forward-looking labels (using shift to avoid lookahead)
        # These are labels that WOULD be known after horizon bars
        # In production, these are computed during replay/backtest

        # Future price extremes
        future_high = df.groupby(symbols)["high"].shift(-horizon).rolling(horizon).max()
        future_low = df.groupby(symbols)["low"].shift(-horizon).rolling(horizon).min()

        # Profit barrier first
        labels["profit_barrier_first"] = (
            (future_high - df["close"]) > (df["close"] - future_low)
        ).astype(int)

        # MFE and MAE
        labels["mfe"] = future_high - df["close"]
        labels["mae"] = df["close"] - future_low

        # Time to target (simplified)
        labels["time_to_target"] = horizon

        # No progress
        labels["no_progress"] = (labels["mfe"] < 1e-6).astype(int)

        # Tail loss probability
        mae_threshold = labels["mae"].quantile(0.95)
        labels["tail_loss"] = (labels["mae"] > mae_threshold).astype(int)

        # Direction
        labels["direction"] = np.where(df["close"] > df["open"], 1, -1)

        # Return over horizon
        labels["return_horizon"] = (df["close"].shift(-horizon) / df["close"] - 1)

        # Fill NaN labels with 0/neutral
        label_cols = labels.columns
        for col in label_cols:
            if labels[col].dtype in [np.float64, np.float32]:
                labels[col] = labels[col].fillna(0)
            elif labels[col].dtype in [np.int64, np.int32]:
                labels[col] = labels[col].fillna(0)

        return labels


class LabelEncoder:
    """Encode labels for ML training."""

    @staticmethod
    def encode_binary(labels: pd.Series) -> np.ndarray:
        """Encode binary labels."""
        return labels.astype(int).values

    @staticmethod
    def encode_multiclass(labels: pd.Series) -> np.ndarray:
        """Encode multiclass labels."""
        return labels.astype(int).values

    @staticmethod
    def decode_binary(predictions: np.ndarray, threshold: float = 0.5) -> np.ndarray:
        """Decode binary predictions."""
        return (predictions >= threshold).astype(int)

    @staticmethod
    def decode_multiclass(predictions: np.ndarray) -> np.ndarray:
        """Decode multiclass predictions."""
        return predictions.argmax(axis=1)


def load_market_data(
    data_dir: Path,
    symbols: Optional[List[str]] = None,
) -> pd.DataFrame:
    """Load market data from CSV files."""
    pipeline = DataPipeline()
    return pipeline.load_raw_data(data_dir, symbols)


def create_research_splits(
    df: pd.DataFrame,
    train_ratio: float = 0.6,
    validation_ratio: float = 0.2,
    test_ratio: float = 0.15,
    sealed_ratio: float = 0.05,
) -> DatasetSplit:
    """Create chronological splits."""
    pipeline = DataPipeline(train_ratio, validation_ratio, test_ratio, sealed_ratio)
    return pipeline.create_splits(df)


def engineer_features(
    df: pd.DataFrame,
    label_horizon: int = 20,
) -> FeatureSet:
    """Engineer features with point-in-time correctness."""
    engineer = FeatureEngineer()
    return engineer.engineer(df, label_horizon=label_horizon)
