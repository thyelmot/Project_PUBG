from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
import duckdb
import numpy as np
import pandas as pd
from src.data.io import atomic_write_json, atomic_write_parquet
from src.utils.hashing import hash_dict
from src.utils.logging import get_logger

logger = get_logger("pubg_splits")


def create_split_assignments(
    con: duckdb.DuckDBPyConnection,
    match_metadata_parquet: Path,
    output_assignments_parquet: Path,
    output_manifest_json: Path,
    strategy: str = "chronological",
    train_ratio: float = 0.70,
    val_ratio: float = 0.15,
    test_ratio: float = 0.15,
    random_state: int = 42,
) -> Dict[str, Any]:
    """Create strict match-isolated train/validation/test split assignments."""
    if strategy not in {"chronological", "group_by_match"}:
        raise ValueError(f"Unknown split strategy: {strategy}")
    ratios = np.asarray([train_ratio, val_ratio, test_ratio], dtype=float)
    if not np.isfinite(ratios).all() or (ratios < 0).any() or train_ratio <= 0 or not np.isclose(ratios.sum(), 1):
        raise ValueError("Split ratios must be finite, nonnegative, sum to 1, and train_ratio > 0.")
    output_assignments_parquet.parent.mkdir(parents=True, exist_ok=True)
    output_manifest_json.parent.mkdir(parents=True, exist_ok=True)

    # Fetch unique match metadata
    df_matches = con.execute("""
        SELECT match_id, match_date, observed_player_count
        FROM read_parquet(?)
        ORDER BY match_date ASC, match_id ASC;
    """, [str(match_metadata_parquet)]).df()
    if df_matches["match_id"].isna().any() or df_matches["match_id"].duplicated().any():
        raise ValueError("Match metadata must contain one non-null row per match_id.")

    total_matches = len(df_matches)
    if total_matches == 0:
        raise ValueError("Cannot split empty match metadata!")

    n_train = int(total_matches * train_ratio)
    n_val = int(total_matches * val_ratio)
    n_test = total_matches - n_train - n_val
    if n_train == 0:
        raise ValueError("Not enough matches for the requested train ratio.")

    if strategy == "chronological":
        df_matches["match_date"] = pd.to_datetime(df_matches["match_date"], utc=True, format="mixed", errors="coerce")
        if df_matches["match_date"].isna().any():
            raise ValueError("Chronological split requires valid dates for every match.")
        # Sort strictly by match_date
        df_matches = df_matches.sort_values(by=["match_date", "match_id"]).reset_index(drop=True)
        train_matches = set(df_matches.iloc[:n_train]["match_id"])
        val_matches = set(df_matches.iloc[n_train: n_train + n_val]["match_id"])
        test_matches = set(df_matches.iloc[n_train + n_val:]["match_id"])
    else:
        # Group by match random split
        rng = np.random.RandomState(random_state)
        shuffled_ids = df_matches["match_id"].values.copy()
        rng.shuffle(shuffled_ids)
        train_matches = set(shuffled_ids[:n_train])
        val_matches = set(shuffled_ids[n_train: n_train + n_val])
        test_matches = set(shuffled_ids[n_train + n_val:])

    def assign_split(mid: str) -> str:
        if mid in train_matches:
            return "train"
        elif mid in val_matches:
            return "validation"
        return "test"

    df_matches["split"] = df_matches["match_id"].apply(assign_split)

    # Save assignments parquet
    atomic_write_parquet(output_assignments_parquet, df_matches[["match_id", "split"]])

    split_counts = df_matches["split"].value_counts().to_dict()
    player_counts = df_matches.groupby("split")["observed_player_count"].sum().to_dict()

    manifest_data = {
        "strategy": strategy,
        "train_ratio": train_ratio,
        "val_ratio": val_ratio,
        "test_ratio": test_ratio,
        "random_state": random_state,
        "total_matches": total_matches,
        "match_counts": split_counts,
        "estimated_player_counts": player_counts,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    manifest_data["config_hash"] = hash_dict({k: v for k, v in manifest_data.items() if k != "created_at"})

    atomic_write_json(output_manifest_json, manifest_data)
    logger.info(f"Split assignments published: {split_counts} matches.")
    return manifest_data
