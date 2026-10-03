from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

import duckdb
import numpy as np
import pandas as pd

from src.data.io import atomic_write_json, atomic_write_parquet
from src.utils.hashing import hash_dict
from src.utils.logging import get_logger

logger = get_logger("pubg_splits")


def _nearest_block_cut(block_sizes: list[int], target_rows: float, minimum: int, maximum: int) -> int:
    """Return a block boundary index nearest a row-count target."""
    if maximum < minimum:
        return minimum
    cumulative = np.cumsum(block_sizes)
    candidates = range(minimum, maximum + 1)
    return min(candidates, key=lambda index: abs(float(cumulative[index - 1]) - target_rows))


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
    chronology_grade: Optional[str] = None,
) -> Dict[str, Any]:
    """Create match-isolated splits and preserve chronology tie blocks."""
    if strategy not in {"chronological", "group_by_match"}:
        raise ValueError(f"Unknown split strategy: {strategy}")
    ratios = np.asarray([train_ratio, val_ratio, test_ratio], dtype=float)
    if not np.isfinite(ratios).all() or (ratios < 0).any() or train_ratio <= 0 or not np.isclose(ratios.sum(), 1):
        raise ValueError("Split ratios must be finite, nonnegative, sum to 1, and train_ratio > 0.")
    if strategy == "chronological" and chronology_grade == "Grade C":
        raise ValueError("Grade C cannot use an official chronological split; use group_by_match.")
    output_assignments_parquet.parent.mkdir(parents=True, exist_ok=True)
    output_manifest_json.parent.mkdir(parents=True, exist_ok=True)

    df_matches = con.execute("""
        SELECT match_id, match_date, observed_player_count
        FROM read_parquet(?)
        ORDER BY match_date ASC, match_id ASC
    """, [str(match_metadata_parquet)]).df()
    if df_matches["match_id"].isna().any() or df_matches["match_id"].duplicated().any():
        raise ValueError("Match metadata must contain one non-null row per match_id.")
    if df_matches.empty:
        raise ValueError("Cannot split empty match metadata!")

    total_matches = len(df_matches)
    boundary_policy = "random_match_groups"
    tie_blocks_split = False

    if strategy == "chronological":
        df_matches["match_date"] = pd.to_datetime(df_matches["match_date"], utc=True, format="mixed", errors="coerce")
        if df_matches["match_date"].isna().any():
            raise ValueError("Chronological split requires valid dates for every match.")
        df_matches = df_matches.sort_values(["match_date", "match_id"]).reset_index(drop=True)
        if chronology_grade == "Grade B":
            df_matches["_block"] = df_matches["match_date"].dt.floor("D")
            boundary_policy = "whole_utc_day_blocks"
        else:
            df_matches["_block"] = df_matches["match_date"]
            boundary_policy = "whole_timestamp_tie_blocks"

        blocks = [
            frame.index.tolist()
            for _, frame in df_matches.groupby("_block", sort=True)
        ]
        active_splits = 1 + int(val_ratio > 0) + int(test_ratio > 0)
        if len(blocks) < active_splits:
            raise ValueError(
                f"Chronological split needs at least {active_splits} chronology blocks; found {len(blocks)}."
            )
        sizes = [len(indices) for indices in blocks]
        remaining_after_train = int(val_ratio > 0) + int(test_ratio > 0)
        train_cut = _nearest_block_cut(
            sizes, total_matches * train_ratio, 1, len(blocks) - remaining_after_train
        )
        if val_ratio > 0:
            remaining_after_val = int(test_ratio > 0)
            val_cut = _nearest_block_cut(
                sizes, total_matches * (train_ratio + val_ratio),
                train_cut + 1,
                len(blocks) - remaining_after_val,
            )
        else:
            val_cut = train_cut

        df_matches["split"] = "test"
        for block in blocks[:train_cut]:
            df_matches.loc[block, "split"] = "train"
        for block in blocks[train_cut:val_cut]:
            df_matches.loc[block, "split"] = "validation"
        if test_ratio == 0:
            for block in blocks[val_cut:]:
                df_matches.loc[block, "split"] = "validation" if val_ratio > 0 else "train"

        block_span = df_matches.groupby("_block")["split"].nunique()
        tie_blocks_split = bool((block_span > 1).any())
        df_matches = df_matches.drop(columns=["_block"])
    else:
        rng = np.random.RandomState(random_state)
        shuffled_ids = df_matches["match_id"].to_numpy(copy=True)
        rng.shuffle(shuffled_ids)
        n_train = int(total_matches * train_ratio)
        n_val = int(total_matches * val_ratio)
        if n_train == 0:
            raise ValueError("Not enough matches for the requested train ratio.")
        train_matches = set(shuffled_ids[:n_train])
        val_matches = set(shuffled_ids[n_train:n_train + n_val])
        df_matches["split"] = df_matches["match_id"].map(
            lambda match_id: "train" if match_id in train_matches else "validation" if match_id in val_matches else "test"
        )
        df_matches["match_date"] = pd.to_datetime(
            df_matches["match_date"], utc=True, format="mixed", errors="coerce"
        )

    atomic_write_parquet(output_assignments_parquet, df_matches[["match_id", "split"]])
    split_sets = {
        split: set(df_matches.loc[df_matches["split"] == split, "match_id"])
        for split in ("train", "validation", "test")
    }
    split_counts = {
        split: int(count)
        for split, count in df_matches["split"].value_counts().to_dict().items()
    }
    player_counts = {
        split: int(count)
        for split, count in df_matches.groupby("split")["observed_player_count"].sum().to_dict().items()
    }
    date_ranges = {}
    for split in ("train", "validation", "test"):
        split_dates = df_matches.loc[df_matches["split"] == split, "match_date"].dropna()
        if not split_dates.empty:
            date_ranges[split] = {"start": str(split_dates.min()), "end": str(split_dates.max())}

    intersections = {
        "train_val": len(split_sets["train"] & split_sets["validation"]),
        "train_test": len(split_sets["train"] & split_sets["test"]),
        "val_test": len(split_sets["validation"] & split_sets["test"]),
    }
    manifest_data = {
        "strategy": strategy,
        "chronology_grade": chronology_grade,
        "boundary_policy": boundary_policy,
        "tie_blocks_split": tie_blocks_split,
        "train_ratio": train_ratio,
        "val_ratio": val_ratio,
        "test_ratio": test_ratio,
        "actual_ratios": {
            split: split_counts.get(split, 0) / total_matches
            for split in ("train", "validation", "test")
        },
        "random_state": random_state,
        "total_matches": total_matches,
        "match_counts": split_counts,
        "estimated_player_counts": player_counts,
        "date_ranges": date_ranges,
        "match_isolation_verified": all(value == 0 for value in intersections.values()),
        "split_intersections": intersections,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    manifest_data["config_hash"] = hash_dict(
        {key: value for key, value in manifest_data.items() if key != "created_at"}
    )
    atomic_write_json(output_manifest_json, manifest_data)
    logger.info(f"Split assignments published: {split_counts} matches.")
    return manifest_data