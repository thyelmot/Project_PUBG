"""Public history API; the verified workflow owns the canonical formulas."""
from pathlib import Path
import pandas as pd
from src.data.io import atomic_write_csv, copy_query_to_parquet
from src.features.history_workflow import history_query, leakage_audit, literal, threshold_value, TASKS
from src.utils.hashing import hash_dict, hash_file


def compute_history_depth_diagnostics(con, player_match_parquet, output_coverage_csv=None,
                                    thresholds=(1,3,5,10), chronology_grade="Grade C",
                                    availability_config=None):
    query=history_query(con,player_match_parquet,chronology_grade,None,availability_config)
    rows=[]
    for t in thresholds:
        if threshold_value(t) is None:
            raise ValueError("Diagnostic threshold cannot be null.")
        rows.append(con.execute(f"""SELECT {t} AS threshold,count(*) AS total_rows,
            count(*) FILTER (WHERE hist_games_played>={t}) AS eligible_rows,
            count(*) FILTER (WHERE hist_games_played>={t})::DOUBLE/nullif(count(*),0) AS eligible_fraction
            FROM ({query})""").df())
    result=pd.concat(rows,ignore_index=True)
    result["chronology_grade"]=chronology_grade
    if output_coverage_csv:
        atomic_write_csv(output_coverage_csv,result)
    return result


def audit_historical_leakage(con,historical_parquet,output_audit_csv=None):
    result=leakage_audit(con,historical_parquet)
    if output_audit_csv:
        atomic_write_csv(output_audit_csv,result)
    return result


def build_historical_features(con,player_match_parquet,output_historical_parquet,
        chronology_grade="Grade C",min_history_threshold=None,coverage_table_path=None,
        leakage_audit_path=None,checkpoint_mgr=None,registry=None,availability_config=None):
    """Low-level build, not official publication; NB08 additionally verifies G3 provenance."""
    threshold=threshold_value(min_history_threshold)
    if chronology_grade not in {"Grade A","Grade B","Grade C"}:
        raise ValueError(f"Unknown chronology grade: {chronology_grade}")
    reason="blocked_by_chronology" if chronology_grade=="Grade C" else (
        "minimum_history_threshold_pending" if threshold is None else None)
    result={"status":"blocked" if chronology_grade=="Grade C" else "pending",
        "reason_code":reason,"decision_gate":"G3","min_history_threshold":threshold,
        "chronology_grade":chronology_grade,"output_path":None,"eligible_historical_records":0}
    if reason:
        for task in TASKS:
            if checkpoint_mgr:
                checkpoint_mgr.record_blocked(task,hash_dict(result),reason,result)
            if registry:
                registry.update_status(task,"blocked",reason_code=reason)
        return result
    query=history_query(con,player_match_parquet,chronology_grade,threshold,availability_config)
    rows=copy_query_to_parquet(con,query,Path(output_historical_parquet))
    eligible=con.execute(f"SELECT count(*) FROM read_parquet({literal(output_historical_parquet)}) WHERE has_sufficient_history").fetchone()[0]
    if coverage_table_path:
        compute_history_depth_diagnostics(con,player_match_parquet,coverage_table_path,
            chronology_grade=chronology_grade,availability_config=availability_config)
    if leakage_audit_path:
        audit_historical_leakage(con,output_historical_parquet,leakage_audit_path)
    result.update(status="completed" if eligible else "blocked",reason_code=None if eligible else "no_eligible_history",
        total_player_records=rows,eligible_historical_records=eligible,coverage_ratio=eligible/rows if rows else 0.,
        output_path=str(output_historical_parquet),output_checksum=hash_file(output_historical_parquet))
    return result
