from pathlib import Path
from src.data.io import atomic_write_csv
from typing import Any, Dict, List, Optional
import pandas as pd
from src.analysis.correlation import compute_bivariate_associations
from src.features.registry import FeatureRegistry
from src.utils.logging import get_logger

logger = get_logger("pubg_rq1")


def run_rq1_analysis(
    df: pd.DataFrame,
    registry: FeatureRegistry,
    output_table_path: Path,
) -> pd.DataFrame:
    """Execute complete RQ1 association analysis across outcomes and modes.

    Invariants:
      1. S1 Survival target MUST NOT use phase timing features derived from match duration (D01).
      2. Rates divided by survive_time (kills_per_minute, walk_velocity) are flagged as diagnostic-only.
      3. Pearson & Spearman computed independently overall and by game mode.
    """
    output_table_path.parent.mkdir(parents=True, exist_ok=True)

    # Outcomes to examine
    tasks_to_run = [
        {"outcome": "player_survive_time", "task_name": "rq1_survival"},
        {"outcome": "normalized_placement", "task_name": "rq1_placement"},
    ]

    mode_map = {1: "Solo", 2: "Duo", 4: "Squad"}
    clean_df = df.copy()
    if "party_size" in clean_df.columns:
        clean_df["mode_label"] = clean_df["party_size"].map(lambda x: mode_map.get(x, f"Other_{x}"))
    else:
        clean_df["mode_label"] = "Overall"

    modes_to_evaluate = ["Overall"] + [m for m in ["Solo", "Duo", "Squad"] if (clean_df["mode_label"] == m).sum() >= 50]

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

            if len(subset_df) < 20:
                continue

            assoc_df = compute_bivariate_associations(
                subset_df,
                feature_cols=allowed_features,
                target_col=outcome,
                target_derived_set=derived_set,
            )
            if assoc_df.empty:
                continue
            assoc_df["mode"] = mode
            # Attach feature group
            assoc_df["group"] = assoc_df["feature"].apply(
                lambda f_name: registry.get(f_name).group if registry.get(f_name) else "unknown"
            )
            all_results.append(assoc_df)

    if not all_results:
        final_table = pd.DataFrame(columns=[
            "feature", "group", "target", "mode", "n_observations", "pearson_r", "pearson_pvalue",
            "spearman_rho", "spearman_pvalue", "is_primary_valid", "target_derived", "notes"])
    else:
        final_table = pd.concat(all_results, ignore_index=True)
        # Reorder columns
        cols = [
            "feature", "group", "target", "mode", "n_observations",
            "pearson_r", "pearson_pvalue", "spearman_rho", "spearman_pvalue",
            "is_primary_valid", "target_derived", "notes"
        ]
        final_table = final_table[[c for c in cols if c in final_table.columns]]

    atomic_write_csv(output_table_path, final_table)
    logger.info(f"RQ1 relationship analysis saved: {len(final_table)} association records -> {output_table_path.name}")
    return final_table
