from typing import Any, Dict, List, Optional, Tuple
import numpy as np
import pandas as pd
from scipy import stats


def compute_bivariate_associations(
    df: pd.DataFrame,
    feature_cols: List[str],
    target_col: str,
    target_derived_set: Optional[set] = None,
) -> pd.DataFrame:
    """Compute verified Pearson and Spearman correlations with sample counts and leakage flags."""
    derived_set = target_derived_set or set()
    records = []

    if target_col not in df.columns:
        raise ValueError(f"Target column '{target_col}' not found in dataframe.")

    target_series = df[target_col]

    for feat in feature_cols:
        if feat not in df.columns:
            continue

        feat_series = df[feat]
        # Align on mutual non-null indices
        valid_mask = feat_series.notna() & target_series.notna()
        n_obs = int(valid_mask.sum())

        if n_obs < 10:
            records.append({
                "feature": feat,
                "target": target_col,
                "n_observations": n_obs,
                "pearson_r": np.nan,
                "pearson_pvalue": np.nan,
                "spearman_rho": np.nan,
                "spearman_pvalue": np.nan,
                "is_primary_valid": False,
                "target_derived": feat in derived_set,
                "notes": "Insufficient observations (< 10)",
            })
            continue

        x = feat_series[valid_mask].astype("float64").values
        y = target_series[valid_mask].astype("float64").values

        # Constant check
        if np.all(x == x[0]) or np.all(y == y[0]):
            records.append({
                "feature": feat,
                "target": target_col,
                "n_observations": n_obs,
                "pearson_r": np.nan,
                "pearson_pvalue": np.nan,
                "spearman_rho": np.nan,
                "spearman_pvalue": np.nan,
                "is_primary_valid": False,
                "target_derived": feat in derived_set,
                "notes": "Constant variable (zero variance)",
            })
            continue

        p_r, p_p = stats.pearsonr(x, y)
        s_rho, s_p = stats.spearmanr(x, y)

        is_primary = (feat not in derived_set)

        records.append({
            "feature": feat,
            "target": target_col,
            "n_observations": n_obs,
            "pearson_r": float(p_r),
            "pearson_pvalue": float(p_p),
            "spearman_rho": float(s_rho),
            "spearman_pvalue": float(s_p),
            "is_primary_valid": is_primary,
            "target_derived": feat in derived_set,
            "notes": "Valid association" if is_primary else "Target-derived coupling (diagnostic only)",
        })

    return pd.DataFrame(records)
