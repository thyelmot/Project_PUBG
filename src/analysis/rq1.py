from pathlib import Path
from typing import Any, Dict, List, Optional
import pyarrow.parquet as pq
import pandas as pd
import numpy as np

from src.data.io import atomic_write_csv, atomic_write_json, read_parquet_df
from src.analysis.correlation import compute_bivariate_associations
from src.features.registry import FeatureRegistry
from src.utils.logging import get_logger

logger = get_logger("pubg_rq1")


def classify_correlation_strength(r: float) -> str:
    """Classify correlation magnitude according to standard conventions.

    Conventions:
      |r| < 0.10: negligible
      0.10 <= |r| < 0.30: weak
      0.30 <= |r| < 0.50: moderate
      |r| >= 0.50: strong
    """
    if pd.isna(r):
        return "unspecified"
    abs_r = abs(r)
    if abs_r < 0.10:
        return "negligible"
    elif abs_r < 0.30:
        return "weak"
    elif abs_r < 0.50:
        return "moderate"
    else:
        return "strong"


def run_rq1_analysis(
    df: pd.DataFrame | Path,
    registry: FeatureRegistry,
    output_table_path: Path,
    min_observations_per_mode: int = 20,
    analysis_scope: str = "unspecified",
) -> pd.DataFrame:
    """Execute complete RQ1 association analysis across outcomes and modes.

    Invariants:
      1. S1 Survival target MUST NOT use phase timing features derived from match duration (D01).
      2. Rates divided by survive_time (kills_per_minute, walk_velocity) are flagged as diagnostic-only.
      3. Pearson & Spearman computed independently overall and by game mode.
      4. Preserves signed correlation coefficients and reports sample size N and validity notes.
    """
    output_table_path.parent.mkdir(parents=True, exist_ok=True)

    # Outcomes to examine
    tasks_to_run = [
        {"outcome": "player_survive_time", "task_name": "rq1_survival"},
        {"outcome": "normalized_placement", "task_name": "rq1_placement"},
    ]

    parquet_path = Path(df) if isinstance(df, (str, Path)) else None

    if parquet_path is not None:
        schema = pq.read_schema(parquet_path).names
        if "team_size_mode" in schema:
            clean_df = read_parquet_df(parquet_path, columns=["team_size_mode"])
            mode_map = {"solo": "Solo", "duo": "Duo", "squad": "Squad"}
            normalized_mode = clean_df["team_size_mode"].astype("string").str.lower()
            unknown = sorted(set(normalized_mode.dropna()) - set(mode_map))
            if unknown:
                raise ValueError(f"Unverified team_size_mode values: {unknown}")
            clean_df["mode_label"] = normalized_mode.map(mode_map)
        elif "party_size" in schema:
            clean_df = read_parquet_df(parquet_path, columns=["party_size"])
            mode_map = {1: "Solo", 2: "Duo", 4: "Squad"}
            unknown = sorted(set(clean_df["party_size"].dropna()) - set(mode_map))
            if unknown:
                raise ValueError(f"Unverified party_size values: {unknown}")
            clean_df["mode_label"] = clean_df["party_size"].map(mode_map)
        else:
            clean_df = pd.DataFrame(index=pd.RangeIndex(pq.ParquetFile(parquet_path).metadata.num_rows))
            clean_df["mode_label"] = "Overall"
    else:
        clean_df = df.copy()
        if "team_size_mode" in clean_df.columns:
            mode_map = {"solo": "Solo", "duo": "Duo", "squad": "Squad"}
            normalized_mode = clean_df["team_size_mode"].astype("string").str.lower()
            unknown = sorted(set(normalized_mode.dropna()) - set(mode_map))
            if unknown:
                raise ValueError(f"Unverified team_size_mode values: {unknown}")
            clean_df["mode_label"] = normalized_mode.map(mode_map)
        elif "party_size" in clean_df.columns:
            mode_map = {1: "Solo", 2: "Duo", 4: "Squad"}
            unknown = sorted(set(clean_df["party_size"].dropna()) - set(mode_map))
            if unknown:
                raise ValueError(f"Unverified party_size values: {unknown}")
            clean_df["mode_label"] = clean_df["party_size"].map(mode_map)
        else:
            clean_df["mode_label"] = "Overall"

    modes_to_evaluate = ["Overall"] + [
        m for m in ["Solo", "Duo", "Squad"]
        if (clean_df["mode_label"] == m).sum() >= min_observations_per_mode
    ]

    all_results = []

    for task_info in tasks_to_run:
        outcome = task_info["outcome"]
        task_name = task_info["task_name"]

        # Authorized features according to registry
        allowed_features = registry.get_allowed_features(task_name)
        # Target derived set
        derived_set = {
            f.name for f in registry.list_all()
            if f.target_derived or (outcome == "player_survive_time" and f.group == "combat_timing_phase")
        }

        for mode in modes_to_evaluate:
            subset_df = clean_df if mode == "Overall" else clean_df[clean_df["mode_label"] == mode]

            if len(subset_df) < min_observations_per_mode:
                continue

            if parquet_path is None:
                assoc_df = compute_bivariate_associations(
                    subset_df, feature_cols=allowed_features, target_col=outcome,
                    target_derived_set=derived_set,
                )
            else:
                if outcome not in schema:
                    raise ValueError(f"Target column {outcome} missing from dataset.")
                pair_results = []
                for feature in allowed_features:
                    if feature not in schema:
                        continue
                    pair = read_parquet_df(parquet_path, columns=list(dict.fromkeys([feature, outcome])))
                    if mode != "Overall":
                        pair = pair.loc[clean_df["mode_label"] == mode]
                    pair_results.append(compute_bivariate_associations(
                        pair, feature_cols=[feature], target_col=outcome,
                        target_derived_set=derived_set,
                    ))
                    del pair
                assoc_df = pd.concat(pair_results, ignore_index=True) if pair_results else pd.DataFrame()

            if assoc_df.empty:
                continue
            assoc_df["mode"] = mode
            assoc_df["analysis_scope"] = analysis_scope
            # Attach feature group
            assoc_df["group"] = assoc_df["feature"].apply(
                lambda f_name: registry.get(f_name).group if registry.get(f_name) else "unknown"
            )
            all_results.append(assoc_df)

    if not all_results:
        final_table = pd.DataFrame(columns=[
            "feature", "group", "target", "mode", "analysis_scope", "n_observations", "pearson_r", "pearson_pvalue",
            "spearman_rho", "spearman_pvalue", "status", "is_primary_valid", "target_derived", "notes"
        ])
    else:
        final_table = pd.concat(all_results, ignore_index=True)
        # Reorder columns
        cols = [
            "feature", "group", "target", "mode", "analysis_scope", "n_observations",
            "pearson_r", "pearson_pvalue", "spearman_rho", "spearman_pvalue",
            "status", "is_primary_valid", "target_derived", "notes"
        ]
        final_table = final_table[[c for c in cols if c in final_table.columns]]

    atomic_write_csv(output_table_path, final_table)
    logger.info(f"RQ1 relationship analysis saved: {len(final_table)} association records -> {output_table_path.name}")
    return final_table


def generate_rq1_interpretations(
    rq1_df: pd.DataFrame,
    output_json_path: Optional[Path] = None,
) -> Dict[str, Any]:
    """Generate structured scientific interpretations and study limitations for RQ1."""
    interpretations: Dict[str, Any] = {
        "primary_findings": {},
        "divergences_linear_vs_monotonic": [],
        "mode_variations": [],
        "analysis_scope": sorted(rq1_df["analysis_scope"].dropna().astype(str).unique().tolist()) if "analysis_scope" in rq1_df else ["unspecified"],
        "population": "Eligible player-match rows within the declared analysis scope; repeated players and shared team outcomes are not independent units.",
        "confounders": ["opportunity_time", "repeated_player", "shared_team_outcome", "mode_and_match_conditions"],
        "methodological_limitations": [
            "Repeated player observations: Several players contribute multiple matches, which violates the strict independent and identically distributed (i.i.d.) assumption.",
            "Opportunity time bias: Players who survive longer naturally have more game time to accumulate kills, damage, and distance.",
            "Observational nature: All coefficients represent observed statistical associations, not causal relationships.",
            "D01 Disclosure: Phase timing features are excluded from primary survival predictors to prevent indirect leakage from duration proxy.",
            "Repeated team outcome: Multiple player rows can share one team placement, so row-level associations do not imply independent team outcomes.",
            "Multiple testing: Many feature-target-mode pairs are inspected; p-values are descriptive and are not used alone to claim strong evidence.",
            "Retrospective scope: Current-match variables are observed after or during the match and do not establish prospective utility.",
        ],
    }

    # Extract top predictors for each target in Overall mode
    for target in ["player_survive_time", "normalized_placement"]:
        valid_subset = rq1_df[
            (rq1_df["target"] == target) &
            (rq1_df["mode"] == "Overall") &
            (rq1_df["is_primary_valid"] == True) &
            (rq1_df["pearson_r"].notna())
        ].copy()

        if not valid_subset.empty:
            valid_subset["abs_r"] = valid_subset["pearson_r"].abs()
            top_features = valid_subset.sort_values(by="abs_r", ascending=False).head(3)
            interpretations["primary_findings"][target] = [
                {
                    "feature": row["feature"],
                    "group": row["group"],
                    "pearson_r": round(float(row["pearson_r"]), 4),
                    "spearman_rho": round(float(row["spearman_rho"]), 4),
                    "strength": classify_correlation_strength(row["pearson_r"]),
                    "n_observations": int(row["n_observations"]),
                    "direction": "positive" if row["pearson_r"] > 0 else "negative",
                    "analysis_scope": row.get("analysis_scope", "unspecified"),
                }
                for _, row in top_features.iterrows()
            ]

    # Check linear vs monotonic divergences (|rho - r| >= 0.10)
    divergent = rq1_df[
        (rq1_df["mode"] == "Overall") &
        (rq1_df["is_primary_valid"] == True) &
        (rq1_df["pearson_r"].notna()) &
        (rq1_df["spearman_rho"].notna()) &
        ((rq1_df["spearman_rho"] - rq1_df["pearson_r"]).abs() >= 0.10)
    ]
    for _, row in divergent.iterrows():
        interpretations["divergences_linear_vs_monotonic"].append({
            "feature": row["feature"],
            "target": row["target"],
            "pearson_r": round(float(row["pearson_r"]), 4),
            "spearman_rho": round(float(row["spearman_rho"]), 4),
            "difference": round(float(abs(row["spearman_rho"] - row["pearson_r"])), 4),
            "interpretation": "Pearson and Spearman differ materially; inspect non-linearity, outliers, and ties before interpretation.",
        })

    valid_modes = rq1_df[
        (rq1_df["mode"] != "Overall") & rq1_df["is_primary_valid"].eq(True) & rq1_df["pearson_r"].notna()
    ]
    for (target, feature), group in valid_modes.groupby(["target", "feature"]):
        if group["mode"].nunique() < 2:
            continue
        strongest = group.loc[group["pearson_r"].abs().idxmax()]
        weakest = group.loc[group["pearson_r"].abs().idxmin()]
        interpretations["mode_variations"].append({
            "target": target,
            "feature": feature,
            "strongest_mode": strongest["mode"],
            "strongest_pearson_r": round(float(strongest["pearson_r"]), 4),
            "weakest_mode": weakest["mode"],
            "weakest_pearson_r": round(float(weakest["pearson_r"]), 4),
            "absolute_magnitude_gap": round(float(abs(strongest["pearson_r"]) - abs(weakest["pearson_r"])), 4),
        })

    if output_json_path is not None:
        atomic_write_json(output_json_path, interpretations)
        logger.info(f"RQ1 structured interpretations saved -> {output_json_path.name}")

    return interpretations
