from typing import Any, Dict, List, Optional
import numpy as np
import pandas as pd
from scipy import stats
from src.utils.logging import get_logger

logger = get_logger("pubg_mode_analysis")


def analyze_behavior_by_mode(
    df: pd.DataFrame,
    behavior_cols: List[str],
    mode_col: str = "team_size_mode",
) -> Dict[str, Any]:
    """Analyze behavioral distribution shifts across Solo, Duo, Squad modes.

    Reports:
      - Descriptive statistics (n, mean, std, median, q25, q75) for each mode.
      - Non-parametric Kruskal-Wallis H test across modes.
      - Effect size eta-squared (eta^2_H = (H - k + 1) / (N - k)) with magnitude classification.
      - RQ2 mode strategy recommendation (per_mode vs overall).
    """
    clean_df = df.copy()

    # Determine mode label mapping based on column type
    if mode_col not in clean_df.columns:
        if "party_size" in clean_df.columns:
            mode_col = "party_size"
        elif "match_mode" in clean_df.columns:
            mode_col = "match_mode"
        else:
            raise ValueError(f"Neither '{mode_col}', 'party_size', nor 'match_mode' found in dataframe.")

    if mode_col == "party_size":
        mode_map = {1: "Solo", 2: "Duo", 4: "Squad"}
        clean_df["game_mode_label"] = clean_df[mode_col].map(lambda x: mode_map.get(x, f"Other_{x}"))
    elif mode_col == "team_size_mode":
        mode_map = {"solo": "Solo", "duo": "Duo", "squad": "Squad"}
        clean_df["game_mode_label"] = clean_df[mode_col].astype(str).str.lower().map(lambda x: mode_map.get(x, f"Other_{x}"))
    else:
        clean_df["game_mode_label"] = clean_df[mode_col].astype(str)

    stats_records = []
    differences = {}

    for col in behavior_cols:
        if col not in clean_df.columns:
            continue

        grouped = clean_df.groupby("game_mode_label")[col].agg(
            n="count",
            mean="mean",
            std="std",
            median="median",
            q25=lambda s: s.quantile(0.25),
            q75=lambda s: s.quantile(0.75),
        ).reset_index()
        grouped["feature"] = col
        stats_records.append(grouped)

        # Statistical test across Solo, Duo, Squad groups
        mode_samples = [
            clean_df[clean_df["game_mode_label"] == m][col].dropna().values
            for m in ["Solo", "Duo", "Squad"]
            if (clean_df["game_mode_label"] == m).sum() >= 10
        ]
        mode_samples = [s for s in mode_samples if len(s) >= 10]

        if len(mode_samples) >= 2:
            all_values = np.concatenate(mode_samples)
            N = len(all_values)
            k = len(mode_samples)

            if np.all(all_values == all_values[0]):
                kw_stat, kw_p = 0.0, 1.0
                eta_sq = 0.0
                magnitude = "negligible"
            else:
                kw_stat, kw_p = stats.kruskal(*mode_samples)
                eta_sq = max(0.0, float((kw_stat - k + 1) / (N - k))) if N > k else 0.0
                magnitude = (
                    "large" if eta_sq >= 0.14
                    else "medium" if eta_sq >= 0.06
                    else "small" if eta_sq >= 0.01
                    else "negligible"
                )

            diff_entry = {
                "kruskal_statistic": float(kw_stat),
                "p_value": float(kw_p),
                "n_observations": int(N),
                "k_groups": int(k),
                "effect_size_eta_sq": round(float(eta_sq), 4),
                "effect_size_eta_squared": round(float(eta_sq), 4),
                "effect_magnitude": magnitude,
                "effect_size_magnitude": magnitude,
                "is_significant": bool(kw_p < 0.01),
            }
            differences[col] = diff_entry

    summary_df = pd.concat(stats_records, ignore_index=True) if stats_records else pd.DataFrame()

    # Recommendation for RQ2: if assistance, DBNO, or combat differs significantly, recommend per_mode
    significant_count = sum(1 for v in differences.values() if v.get("is_significant", False))
    recommendation = "per_mode" if significant_count >= 2 else "overall"

    logger.info(
        f"Mode analysis completed. Significant shifts in {significant_count}/{len(differences)} features. "
        f"Recommendation: {recommendation}"
    )

    return {
        "summary_table": summary_df,
        "mode_differences": differences,
        "recommended_rq2_strategy": recommendation,
    }


def format_mode_differences_table(differences: Dict[str, Any]) -> pd.DataFrame:
    """Format Kruskal-Wallis mode differences into a tabular DataFrame for export and display."""
    rows = []
    for feat, diff in differences.items():
        eta = diff.get("effect_size_eta_squared", diff.get("effect_size_eta_sq", np.nan))
        mag = diff.get("effect_size_magnitude", diff.get("effect_magnitude", "unknown"))
        rows.append({
            "feature": feat,
            "kruskal_statistic": diff.get("kruskal_statistic", np.nan),
            "p_value": diff.get("p_value", np.nan),
            "is_significant": diff.get("is_significant", False),
            "n_observations": diff.get("n_observations", np.nan),
            "k_groups": diff.get("k_groups", np.nan),
            "effect_size_eta_sq": eta,
            "effect_size_eta_squared": eta,
            "effect_magnitude": mag,
            "effect_size_magnitude": mag,
        })
    cols = [
        "feature", "kruskal_statistic", "p_value", "is_significant",
        "n_observations", "k_groups", "effect_size_eta_sq", "effect_size_eta_squared",
        "effect_magnitude", "effect_size_magnitude"
    ]
    return pd.DataFrame(rows, columns=cols) if rows else pd.DataFrame(columns=cols)
