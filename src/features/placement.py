from typing import Optional

import duckdb
import pandas as pd


def normalized_placement_sql(player_alias: str = "a", metadata_alias: str = "m") -> str:
    """Return the canonical DuckDB expression for roster-normalized placement."""
    return f"""CASE
        WHEN {placement_valid_sql(player_alias, metadata_alias)}
        THEN 1.0 - (
            CAST({player_alias}.team_placement - 1 AS DOUBLE)
            / ({metadata_alias}.observed_team_count - 1)
        )
        ELSE NULL
    END"""


def placement_valid_sql(player_alias: str = "a", metadata_alias: str = "m") -> str:
    """Return the exact validity predicate used by normalized_placement_sql."""
    return f"""(
        isfinite({metadata_alias}.observed_team_count)
        AND isfinite({player_alias}.team_placement)
        AND {metadata_alias}.observed_team_count > 1
        AND {player_alias}.team_placement BETWEEN 1 AND {metadata_alias}.observed_team_count
        AND COALESCE({metadata_alias}.is_roster_complete, false)
    )"""


def compute_normalized_placement(
    team_placement: pd.Series,
    observed_team_count: pd.Series,
    is_roster_complete: Optional[pd.Series] = None,
) -> pd.DataFrame:
    """Small-frame adapter to canonical SQL; invalid values are never clipped."""
    inputs = pd.DataFrame({
        "team_placement": team_placement.astype("float64").to_numpy(),
        "observed_team_count": observed_team_count.astype("float64").to_numpy(),
        "is_roster_complete": True if is_roster_complete is None else is_roster_complete.fillna(False).astype(bool).to_numpy(),
    })
    with duckdb.connect(":memory:") as connection:
        connection.register("a", inputs)
        result = connection.execute(f"""SELECT
            {normalized_placement_sql('a', 'a')} AS normalized_placement,
            COALESCE({placement_valid_sql('a', 'a')}, false) AS placement_valid FROM a""").df()
    result.index = team_placement.index
    result.insert(0, "team_placement", team_placement.to_numpy())
    result.insert(1, "observed_team_count", observed_team_count.to_numpy())
    return result
