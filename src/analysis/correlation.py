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
                "status": "insufficient_observations",
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
                "status": "constant_variable",
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
            "status": "valid" if is_primary else "diagnostic_only",
            "is_primary_valid": is_primary,
            "target_derived": feat in derived_set,
            "notes": "Valid association" if is_primary else "Target-derived coupling (diagnostic only)",
        })

    return pd.DataFrame(records)


def compute_vif_summary(
    df: pd.DataFrame,
    feature_cols: List[str],
    target_derived_set: Optional[set] = None,
) -> pd.DataFrame:
    """Compute Variance Inflation Factor (VIF = 1 / (1 - R_j^2)) for valid numerical subset.

    Rules (NB05-08, NB05-15):
      - Exclude targets and deterministic descendants from independent predictor evaluation.
      - Never drop features automatically based on an arbitrary VIF cutoff; report for diagnosis.
      - Tolerates collinear matrices safely by reporting inf / extreme severity.
    """
    derived_set = target_derived_set or set()
    valid_cols = [c for c in feature_cols if c in df.columns and c not in derived_set]

    if len(valid_cols) < 2:
        return pd.DataFrame(columns=[
            "feature", "vif", "tolerance", "n_observations", "multicollinearity_severity", "notes"
        ])

    clean_subset = df[valid_cols].dropna().astype("float64")
    n_obs = len(clean_subset)

    if n_obs <= len(valid_cols):
        return pd.DataFrame([
            {
                "feature": c,
                "vif": np.nan,
                "tolerance": np.nan,
                "n_observations": n_obs,
                "multicollinearity_severity": "undetermined",
                "notes": "Insufficient observations after dropna",
            }
            for c in valid_cols
        ])

    # Check for zero variance
    stds = clean_subset.std(axis=0)
    zero_var_cols = stds[stds == 0].index.tolist()
    if zero_var_cols:
        return pd.DataFrame([
            {
                "feature": c,
                "vif": np.nan,
                "tolerance": np.nan,
                "n_observations": n_obs,
                "multicollinearity_severity": "zero_variance" if c in zero_var_cols else "undetermined",
                "notes": f"Zero variance detected in column(s): {zero_var_cols}",
            }
            for c in valid_cols
        ])

    X_mat = clean_subset.values
    records = []

    for j, col in enumerate(valid_cols):
        y = X_mat[:, j]
        other_idx = [i for i in range(len(valid_cols)) if i != j]
        A = np.column_stack([np.ones(n_obs), X_mat[:, other_idx]])

        try:
            beta, _, _, _ = np.linalg.lstsq(A, y, rcond=None)
            res = y - A @ beta
            ss_tot = float(np.sum((y - np.mean(y)) ** 2))
            ss_res = float(np.sum(res ** 2))
            r2 = max(0.0, min(1.0, 1.0 - (ss_res / ss_tot))) if ss_tot > 0 else 0.0
            tol = max(0.0, 1.0 - r2)
            if tol <= 1e-6 or ss_res < 1e-10:
                vif_val = np.inf
                tol_val = 0.0
                severity = "extreme"
            else:
                vif_val = float(1.0 / tol)
                tol_val = float(tol)
                if vif_val >= 10.0:
                    severity = "high"
                elif vif_val >= 5.0:
                    severity = "moderate"
                else:
                    severity = "low"

            records.append({
                "feature": col,
                "vif": np.inf if np.isinf(vif_val) else round(vif_val, 4),
                "tolerance": round(tol_val, 4),
                "n_observations": n_obs,
                "multicollinearity_severity": severity,
                "notes": "Standard VIF diagnosis (diagnostic only, not automatic pruning)" if severity != "extreme" else "Extreme/perfect multicollinearity detected",
            })
        except Exception as e:
            records.append({
                "feature": col,
                "vif": np.nan,
                "tolerance": np.nan,
                "n_observations": n_obs,
                "multicollinearity_severity": "undetermined",
                "notes": f"VIF computation failed: {str(e)}",
            })

    return pd.DataFrame(records)
