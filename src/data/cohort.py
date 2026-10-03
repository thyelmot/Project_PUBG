"""Cohort definition, row identification, and sample alignment."""
from typing import Dict, List, Optional, Union
import pandas as pd
import numpy as np


def _encode_identity(value: str) -> str:
    """Length-prefix one component so separators inside values cannot collide."""
    return f"{len(value)}:{value}"


def generate_row_id(
    df: pd.DataFrame,
    match_id_col: str = "match_id",
    player_name_col: str = "player_name",
    source_file_col: str = "source_file",
    source_row_col: str = "source_row",
    raise_on_duplicate: bool = True,
) -> pd.Series:
    """Generate a collision-safe player-match ID, falling back to source lineage."""
    if match_id_col not in df.columns or player_name_col not in df.columns:
        raise KeyError(f"Missing required columns for row_id: {match_id_col}, {player_name_col}")

    def clean(value):
        return None if pd.isna(value) or not str(value).strip() else str(value).strip()

    row_ids = []
    missing_lineage = 0
    has_lineage = source_file_col in df.columns and source_row_col in df.columns
    for index, row in df.iterrows():
        match_id = clean(row[match_id_col])
        player_name = clean(row[player_name_col])
        if match_id is None:
            raise ValueError(f"Found empty or null match_id at row {index}")
        if player_name is not None:
            identity = "player:" + _encode_identity(player_name)
        elif has_lineage:
            source_file = clean(row[source_file_col])
            source_row = clean(row[source_row_col])
            if source_file is None or source_row is None:
                missing_lineage += 1
                identity = ""
            else:
                identity = "lineage:" + _encode_identity(source_file) + _encode_identity(source_row)
        else:
            missing_lineage += 1
            identity = ""
        row_ids.append("match:" + _encode_identity(match_id) + "|" + identity)

    if missing_lineage:
        raise ValueError(
            f"Found {missing_lineage} rows without player_name or complete source_file/source_row lineage"
        )
    row_ids = pd.Series(row_ids, index=df.index, name="row_id", dtype="string")

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
    require_exact: bool = False,
) -> Union[List[pd.DataFrame], Dict[str, pd.DataFrame]]:
    """Align pre-fit cohorts; evaluation callers can require identical row-ID sets."""
    is_dict = isinstance(dfs, dict)
    df_list = list(dfs.values()) if is_dict else dfs

    if not df_list:
        return {} if is_dict else []

    for d in df_list:
        if row_id_col not in d.columns:
            raise KeyError(f"Column '{row_id_col}' missing from one or more dataframes")
        if d[row_id_col].isna().any() or d[row_id_col].duplicated().any():
            raise ValueError(f"Column '{row_id_col}' must be non-null and unique in every dataframe")

    common_keys = set(df_list[0][row_id_col])
    for index, d in enumerate(df_list[1:], start=1):
        keys = set(d[row_id_col])
        if require_exact and keys != common_keys:
            raise ValueError(
                f"row_id set mismatch at dataframe {index}: "
                f"reference_only={len(common_keys - keys)}, candidate_only={len(keys - common_keys)}"
            )
        common_keys.intersection_update(keys)

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
                if not np.allclose(ref_t, oth_t, atol=1e-7, equal_nan=True):
                    raise ValueError(f"Target mismatch between reference and dataframe at index {idx}")

    if is_dict:
        return {k: aligned[i] for i, k in enumerate(dfs.keys())}
    return aligned


def summarize_cohort(
    df: pd.DataFrame,
    split_col: str = "split",
    mode_col: str = "team_size_mode",
    row_id_col: str = "row_id",
    eligibility_rule: str = "",
    exclusions: Optional[Dict[str, int]] = None,
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
            row_dict.update(matches_count=grp["match_id"].nunique() if "match_id" in grp else 0,
                            teams_count=grp["team_id"].nunique() if "team_id" in grp else 0,
                            players_count=grp["player_name"].nunique() if "player_name" in grp else 0)
            records.append(row_dict)
    else:
        row_dict = {"rows_count": len(df)}
        row_dict.update(matches_count=df["match_id"].nunique() if "match_id" in df else 0,
                        teams_count=df["team_id"].nunique() if "team_id" in df else 0,
                        players_count=df["player_name"].nunique() if "player_name" in df else 0)
        records.append(row_dict)

    result = pd.DataFrame(records)
    result["eligibility_rule"] = eligibility_rule
    result["exclusions"] = "; ".join(
        f"{reason}={count}" for reason, count in sorted((exclusions or {}).items())
    )
    return result
