from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union
import duckdb
import numpy as np
import pandas as pd
from scipy import stats
from src.analysis.correlation import compute_bivariate_associations
from src.analysis.mode_analysis import analyze_behavior_by_mode
from src.data.io import atomic_write_json, atomic_write_csv
from src.utils.logging import get_logger

logger = get_logger("pubg_eda")


def compute_distribution_summary(df: pd.DataFrame, columns: List[str]) -> pd.DataFrame:
    """Compute comprehensive descriptive summary on in-memory DataFrame:
    count, missing_count, missing_pct, zero_rate, mean, std, min, median, p25, p75, p95, max, skewness.
    """
    records = []
    for col in columns:
        if col not in df.columns:
            continue
        series = df[col].dropna()
        n = len(series)
        missing_count = int(df[col].isna().sum())
        missing_pct = float(df[col].isna().mean() * 100)

        if n == 0:
            continue

        zero_rate = float((series == 0).sum() / n)
        mean_val = float(series.mean())
        std_val = float(series.std()) if n > 1 else 0.0
        min_val = float(series.min())
        median_val = float(series.median())
        max_val = float(series.max())
        skew_val = float(stats.skew(series)) if n > 2 else 0.0

        records.append({
            "feature": col,
            "count": n,
            "missing_count": missing_count,
            "missing_pct": missing_pct,
            "zero_rate": zero_rate,
            "mean": mean_val,
            "std": std_val,
            "min": min_val,
            "p25": float(series.quantile(0.25)),
            "median": median_val,
            "p75": float(series.quantile(0.75)),
            "p95": float(series.quantile(0.95)),
            "max": max_val,
            "skewness": skew_val,
        })
    return pd.DataFrame(records, columns=[
        "feature", "count", "missing_count", "missing_pct", "zero_rate",
        "mean", "std", "min", "p25", "median", "p75", "p95", "max", "skewness"
    ])


def compute_sql_distribution_summary(
    con: duckdb.DuckDBPyConnection,
    parquet_path: Path,
    columns: List[str],
) -> pd.DataFrame:
    """Compute exact full-data distribution summary via DuckDB streaming SQL on disk.

    Avoids loading full datasets into pandas memory while guaranteeing exact quantiles and moments.
    """
    safe_path = parquet_path.resolve().as_posix().replace("'", "''")
    # Discover available columns
    available_cols = set(con.execute(f"SELECT * FROM read_parquet('{safe_path}') LIMIT 0;").df().columns)

    records = []
    total_rows = con.execute(f"SELECT count(*) FROM read_parquet('{safe_path}');").fetchone()[0]

    for col in columns:
        if col not in available_cols:
            continue

        # Use DuckDB exact statistical aggregations
        query = f"""
        SELECT
            COUNT({col}) AS count_valid,
            SUM(CASE WHEN {col} = 0 THEN 1 ELSE 0 END) AS count_zero,
            AVG(CAST({col} AS DOUBLE)) AS mean_val,
            STDDEV(CAST({col} AS DOUBLE)) AS std_val,
            MIN(CAST({col} AS DOUBLE)) AS min_val,
            QUANTILE_CONT(CAST({col} AS DOUBLE), 0.25) AS p25_val,
            MEDIAN(CAST({col} AS DOUBLE)) AS median_val,
            QUANTILE_CONT(CAST({col} AS DOUBLE), 0.75) AS p75_val,
            QUANTILE_CONT(CAST({col} AS DOUBLE), 0.95) AS p95_val,
            MAX(CAST({col} AS DOUBLE)) AS max_val
        FROM read_parquet('{safe_path}');
        """
        row = con.execute(query).fetchone()
        count_valid = int(row[0] or 0)
        count_zero = int(row[1] or 0)
        missing_count = total_rows - count_valid
        missing_pct = float(missing_count * 100.0 / total_rows) if total_rows > 0 else 0.0
        zero_rate = float(count_zero / count_valid) if count_valid > 0 else 0.0

        mean_val = float(row[2]) if row[2] is not None else np.nan
        std_val = float(row[3]) if row[3] is not None else np.nan
        min_val = float(row[4]) if row[4] is not None else np.nan
        p25_val = float(row[5]) if row[5] is not None else np.nan
        median_val = float(row[6]) if row[6] is not None else np.nan
        p75_val = float(row[7]) if row[7] is not None else np.nan
        p95_val = float(row[8]) if row[8] is not None else np.nan
        max_val = float(row[9]) if row[9] is not None else np.nan

        # Exact skewness calculation
        if count_valid > 2 and std_val > 0:
            skew_query = f"""
            SELECT
                AVG(POWER((CAST({col} AS DOUBLE) - {mean_val}) / {std_val}, 3))
            FROM read_parquet('{safe_path}')
            WHERE {col} IS NOT NULL;
            """
            skew_val = float(con.execute(skew_query).fetchone()[0] or 0.0)
        else:
            skew_val = 0.0

        records.append({
            "feature": col,
            "count": count_valid,
            "missing_count": missing_count,
            "missing_pct": round(missing_pct, 4),
            "zero_rate": round(zero_rate, 4),
            "mean": round(mean_val, 4) if not np.isnan(mean_val) else np.nan,
            "std": round(std_val, 4) if not np.isnan(std_val) else np.nan,
            "min": round(min_val, 4) if not np.isnan(min_val) else np.nan,
            "p25": round(p25_val, 4) if not np.isnan(p25_val) else np.nan,
            "median": round(median_val, 4) if not np.isnan(median_val) else np.nan,
            "p75": round(p75_val, 4) if not np.isnan(p75_val) else np.nan,
            "p95": round(p95_val, 4) if not np.isnan(p95_val) else np.nan,
            "max": round(max_val, 4) if not np.isnan(max_val) else np.nan,
            "skewness": round(skew_val, 4),
        })

    return pd.DataFrame(records, columns=[
        "feature", "count", "missing_count", "missing_pct", "zero_rate",
        "mean", "std", "min", "p25", "median", "p75", "p95", "max", "skewness"
    ])


def compute_sql_correlation_matrices(
    con: duckdb.DuckDBPyConnection,
    parquet_path: Path,
    columns: List[str],
) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Return exact pairwise Pearson, tie-aware Spearman and pair-N matrices.

    Each pair is processed by DuckDB, so the notebook does not materialize the
    complete multivariate dataset in pandas or average correlations by chunk.
    """
    safe_path = parquet_path.resolve().as_posix().replace("'", "''")
    available = set(con.execute(f"SELECT * FROM read_parquet('{safe_path}') LIMIT 0").df().columns)
    selected = [col for col in columns if col in available]
    pearson = pd.DataFrame(np.nan, index=selected, columns=selected, dtype="float64")
    spearman = pearson.copy()
    pair_n = pd.DataFrame(0, index=selected, columns=selected, dtype="int64")

    for i, left in enumerate(selected):
        for right in selected[i:]:
            query = f"""
            WITH pairs AS (
                SELECT CAST({left} AS DOUBLE) AS x, CAST({right} AS DOUBLE) AS y
                FROM read_parquet('{safe_path}')
                WHERE {left} IS NOT NULL AND {right} IS NOT NULL
            ), ranked AS (
                SELECT x, y,
                    RANK() OVER (ORDER BY x) + (COUNT(*) OVER (PARTITION BY x) - 1) / 2.0 AS rx,
                    RANK() OVER (ORDER BY y) + (COUNT(*) OVER (PARTITION BY y) - 1) / 2.0 AS ry
                FROM pairs
            )
            SELECT COUNT(*) AS n, CORR(x, y) AS pearson_r, CORR(rx, ry) AS spearman_rho
            FROM ranked
            """
            n_obs, pearson_r, spearman_rho = con.execute(query).fetchone()
            for matrix, value in ((pearson, pearson_r), (spearman, spearman_rho)):
                matrix.loc[left, right] = matrix.loc[right, left] = value
            pair_n.loc[left, right] = pair_n.loc[right, left] = int(n_obs)

    return pearson, spearman, pair_n


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


def compute_player_retention_diagnostics(
    con: duckdb.DuckDBPyConnection,
    parquet_path: Path,
    thresholds: List[int] = [1, 5, 10, 20, 50],
) -> pd.DataFrame:
    """Compute player retention statistics across candidate thresholds (Chart A02 / I01).

    Note: Retention thresholds 5/10/20/50 are diagnostic candidates and do not prejudge RQ2 min_games.
    """
    safe_path = parquet_path.resolve().as_posix().replace("'", "''")
    values_clause = ", ".join(f"({k})" for k in thresholds)

    query = f"""
    WITH player_counts AS (
        SELECT player_name, COUNT(*) AS match_count
        FROM read_parquet('{safe_path}')
        WHERE player_name IS NOT NULL
        GROUP BY player_name
    ),
    totals AS (
        SELECT COUNT(*) AS total_unique_players, SUM(match_count) AS total_player_matches
        FROM player_counts
    )
    SELECT
        k.threshold,
        COUNT(CASE WHEN p.match_count >= k.threshold THEN 1 END) AS eligible_players,
        ROUND(COUNT(CASE WHEN p.match_count >= k.threshold THEN 1 END) * 100.0 / t.total_unique_players, 2) AS player_retention_pct,
        SUM(CASE WHEN p.match_count >= k.threshold THEN p.match_count ELSE 0 END) AS eligible_matches,
        ROUND(SUM(CASE WHEN p.match_count >= k.threshold THEN p.match_count ELSE 0 END) * 100.0 / t.total_player_matches, 2) AS match_coverage_pct
    FROM player_counts p
    CROSS JOIN (VALUES {values_clause}) AS k(threshold)
    CROSS JOIN totals t
    GROUP BY k.threshold, t.total_unique_players, t.total_player_matches
    ORDER BY k.threshold ASC;
    """
    return con.execute(query).df()


def compute_combat_phase_by_placement_tier(
    con: duckdb.DuckDBPyConnection,
    parquet_path: Path,
) -> pd.DataFrame:
    """Compute combat phase contribution across normalized placement quartiles (Chart H06 - High Priority).

    Evaluates how early, mid, and late combat phases distribute among placement tiers.
    """
    safe_path = parquet_path.resolve().as_posix().replace("'", "''")
    cols = [r[0] for r in con.execute(f"DESCRIBE SELECT * FROM read_parquet('{safe_path}') LIMIT 0;").fetchall()]
    if "valid_placement" in cols:
        valid_filter = "valid_placement = true"
    elif "placement_validity_flag" in cols:
        valid_filter = "placement_validity_flag = 'VALID'"
    else:
        valid_filter = "1=1"

    query = f"""
    SELECT
        CASE
            WHEN normalized_placement >= 0.75 THEN 'Tier 1 (Top 25%)'
            WHEN normalized_placement >= 0.50 THEN 'Tier 2 (25% - 50%)'
            WHEN normalized_placement >= 0.25 THEN 'Tier 3 (50% - 75%)'
            ELSE 'Tier 4 (Bottom 25%)'
        END AS placement_tier,
        COUNT(*) AS player_count,
        ROUND(AVG(player_kills), 2) AS avg_kills,
        ROUND(AVG(player_dmg), 2) AS avg_damage,
        ROUND(AVG(early_kill_ratio), 4) AS avg_early_ratio,
        ROUND(AVG(mid_kill_ratio), 4) AS avg_mid_ratio,
        ROUND(AVG(late_kill_ratio), 4) AS avg_late_ratio
    FROM read_parquet('{safe_path}')
    WHERE {valid_filter}
      AND has_kill = true
      AND early_kill_ratio IS NOT NULL
    GROUP BY 1
    ORDER BY 1 ASC;
    """
    return con.execute(query).df()


def run_chronology_audit(
    meta_df: pd.DataFrame,
    has_exact_order_evidence: bool = False,
    config_grade: Optional[str] = None,
    player_match_df: Optional[pd.DataFrame] = None,
) -> Dict[str, Any]:
    """Audit chronology evidence; configuration may downgrade but never upgrade evidence."""
    base = {
        "grade": "Grade C",
        "description": "Chronology insufficient. Historical prediction S2/P3 blocked by chronology.",
        "historical_modeling_status": "blocked",
        "policy": "blocked",
        "total_matches": int(len(meta_df)),
        "unique_timestamps": 0,
        "timestamp_tie_ratio": 1.0,
        "total_days_observed": 0,
        "max_matches_per_day": 0,
        "same_day_multi_match_days": 0,
        "same_player_timestamp_overlap_count": 0,
        "null_date_count": int(len(meta_df)),
        "min_timestamp": None,
        "max_timestamp": None,
        "timezone_normalized": "UTC",
        "observed_resolution_seconds": None,
        "source_timestamp_semantics": "pending_source_evidence",
        "statistic_availability": "pending_source_evidence",
        "has_exact_order_evidence": bool(has_exact_order_evidence),
        "config_grade_requested": config_grade,
    }
    if "match_date" not in meta_df.columns:
        return {**base, "reason": "No match_date column found in metadata."}

    dates = pd.to_datetime(meta_df["match_date"], errors="coerce", utc=True, format="mixed")
    null_dates = int(dates.isna().sum())
    valid_dates = dates.dropna()
    base.update({
        "null_date_count": null_dates,
        "unique_timestamps": int(valid_dates.nunique()),
        "min_timestamp": str(valid_dates.min()) if not valid_dates.empty else None,
        "max_timestamp": str(valid_dates.max()) if not valid_dates.empty else None,
    })
    if null_dates > 0 or valid_dates.empty:
        return {
            **base,
            "reason": "Timestamp contains missing or unparseable dates.",
            "description": "Chronology contains missing/unparseable match dates; S2/P3 remains blocked.",
        }

    total_matches = len(valid_dates)
    unique_timestamps = int(valid_dates.nunique())
    tie_ratio = float(1.0 - unique_timestamps / total_matches) if total_matches else 1.0
    days = valid_dates.dt.floor("D")
    matches_per_day = days.value_counts()
    total_days = int(len(matches_per_day))
    positive_deltas = valid_dates.sort_values().drop_duplicates().diff().dropna()
    positive_deltas = positive_deltas[positive_deltas > pd.Timedelta(0)]
    resolution = float(positive_deltas.min().total_seconds()) if not positive_deltas.empty else None

    overlap_count = 0
    if player_match_df is not None and {"player_name", "match_id"}.issubset(player_match_df.columns):
        time_column = "match_date" if "match_date" in player_match_df.columns else "date" if "date" in player_match_df.columns else None
        if time_column:
            player_times = player_match_df[["player_name", "match_id", time_column]].copy()
            player_times[time_column] = pd.to_datetime(
                player_times[time_column], errors="coerce", utc=True, format="mixed"
            )
            player_times = player_times.dropna(subset=["player_name", "match_id", time_column]).drop_duplicates()
            overlaps = player_times.groupby(["player_name", time_column])["match_id"].nunique()
            overlap_count = int((overlaps > 1).sum())

    evidence_grade = "Grade C"
    if has_exact_order_evidence and tie_ratio < 0.05 and overlap_count == 0:
        evidence_grade = "Grade A"
    elif total_days >= 3:
        evidence_grade = "Grade B"

    grade = evidence_grade
    if config_grade in {"Grade A", "Grade B", "Grade C"}:
        rank = {"Grade C": 0, "Grade B": 1, "Grade A": 2}
        if rank[config_grade] < rank[evidence_grade]:
            grade = config_grade

    if grade == "Grade A":
        description = "Exact intra-day order has explicit source evidence; granular historical expansion is eligible."
        status = "eligible_granular"
        policy = "exact_order"
    elif grade == "Grade B":
        description = (
            "Day-level chronology is usable. Historical features may use strictly earlier days only; "
            "same-day matches are excluded because exact intra-day order and statistic availability remain unverified."
        )
        status = "eligible_cross_day"
        policy = "strictly_earlier_days_only"
    else:
        description = "Fewer than three reliable days or a configured downgrade; official historical S2/P3 is blocked."
        status = "blocked"
        policy = "blocked"

    return {
        **base,
        "grade": grade,
        "evidence_grade": evidence_grade,
        "description": description,
        "historical_modeling_status": status,
        "policy": policy,
        "total_matches": total_matches,
        "unique_timestamps": unique_timestamps,
        "timestamp_tie_ratio": tie_ratio,
        "total_days_observed": total_days,
        "max_matches_per_day": int(matches_per_day.max()) if not matches_per_day.empty else 0,
        "same_day_multi_match_days": int((matches_per_day > 1).sum()),
        "same_player_timestamp_overlap_count": overlap_count,
        "null_date_count": null_dates,
        "observed_resolution_seconds": resolution,
        "reason": None if grade != "Grade C" else "Insufficient trustworthy chronology.",
    }

def analyze_parquet_distributions(path: Path, columns: List[str]):
    """Exact full-row statistics, loading only one feature and its mode at a time.

    Memory scales with row count of a single column; quantiles and Kruskal remain exact.
    """
    import pyarrow.parquet as pq
    from src.data.io import read_parquet_df

    names = pq.read_schema(path).names
    summaries, mode_tables, differences, diff_rows = [], [], {}, []

    mode_candidate = "team_size_mode" if "team_size_mode" in names else "party_size"

    for col in columns:
        if col not in names:
            continue
        frame = read_parquet_df(path, columns=list(dict.fromkeys([mode_candidate, col])))
        summaries.append(compute_distribution_summary(frame, [col]))
        result = analyze_behavior_by_mode(frame, [col], mode_col=mode_candidate)
        mode_tables.append(result["summary_table"])
        differences.update(result["mode_differences"])
        if "mode_differences_table" in result and not result["mode_differences_table"].empty:
            diff_rows.append(result["mode_differences_table"])
        del frame

    dist_summary = pd.concat(summaries, ignore_index=True) if summaries else compute_distribution_summary(pd.DataFrame(), [])
    mode_summary = pd.concat(mode_tables, ignore_index=True) if mode_tables else pd.DataFrame()
    diff_table = pd.concat(diff_rows, ignore_index=True) if diff_rows else pd.DataFrame()

    significant_count = sum(v.get("is_significant", False) for v in differences.values())

    return (
        dist_summary,
        {
            "summary_table": mode_summary,
            "mode_differences": differences,
            "recommended_rq2_strategy": "per_mode" if significant_count >= 2 else "overall",
        },
    )
