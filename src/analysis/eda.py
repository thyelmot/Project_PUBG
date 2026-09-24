from pathlib import Path
from typing import Any, Dict, List, Optional
import numpy as np
import pandas as pd
from scipy import stats
from src.analysis.correlation import compute_bivariate_associations
from src.analysis.mode_analysis import analyze_behavior_by_mode
from src.data.io import atomic_write_json
from src.utils.logging import get_logger

logger = get_logger("pubg_eda")


def compute_distribution_summary(df: pd.DataFrame, columns: List[str]) -> pd.DataFrame:
    """Compute comprehensive descriptive summary: mean, std, median, skew, zero_rate, quantiles."""
    records = []
    for col in columns:
        if col not in df.columns:
            continue
        series = df[col].dropna()
        n = len(series)
        if n == 0:
            continue

        zero_rate = float((series == 0).sum() / n)
        mean_val = float(series.mean())
        std_val = float(series.std()) if n > 1 else 0.0
        median_val = float(series.median())
        skew_val = float(stats.skew(series)) if n > 2 else 0.0

        records.append({
            "feature": col,
            "count": n,
            "missing_count": int(df[col].isna().sum()),
            "missing_pct": float(df[col].isna().mean() * 100),
            "zero_rate": zero_rate,
            "mean": mean_val,
            "std": std_val,
            "median": median_val,
            "p25": float(series.quantile(0.25)),
            "p75": float(series.quantile(0.75)),
            "p95": float(series.quantile(0.95)),
            "skewness": skew_val,
        })
    return pd.DataFrame(records, columns=["feature", "count", "missing_count", "missing_pct",
                                         "zero_rate", "mean", "std", "median", "p25", "p75", "p95", "skewness"])


def run_structural_eda(df: pd.DataFrame, meta_df: pd.DataFrame) -> Dict[str, Any]:
    """Phase 1: Structural dataset overview."""
    total_rows = len(df)
    total_matches = len(meta_df)
    unique_players = df["player_name"].dropna().nunique()
    unique_teams = df.groupby(["match_id", "team_id"]).ngroups

    games_per_player = df["player_name"].dropna().value_counts()

    return {
        "total_records": total_rows,
        "total_matches": total_matches,
        "unique_players": unique_players,
        "unique_teams": unique_teams,
        "avg_players_per_match": float(total_rows / total_matches) if total_matches > 0 else 0,
        "median_games_per_player": float(games_per_player.median()) if not games_per_player.empty else 0,
        "p90_games_per_player": float(games_per_player.quantile(0.90)) if not games_per_player.empty else 0,
    }


def run_chronology_audit(meta_df: pd.DataFrame) -> Dict[str, Any]:
    """Phase 8: Audit timestamps and determine preliminary Chronology Grade (A/B/C)."""
    if "match_date" not in meta_df.columns:
        return {"grade": "Grade C", "reason": "No match_date column found in metadata."}

    dates = pd.to_datetime(meta_df["match_date"], errors="coerce", utc=True, format="mixed")
    null_dates = dates.isna().sum()

    if null_dates > 0:
        return {
            "grade": "Grade C",
            "null_date_count": int(null_dates),
            "reason": "Timestamp contains missing or unparseable dates.",
        }

    # Check date ties
    total_matches = len(dates)
    unique_timestamps = dates.nunique()
    tie_ratio = 1.0 - (unique_timestamps / total_matches) if total_matches > 0 else 1.0

    # Extract days
    days = dates.dt.date
    matches_per_day = days.value_counts()
    max_matches_in_single_day = int(matches_per_day.max()) if not matches_per_day.empty else 0

    # Assign Grade based on Evidence
    # Grade A: granular distinct timestamps (< 5% collisions)
    # Grade B: cross-day chronological sequence with multi-matches per day
    if tie_ratio < 0.05:
        grade = "Grade A"
        grade_desc = "Verified precise timestamps with minimal ties. Safe for expanding history."
    elif len(matches_per_day) >= 3:
        grade = "Grade B"
        grade_desc = "Day-level grouping verified. Cross-day historical modeling permitted (same-day excluded)."
    else:
        grade = "Grade C"
        grade_desc = "Chronology insufficient. Historical prediction S2/P3 blocked by chronology."

    return {
        "grade": grade,
        "description": grade_desc,
        "total_matches": total_matches,
        "unique_timestamps": unique_timestamps,
        "timestamp_tie_ratio": float(tie_ratio),
        "total_days_observed": len(matches_per_day),
        "max_matches_per_day": max_matches_in_single_day,
    }
