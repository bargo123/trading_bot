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


class InsufficientDataError(ValueError):
    """Raised when valid inputs cannot produce usable supervised partitions."""


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
    canonical: pd.DataFrame
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

        key_columns = ["symbol", "timeframe", "time"]
        provenance_columns = ["source_file", "source_kind", "source_quality"]
        duplicate_rows = combined.duplicated(key_columns, keep=False)
        drop_indices = []
        for key, group in combined.loc[duplicate_rows].groupby(
            key_columns, sort=False, dropna=False
        ):
            market_columns = [
                column
                for column in combined.columns
                if column not in provenance_columns and column not in key_columns
            ]
            conflicting = [
                column
                for column in market_columns
                if group[column].nunique(dropna=False) > 1
            ]
            if conflicting:
                symbol, timeframe, timestamp = key
                raise ValueError(
                    "Conflicting duplicate observations for "
                    f"symbol={symbol}, timeframe={timeframe}, time={timestamp}; "
                    f"columns={conflicting}"
                )

            keep_index = group.index[0]
            for column in provenance_columns:
                combined.at[keep_index, column] = "|".join(
                    sorted({str(value) for value in group[column].dropna()})
                )
            drop_indices.extend(group.index[1:])

        if drop_indices:
            combined = combined.drop(index=drop_indices).reset_index(drop=True)

        logger.info(f"Loaded {len(combined)} total rows from {len(frames)} files")
        return combined

    def create_splits(
        self,
        df: pd.DataFrame,
        *,
        label_horizon: int,
    ) -> DatasetSplit:
        """Create timestamp-safe chronological splits with boundary purges."""
        if df.empty:
            raise ValueError("Cannot split empty DataFrame")

        if "time" not in df.columns:
            raise ValueError("Time column 'time' not found")
        if (
            isinstance(label_horizon, bool)
            or not isinstance(label_horizon, int)
            or label_horizon <= 0
        ):
            raise ValueError("label_horizon must be a positive integer")
        group_columns = ["symbol", "timeframe"]
        missing_group_columns = [
            column for column in group_columns if column not in df.columns
        ]
        if missing_group_columns:
            raise ValueError(
                f"DataFrame missing grouping columns: {missing_group_columns}"
            )

        df = df.copy()
        df["time"] = pd.to_datetime(df["time"], utc=True)
        df = df.sort_values(
            ["time", *group_columns], kind="stable"
        ).reset_index(drop=True)

        timestamps = pd.Index(df["time"].drop_duplicates().sort_values())
        train_end = int(len(timestamps) * self.train_ratio)
        validation_end = train_end + int(
            len(timestamps) * self.validation_ratio
        )
        test_end = validation_end + int(len(timestamps) * self.test_ratio)
        if not 0 < train_end < validation_end < test_end < len(timestamps):
            raise InsufficientDataError(
                "Ratios produce empty timestamp partitions for this dataset"
            )

        timestamp_partitions = (
            timestamps[:train_end],
            timestamps[train_end:validation_end],
            timestamps[validation_end:test_end],
            timestamps[test_end:],
        )
        partitions = [
            df.loc[df["time"].isin(partition)].copy()
            for partition in timestamp_partitions
        ]

        purged_rows = 0
        for partition_index in range(3):
            partition = partitions[partition_index]
            position = partition.groupby(
                group_columns, sort=False, observed=True
            ).cumcount()
            group_size = partition.groupby(
                group_columns, sort=False, observed=True
            )["time"].transform("size")
            keep = position < (group_size - label_horizon)
            purged_rows += int((~keep).sum())
            partitions[partition_index] = partition.loc[keep].copy()

        dropped_target_rows = 0
        if "profit_barrier_first" in df.columns:
            for partition_index, partition in enumerate(partitions):
                known_target = partition["profit_barrier_first"].notna()
                dropped_target_rows += int((~known_target).sum())
                partitions[partition_index] = partition.loc[known_target].copy()

        train, validation, test, sealed_holdout = partitions
        partition_names = ("train", "validation", "test", "sealed_holdout")
        empty_partitions = [
            name
            for name, partition in zip(partition_names, partitions)
            if partition.empty
        ]
        if empty_partitions:
            raise InsufficientDataError(
                "Unusable split after purge and target filtering; "
                f"empty partitions: {empty_partitions}"
            )
        if len(train) < self.min_train_size:
            raise InsufficientDataError(
                "Training partition too small after purge and target filtering: "
                f"{len(train)} rows, minimum {self.min_train_size}"
            )

        def timestamp_bound(partition: pd.DataFrame) -> Dict[str, Optional[str]]:
            if partition.empty:
                return {"start": None, "end": None}
            return {
                "start": partition["time"].min().isoformat(),
                "end": partition["time"].max().isoformat(),
            }

        timestamp_bounds = {
            "train": timestamp_bound(train),
            "validation": timestamp_bound(validation),
            "test": timestamp_bound(test),
            "sealed_holdout": timestamp_bound(sealed_holdout),
        }

        split_info = {
            "total_rows": len(df),
            "train_rows": len(train),
            "validation_rows": len(validation),
            "test_rows": len(test),
            "sealed_rows": len(sealed_holdout),
            "label_horizon": label_horizon,
            "purged_rows": purged_rows,
            "dropped_target_rows": dropped_target_rows,
            "timestamp_bounds": timestamp_bounds,
            "train_date_range": f"{train['time'].min()} to {train['time'].max()}" if len(train) > 0 else "empty",
            "validation_date_range": f"{validation['time'].min()} to {validation['time'].max()}" if len(validation) > 0 else "empty",
            "test_date_range": f"{test['time'].min()} to {test['time'].max()}" if len(test) > 0 else "empty",
            "sealed_date_range": f"{sealed_holdout['time'].min()} to {sealed_holdout['time'].max()}" if len(sealed_holdout) > 0 else "empty",
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
        columns = sorted(df.columns, key=str)
        canonical = df.loc[:, columns].copy()
        for column in columns:
            if pd.api.types.is_datetime64_any_dtype(canonical[column].dtype):
                canonical[column] = pd.to_datetime(
                    canonical[column], utc=True, errors="coerce"
                ).astype("datetime64[ns, UTC]")
            canonical[column] = canonical[column].mask(
                canonical[column].isna(), np.nan
            )

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
        return digest.hexdigest()


class FeatureEngineer:
    """Point-in-time feature engineering."""

    _GROUP_KEYS = ["symbol", "timeframe"]
    _METADATA_COLUMNS = [
        "time",
        "source_file",
        "source_kind",
        "source_quality",
        "symbol",
        "timeframe",
    ]

    def __init__(self):
        self.feature_names: List[str] = []
        self.feature_metadata: Dict[str, Dict[str, Any]] = {}

    def engineer(
        self,
        df: pd.DataFrame,
        *,
        profit_barrier_pct: float,
        loss_barrier_pct: float,
        label_horizon: int = 20,
        fit_scalers: bool = True,
        scaler_dict: Optional[Dict[str, Any]] = None,
    ) -> FeatureSet:
        """Engineer features with point-in-time correctness."""
        profit_barrier_pct = self._validate_barrier(
            "profit_barrier_pct", profit_barrier_pct
        )
        loss_barrier_pct = self._validate_barrier(
            "loss_barrier_pct", loss_barrier_pct
        )
        if (
            isinstance(label_horizon, bool)
            or not isinstance(label_horizon, int)
            or label_horizon <= 0
        ):
            raise ValueError("label_horizon must be a positive integer")

        if df.empty:
            return FeatureSet(
                canonical=pd.DataFrame(),
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
        missing_group_columns = [
            column for column in self._GROUP_KEYS if column not in df.columns
        ]
        if missing_group_columns:
            raise ValueError(
                f"DataFrame missing grouping columns: {missing_group_columns}"
            )

        df["time"] = pd.to_datetime(df["time"], utc=True)
        df = df.sort_values(
            [*self._GROUP_KEYS, "time"], kind="stable"
        ).reset_index(drop=True)

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
        labels_df = self._create_labels(
            features_df,
            horizon=label_horizon,
            profit_barrier_pct=profit_barrier_pct,
            loss_barrier_pct=loss_barrier_pct,
        )

        # Store feature names (exclude metadata columns)
        metadata_cols = [
            column for column in self._METADATA_COLUMNS if column in features_df.columns
        ]
        feature_cols = [
            column
            for column in features_df.columns
            if column not in metadata_cols and column not in labels_df.columns
        ]
        label_cols = list(labels_df.columns)

        self.feature_names = feature_cols
        self.feature_metadata = {
            name: {"type": str(features_df[name].dtype), "description": ""}
            for name in feature_cols
        }

        features_clean = features_df[feature_cols].replace(
            [np.inf, -np.inf], np.nan
        )
        canonical = pd.concat(
            [features_df[metadata_cols], features_clean, labels_df[label_cols]], axis=1
        )

        return FeatureSet(
            canonical=canonical,
            features=features_clean,
            labels=labels_df[label_cols],
            feature_names=feature_cols,
            label_names=label_cols,
            feature_metadata=self.feature_metadata,
        )

    @staticmethod
    def _validate_barrier(name: str, value: Optional[float]) -> float:
        if value is None:
            raise ValueError(f"{name} must be explicitly provided and positive")
        try:
            barrier = float(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{name} must be positive") from exc
        if not np.isfinite(barrier) or barrier <= 0:
            raise ValueError(f"{name} must be positive")
        return barrier

    def _add_price_features(self, df: pd.DataFrame) -> None:
        """Add price-based features."""
        grouped = df.groupby(self._GROUP_KEYS, sort=False, observed=True)
        # Returns
        df["returns"] = grouped["close"].pct_change(fill_method=None)
        df["log_returns"] = np.log(df["close"] / grouped["close"].shift(1))

        # Momentum
        for window in [1, 3, 5, 10, 15, 30]:
            df[f"momentum_{window}"] = grouped["close"].pct_change(
                window, fill_method=None
            )

        # Acceleration
        df["acceleration"] = df.groupby(
            self._GROUP_KEYS, sort=False, observed=True
        )["returns"].diff()

        # Distance from open
        df["dist_from_open"] = (df["close"] - df["open"]) / df["open"].replace(0, np.nan)

    def _add_volatility_features(self, df: pd.DataFrame) -> None:
        """Add volatility features."""
        grouped = df.groupby(self._GROUP_KEYS, sort=False, observed=True)
        df["range"] = (df["high"] - df["low"]) / df["close"].replace(0, np.nan)
        df["body_size"] = abs(df["close"] - df["open"]) / df["close"].replace(0, np.nan)
        df["upper_wick"] = (df["high"] - df[["open", "close"]].max(axis=1)) / df["close"].replace(0, np.nan)
        df["lower_wick"] = (df[["open", "close"]].min(axis=1) - df["low"]) / df["close"].replace(0, np.nan)

        # ATR
        df["tr"] = np.maximum(
            df["high"] - df["low"],
            np.maximum(
                abs(df["high"] - grouped["close"].shift(1)),
                abs(df["low"] - grouped["close"].shift(1))
            )
        )
        for window in [14, 30]:
            df[f"atr_{window}"] = df.groupby(
                self._GROUP_KEYS, sort=False, observed=True
            )["tr"].transform(lambda values: values.rolling(window).mean())

        # Realized volatility
        for window in [10, 20, 50]:
            df[f"realized_vol_{window}"] = df.groupby(
                self._GROUP_KEYS, sort=False, observed=True
            )["returns"].transform(lambda values: values.rolling(window).std())

    def _add_structure_features(self, df: pd.DataFrame) -> None:
        """Add market structure features."""
        # Range position
        df["range_position"] = (df["close"] - df["low"]) / (df["high"] - df["low"]).replace(0, np.nan)

        # Distance from high/low
        df["dist_from_high"] = (df["high"] - df["close"]) / df["close"].replace(0, np.nan)
        df["dist_from_low"] = (df["close"] - df["low"]) / df["close"].replace(0, np.nan)

        # Rolling support/resistance
        for window in [20, 50, 100]:
            df[f"resistance_{window}"] = df.groupby(
                self._GROUP_KEYS, sort=False, observed=True
            )["high"].transform(lambda values: values.rolling(window).max())
            df[f"support_{window}"] = df.groupby(
                self._GROUP_KEYS, sort=False, observed=True
            )["low"].transform(lambda values: values.rolling(window).min())
            df[f"dist_to_resistance_{window}"] = (df[f"resistance_{window}"] - df["close"]) / df["close"]
            df[f"dist_to_support_{window}"] = (df["close"] - df[f"support_{window}"]) / df["close"]

    def _add_multitimeframe_features(self, df: pd.DataFrame) -> None:
        """Add multi-timeframe features using rolling windows."""
        for window in [5, 15, 30, 60, 120, 240]:
            # SMA
            grouped_close = df.groupby(
                self._GROUP_KEYS, sort=False, observed=True
            )["close"]
            df[f"sma_{window}"] = grouped_close.transform(
                lambda values: values.rolling(window).mean()
            )
            df[f"ema_{window}"] = grouped_close.transform(
                lambda values: values.ewm(span=window).mean()
            )

            # Distance from MA
            df[f"dist_sma_{window}"] = (df["close"] - df[f"sma_{window}"]) / df[f"sma_{window}"]
            df[f"dist_ema_{window}"] = (df["close"] - df[f"ema_{window}"]) / df[f"ema_{window}"]

            # MA slope
            df[f"sma_slope_{window}"] = df.groupby(
                self._GROUP_KEYS, sort=False, observed=True
            )[f"sma_{window}"].diff()

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
        previous_session = df.groupby(
            self._GROUP_KEYS, sort=False, observed=True
        )["session"].shift(1)
        df["session_transition"] = (df["session"] != previous_session).astype(int)

    def _add_microstructure_features(self, df: pd.DataFrame) -> None:
        """Add microstructure features if spread/bid/ask available."""
        if "spread" in df.columns:
            df["spread_pct"] = df["spread"] / df["close"]
            df["spread_zscore"] = df.groupby(self._GROUP_KEYS)["spread"].transform(
                lambda x: (x - x.rolling(100).mean()) / x.rolling(100).std()
            )

        if "bid" in df.columns and "ask" in df.columns:
            df["mid_price"] = (df["bid"] + df["ask"]) / 2
            df["spread_abs"] = df["ask"] - df["bid"]

        if "volume" in df.columns:
            df["volume_zscore"] = df.groupby(self._GROUP_KEYS)["volume"].transform(
                lambda x: (x - x.rolling(100).mean()) / x.rolling(100).std()
            )
            df["volume_change"] = df.groupby(self._GROUP_KEYS)["volume"].pct_change(
                fill_method=None
            )

    def _create_labels(
        self,
        df: pd.DataFrame,
        *,
        horizon: int,
        profit_barrier_pct: float,
        loss_barrier_pct: float,
    ) -> pd.DataFrame:
        """Create independently matured outcomes for each market series."""
        label_columns = [
            "profit_barrier_first",
            "mfe",
            "mae",
            "time_to_target",
            "no_progress",
            "tail_loss",
            "direction",
            "return_horizon",
        ]
        labels = pd.DataFrame(np.nan, index=df.index, columns=label_columns)

        for _, group in df.groupby(
            self._GROUP_KEYS, sort=False, observed=True
        ):
            group = group.sort_values("time", kind="stable")
            indices = group.index.to_list()
            for position, index in enumerate(indices):
                if position + horizon >= len(indices):
                    continue

                future_indices = indices[position + 1 : position + horizon + 1]
                future = df.loc[future_indices]
                close = float(df.at[index, "close"])
                future_high = float(future["high"].max())
                future_low = float(future["low"].min())
                final_close = float(future.iloc[-1]["close"])
                mfe = max(0.0, future_high - close)
                mae = max(0.0, close - future_low)
                profit_price = close * (1.0 + profit_barrier_pct)
                loss_price = close * (1.0 - loss_barrier_pct)

                labels.at[index, "mfe"] = mfe
                labels.at[index, "mae"] = mae
                labels.at[index, "no_progress"] = int(mfe <= 0.0)
                labels.at[index, "tail_loss"] = int(future_low <= loss_price)
                labels.at[index, "direction"] = float(np.sign(final_close - close))
                labels.at[index, "return_horizon"] = final_close / close - 1.0

                for offset, (_, bar) in enumerate(future.iterrows(), start=1):
                    profit_hit = float(bar["high"]) >= profit_price
                    loss_hit = float(bar["low"]) <= loss_price
                    if profit_hit and loss_hit:
                        labels.at[index, "profit_barrier_first"] = 0
                        labels.at[index, "time_to_target"] = offset
                        break
                    if profit_hit or loss_hit:
                        labels.at[index, "profit_barrier_first"] = int(profit_hit)
                        labels.at[index, "time_to_target"] = offset
                        break

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
    *,
    label_horizon: int,
    train_ratio: float = 0.6,
    validation_ratio: float = 0.2,
    test_ratio: float = 0.15,
    sealed_ratio: float = 0.05,
) -> DatasetSplit:
    """Create chronological splits."""
    pipeline = DataPipeline(train_ratio, validation_ratio, test_ratio, sealed_ratio)
    return pipeline.create_splits(df, label_horizon=label_horizon)


def engineer_features(
    df: pd.DataFrame,
    *,
    profit_barrier_pct: float,
    loss_barrier_pct: float,
    label_horizon: int = 20,
) -> FeatureSet:
    """Engineer features with point-in-time correctness."""
    engineer = FeatureEngineer()
    return engineer.engineer(
        df,
        label_horizon=label_horizon,
        profit_barrier_pct=profit_barrier_pct,
        loss_barrier_pct=loss_barrier_pct,
    )
