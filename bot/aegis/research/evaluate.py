"""Holdout helpers. Never invent metrics or peek at holdout labels."""
from __future__ import annotations

import pandas as pd


def untouched_holdout(df: pd.DataFrame, *, holdout_frac: float = 0.3) -> tuple[pd.DataFrame, pd.DataFrame]:
    if not 0 < holdout_frac < 1:
        raise ValueError("holdout_frac must be in (0, 1)")
    n = len(df)
    if n < 10:
        raise ValueError("need at least 10 rows to split")
    cut = int(n * (1.0 - holdout_frac))
    cut = min(max(cut, 1), n - 1)
    train = df.iloc[:cut].copy()
    hold = df.iloc[cut:].copy()
    if "time" in df.columns:
        if train["time"].max() >= hold["time"].min():
            # last train timestamp must be strictly before first holdout bar
            hold = hold.loc[hold["time"] > train["time"].max()].copy()
    return train.reset_index(drop=True), hold.reset_index(drop=True)


def purged_holdout(
    df: pd.DataFrame,
    *,
    holdout_frac: float = 0.3,
    embargo_frac: float = 0.02,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Time holdout with an embargo gap (Prado/Jansen research_proxy).

    After the usual chronological split, drop training rows whose timestamp falls
    inside the embargo window immediately before holdout. Overlapping label windows
    are not modeled here — bar clips are one row per closed trade.
    """
    train, hold = untouched_holdout(df, holdout_frac=holdout_frac)
    if "time" not in df.columns or hold.empty or train.empty:
        return train, hold
    hold_min = pd.Timestamp(hold["time"].min())
    train_min = pd.Timestamp(train["time"].min())
    train_max = pd.Timestamp(train["time"].max())
    span = max((train_max - train_min).total_seconds(), 1.0)
    embargo = pd.Timedelta(seconds=span * float(embargo_frac))
    cutoff = hold_min - embargo
    purged = train.loc[pd.to_datetime(train["time"], utc=True) < cutoff].copy()
    if len(purged) < max(5, int(len(train) * 0.5)):
        return train, hold
    return purged.reset_index(drop=True), hold.reset_index(drop=True)


def combinatorial_purged_folds(
    df: pd.DataFrame,
    *,
    n_groups: int = 5,
    n_test_groups: int = 1,
    embargo_frac: float = 0.02,
):
    """Yield (train, test) frames: contiguous groups, train purged around test (AFML CPCV proxy)."""
    if n_groups < 2:
        raise ValueError("n_groups must be >= 2")
    n = len(df)
    if n < n_groups * 2:
        raise ValueError("not enough rows for combinatorial folds")
    frame = df.reset_index(drop=True)
    edges = [int(round(i * n / n_groups)) for i in range(n_groups + 1)]
    groups = [frame.iloc[edges[i] : edges[i + 1]].copy() for i in range(n_groups)]
    for test_i in range(n_groups):
        test = pd.concat(groups[test_i : test_i + n_test_groups], ignore_index=False)
        train_parts = [groups[j] for j in range(n_groups) if j < test_i or j >= test_i + n_test_groups]
        train = pd.concat(train_parts, ignore_index=False)
        if "time" in frame.columns and not test.empty and not train.empty:
            test_t = pd.to_datetime(test["time"], utc=True)
            span = max((test_t.max() - test_t.min()).total_seconds(), 1.0)
            embargo = pd.Timedelta(seconds=span * float(embargo_frac))
            lo = test_t.min() - embargo
            hi = test_t.max() + embargo
            train_t = pd.to_datetime(train["time"], utc=True)
            train = train.loc[(train_t < lo) | (train_t > hi)].copy()
        if train.empty or test.empty:
            continue
        yield train.reset_index(drop=True), test.reset_index(drop=True)
