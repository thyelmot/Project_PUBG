from typing import Any, Iterable, List, Optional, Union
import numpy as np
import pandas as pd


def assert_finite(data: Union[pd.Series, pd.DataFrame], columns: Optional[List[str]] = None, name: str = "feature") -> None:
    """Ensure all non-null values in a series or dataframe are strictly finite (not Inf, -Inf)."""
    if isinstance(data, pd.DataFrame):
        cols = columns or list(data.columns)
        for col in cols:
            assert_finite(data[col], name=col)
        return

    valid_mask = data.notna()
    if not bool(np.isfinite(data[valid_mask]).all()):
        inf_count = int(np.isinf(data[valid_mask]).sum())
        raise ValueError(f"Feature '{name}' contains {inf_count} infinite values.")


def assert_non_negative(data: Union[pd.Series, pd.DataFrame], columns: Optional[List[str]] = None, name: str = "feature") -> None:
    """Ensure non-null values are non-negative."""
    if isinstance(data, pd.DataFrame):
        cols = columns or list(data.columns)
        for col in cols:
            assert_non_negative(data[col], name=col)
        return

    valid_mask = data.notna()
    min_val = data[valid_mask].min() if valid_mask.any() else 0
    if min_val < 0:
        raise ValueError(f"Feature '{name}' contains negative values (minimum: {min_val}).")


def assert_valid_ratio(data: Union[pd.Series, pd.DataFrame], columns: Optional[List[str]] = None, name: str = "ratio", allow_nan: bool = True) -> None:
    """Ensure values are within valid ratio interval [0.0, 1.0]."""
    if isinstance(data, pd.DataFrame):
        cols = columns or list(data.columns)
        for col in cols:
            assert_valid_ratio(data[col], name=col, allow_nan=allow_nan)
        return

    if not allow_nan and bool(data.isna().any()):
        raise ValueError(f"Ratio '{name}' contains unexpected NaN values.")
    valid = data.dropna()
    if not valid.empty:
        if bool((valid < -1e-6).any()) or bool((valid > 1.0 + 1e-6).any()):
            min_val, max_val = valid.min(), valid.max()
            raise ValueError(f"Ratio '{name}' out of bounds [0, 1]: [{min_val}, {max_val}].")


def assert_same_index(df1: pd.DataFrame, df2: pd.DataFrame, context: str = "paired evaluation") -> None:
    """Verify that two dataframes share the exact identical row index for paired comparisons."""
    if len(df1) != len(df2):
        raise ValueError(f"Row count mismatch in {context}: {len(df1)} vs {len(df2)}.")
    if not df1.index.equals(df2.index):
        raise ValueError(f"Index order or keys do not match exactly in {context}.")


def assert_no_target_in_features(feature_names: Iterable[str], target_names: Union[str, Iterable[str]]) -> None:
    """Assert that no target columns leaked into feature list."""
    if isinstance(target_names, str):
        target_set = {target_names}
    else:
        target_set = set(target_names)
    intersection = set(feature_names).intersection(target_set)
    if intersection:
        raise ValueError(f"Target leakage detected! Targets found in feature list: {intersection}")

