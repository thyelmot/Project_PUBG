"""Cohort definition, row identification, and sample alignment."""
from typing import Dict, List, Optional, Union
import pandas as pd
import numpy as np


def generate_row_id(
    df: pd.DataFrame,
    match_id_col: str = "match_id",
    player_name_col: str = "player_name",
    raise_on_duplicate: bool = True,
) -> pd.Series:
    """Generate deterministic row_id from match_id and player_name."""
    if match_id_col not in df.columns or player_name_col not in df.columns:
        raise KeyError(f"Missing required columns for row_id: {match_id_col}, {player_name_col}")

    match_series = df[match_id_col].astype(str).str.strip()
    player_series = df[player_name_col].astype(str).str.strip()

    # Check for empty / null
    invalid_mask = (
        (match_series == "")
        | (match_series == "nan")
        | (match_series == "None")
        | (player_series == "")
        | (player_series == "nan")
        | (player_series == "None")
    )
    if invalid_mask.any():
        raise ValueError(f"Found {invalid_mask.sum()} rows with empty or null match_id/player_name")

    row_ids = match_series + "__" + player_series

    if raise_on_duplicate:
        dups = row_ids.duplicated()
        if dups.any():
            dup_sample = row_ids[dups].iloc[0]
            raise ValueError(f"Duplicate row_id generated: {dup_sample} ({dups.sum()} duplicates total)")

    return row_ids


def ensure_row_id(
    df: pd.DataFrame,
    match_id_col: str = "match_id",
    player_name_col: str = "player_name",
) -> pd.DataFrame:
    """Ensure DataFrame has a verified, unique 'row_id' column."""
    df_copy = df.copy()
    if "row_id" in df_copy.columns:
        if df_copy["row_id"].duplicated().any():
            raise ValueError("Existing 'row_id' column contains duplicates")
        if df_copy["row_id"].isna().any():
            raise ValueError("Existing 'row_id' column contains nulls")
    else:
        df_copy["row_id"] = generate_row_id(df_copy, match_id_col, player_name_col)
    return df_copy


def align_cohort_rows(
    dfs: Union[List[pd.DataFrame], Dict[str, pd.DataFrame]],
    row_id_col: str = "row_id",
    target_col: Optional[str] = None,
    split_col: Optional[str] = "split",
) -> Union[List[pd.DataFrame], Dict[str, pd.DataFrame]]:
    """Align multiple candidate dataframes on common row_id intersection."""
    is_dict = isinstance(dfs, dict)
    df_list = list(dfs.values()) if is_dict else dfs

    if not df_list:
        return {} if is_dict else []

    for d in df_list:
        if row_id_col not in d.columns:
            raise KeyError(f"Column '{row_id_col}' missing from one or more dataframes")

    common_keys = set(df_list[0][row_id_col])
    for d in df_list[1:]:
        common_keys = common_keys.intersection(set(d[row_id_col]))

    sorted_keys = sorted(list(common_keys))

    aligned = []
    for d in df_list:
        sub = d[d[row_id_col].isin(common_keys)].copy()
        sub = sub.sort_values(by=row_id_col).reset_index(drop=True)
        aligned.append(sub)

    # Verification of target and split identity across aligned dataframes
    if len(aligned) > 1:
        ref = aligned[0]
        for idx, other in enumerate(aligned[1:], start=1):
            if split_col and split_col in ref.columns and split_col in other.columns:
                if not (ref[split_col].values == other[split_col].values).all():
                    raise ValueError(f"Split mismatch between reference and dataframe at index {idx}")
            if target_col and target_col in ref.columns and target_col in other.columns:
                ref_t = ref[target_col].values
                oth_t = other[target_col].values
                valid_mask = (~pd.isna(ref_t)) & (~pd.isna(oth_t))
                if not np.allclose(ref_t[valid_mask], oth_t[valid_mask], atol=1e-7):
                    raise ValueError(f"Target mismatch between reference and dataframe at index {idx}")

    if is_dict:
        return {k: aligned[i] for i, k in enumerate(dfs.keys())}
    return aligned


def summarize_cohort(
    df: pd.DataFrame,
    split_col: str = "split",
    mode_col: str = "team_size_mode",
    row_id_col: str = "row_id",
) -> pd.DataFrame:
    """Summarize cohort accounting: rows, unique matches, teams, and players."""
    group_cols = [c for c in [split_col, mode_col] if c in df.columns]

    records = []
    if group_cols:
        for keys, grp in df.groupby(group_cols):
            if not isinstance(keys, tuple):
                keys = (keys,)
            row_dict = dict(zip(group_cols, keys))
            row_dict["rows_count"] = len(grp)
            if "match_id" in grp.columns:
                row_dict["matches_count"] = grp["match_id"].nunique()
            if "team_id" in grp.columns:
                row_dict["teams_count"] = grp["team_id"].nunique()
            if "player_name" in grp.columns:
                row_dict["players_count"] = grp["player_name"].nunique()
            records.append(row_dict)
    else:
        row_dict = {"rows_count": len(df)}
        if "match_id" in df.columns:
            row_dict["matches_count"] = df["match_id"].nunique()
        if "team_id" in df.columns:
            row_dict["teams_count"] = df["team_id"].nunique()
        if "player_name" in df.columns:
            row_dict["players_count"] = df["player_name"].nunique()
        records.append(row_dict)

    return pd.DataFrame(records)
