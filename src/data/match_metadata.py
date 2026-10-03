from pathlib import Path
from tempfile import TemporaryDirectory
import math
from typing import Optional

import duckdb

from src.data.io import copy_query_to_parquet
from src.utils.logging import get_logger

logger = get_logger("pubg_match_metadata")


def build_match_metadata(
    con: duckdb.DuckDBPyConnection,
    cleaned_aggregate_parquet: Path,
    output_metadata_parquet: Path,
    audit_report_path: Optional[Path] = None,
) -> int:
    """Build match-level roster metadata without masking within-match conflicts."""
    output_metadata_parquet.parent.mkdir(parents=True, exist_ok=True)
    safe_clean = cleaned_aggregate_parquet.resolve().as_posix().replace("'", "''")
    rows = con.execute(f"SELECT count(*) FROM read_parquet('{safe_clean}')").fetchone()[0]
    buckets = max(1, math.ceil(rows / 1_000_000))

    aggregate = f"""
        WITH team_rollup AS (
            SELECT
                match_id,
                team_id,
                count(DISTINCT team_placement) AS placement_value_count
            FROM read_parquet('{safe_clean}')
            WHERE hash(match_id) % {buckets} = {{bucket}}
            GROUP BY match_id, team_id
        ),
        team_audit AS (
            SELECT
                match_id,
                count(*) FILTER (WHERE placement_value_count > 1) AS team_placement_conflict_count
            FROM team_rollup
            GROUP BY match_id
        ),
        match_rollup AS (
            SELECT
                match_id,
                CASE WHEN count(DISTINCT date) = 1 THEN min(date) ELSE NULL END AS match_date,
                CASE WHEN count(DISTINCT match_mode) = 1 THEN min(match_mode) ELSE NULL END AS match_mode,
                CASE WHEN count(DISTINCT party_size) = 1 THEN min(party_size) ELSE NULL END AS party_size,
                CASE WHEN count(DISTINCT game_size) = 1 THEN min(game_size) ELSE NULL END AS game_size,
                count(DISTINCT team_id) AS observed_team_count,
                count(*) AS observed_player_count,
                max(team_placement) FILTER (WHERE team_placement > 0) AS max_observed_placement,
                max(player_survive_time) FILTER (
                    WHERE player_survive_time >= 0
                      AND NOT (isnan(player_survive_time) OR isinf(player_survive_time))
                ) AS estimated_match_duration,
                count(*) FILTER (WHERE team_id IS NULL OR length(trim(team_id)) = 0) AS missing_team_id_rows,
                count(DISTINCT date) > 1 AS has_date_conflict,
                count(DISTINCT match_mode) > 1 AS has_mode_conflict,
                count(DISTINCT party_size) > 1 AS has_party_size_conflict,
                count(DISTINCT game_size) > 1 AS has_game_size_conflict
            FROM read_parquet('{safe_clean}')
            WHERE hash(match_id) % {buckets} = {{bucket}}
            GROUP BY match_id
        )
        SELECT
            m.*,
            coalesce(t.team_placement_conflict_count, 0) AS team_placement_conflict_count,
            (
                m.observed_team_count >= 2
                AND m.max_observed_placement >= 2
                AND abs(m.observed_team_count - m.max_observed_placement) <= 2
                AND m.missing_team_id_rows = 0
                AND coalesce(t.team_placement_conflict_count, 0) = 0
            ) AS is_roster_complete,
            (
                m.has_date_conflict OR m.has_mode_conflict
                OR m.has_party_size_conflict OR m.has_game_size_conflict
            ) AS has_metadata_conflict
        FROM match_rollup m
        LEFT JOIN team_audit t USING (match_id)
    """

    temp_root = Path(con.execute("SELECT current_setting('temp_directory')").fetchone()[0])
    temp_root.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix="metadata_", dir=temp_root) as directory:
        parts = []
        for bucket in range(buckets):
            part = (Path(directory) / f"part_{bucket}.parquet").as_posix().replace("'", "''")
            con.execute(f"COPY ({aggregate.format(bucket=bucket)}) TO '{part}' (FORMAT PARQUET, COMPRESSION 'ZSTD')")
            parts.append("'" + part + "'")
            logger.info(f"Match metadata: bucket {bucket + 1}/{buckets} completed")
        total_matches = copy_query_to_parquet(
            con, f"SELECT * FROM read_parquet([{','.join(parts)}])", output_metadata_parquet
        )

    if audit_report_path:
        safe_output = output_metadata_parquet.resolve().as_posix().replace("'", "''")
        audit_res = con.execute(f"""
            SELECT
                count(*) AS total_matches,
                count(*) FILTER (WHERE has_date_conflict) AS date_conflicts,
                count(*) FILTER (WHERE has_mode_conflict) AS mode_conflicts,
                count(*) FILTER (WHERE has_party_size_conflict) AS party_size_conflicts,
                count(*) FILTER (WHERE has_game_size_conflict) AS game_size_conflicts,
                count(*) FILTER (WHERE team_placement_conflict_count > 0) AS team_placement_conflict_matches,
                sum(missing_team_id_rows) AS missing_team_id_rows,
                count(*) FILTER (WHERE is_roster_complete) AS roster_complete_matches,
                avg(observed_player_count) AS avg_players_per_match,
                avg(observed_team_count) AS avg_teams_per_match
            FROM read_parquet('{safe_output}')
        """).df().to_dict(orient="records")[0]
        from src.data.io import atomic_write_json
        atomic_write_json(Path(audit_report_path), audit_res)

    logger.info(f"Built match metadata for {total_matches} unique matches -> {output_metadata_parquet.name}")
    return total_matches