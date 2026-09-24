from typing import Any, Dict, List
import numpy as np
import pandas as pd
from scipy import stats
from src.utils.logging import get_logger

logger = get_logger("pubg_mode_analysis")


def analyze_behavior_by_mode(
    df: pd.DataFrame,
    behavior_cols: List[str],
    mode_col: str = "party_size",
) -> Dict[str, Any]:
    """Analyze behavioral distribution shifts across Solo, Duo, Squad modes."""
    # Map party_size to readable mode
    mode_map = {1: "Solo", 2: "Duo", 4: "Squad"}
    clean_df = df.copy()
    clean_df["game_mode_label"] = clean_df[mode_col].map(lambda x: mode_map.get(x, f"Other_{x}"))

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
            if (clean_df["game_mode_label"] == m).sum() >= 20
        ]
        mode_samples = [s for s in mode_samples if len(s) >= 20]
        if len(mode_samples) >= 2:
            all_values = np.concatenate(mode_samples)
            if np.all(all_values == all_values[0]):
                kw_stat, kw_p = 0.0, 1.0
            else:
                kw_stat, kw_p = stats.kruskal(*mode_samples)
            differences[col] = {
                "kruskal_statistic": float(kw_stat),
                "p_value": float(kw_p),
                "is_significant": float(kw_p) < 0.01,
            }

    summary_df = pd.concat(stats_records, ignore_index=True) if stats_records else pd.DataFrame()

    # Recommendation for RQ2: if assistance or combat differs significantly, recommend per-mode or player-mode
    significant_count = sum(1 for v in differences.values() if v.get("is_significant", False))
    recommendation = "per_mode" if significant_count >= 2 else "overall"

    logger.info(f"Mode analysis completed. Significant shifts in {significant_count}/{len(differences)} features. Recommendation: {recommendation}")

    return {
        "summary_table": summary_df,
        "mode_differences": differences,
        "recommended_rq2_strategy": recommendation,
    }
