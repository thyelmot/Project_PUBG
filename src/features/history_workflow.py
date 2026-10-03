"""Verified NB08 publication; availability blocks, development diagnostics, safe handoff."""
from pathlib import Path
from datetime import datetime, timezone
import shutil
import tempfile

import duckdb
import pandas as pd

from src.data.io import atomic_write_csv, atomic_write_json, copy_query_to_parquet, publish_file, read_json
from src.utils.hashing import hash_dict, hash_file, hash_source_files

FEATURES = {
    "kills": ("player_kills", "hist_kills_mean", "count"),
    "damage": ("player_dmg", "hist_dmg_mean", "source_damage_unit"),
    "walk": ("player_dist_walk", "hist_walk_mean", "source_distance_unit"),
    "ride": ("player_dist_ride", "hist_ride_mean", "source_distance_unit"),
    "assists": ("player_assists", "hist_assists_mean", "count"),
    "dbno": ("player_dbno", "hist_dbno_mean", "count"),
    "survival": ("player_survive_time", "hist_survive_mean", "source_time_unit"),
    "placement": ("normalized_placement", "hist_placement_mean", "fraction_0_1"),
}
TASKS = ("s2_historical_survival", "p3_historical_placement")


def literal(path):
    return "'" + Path(path).resolve().as_posix().replace("'", "''") + "'"


def threshold_value(value):
    if value is not None and (isinstance(value, bool) or not isinstance(value, int) or value < 1):
        raise ValueError("minimum_history_threshold must be a positive integer or None.")
    return value


def code_hash():
    root = Path(__file__).resolve().parents[2]
    return hash_source_files([Path(__file__), root / "src/features/historical.py",
        root / "src/features/registry.py", root / "src/data/io.py", root / "src/data/checkpoints.py",
        root / "src/utils/hashing.py", root / "src/utils/generate_notebooks.py"])


def diagnostic_settings(settings):
    return {k: v for k, v in settings.items() if k not in
        {"threshold_decision_reason", "threshold_diagnostics_hash", "evaluation_protocol"}}


def receipt_hash(receipt):
    # Free spill disk changes between runs; do not make a research decision depend on it.
    evidence={k:v for k,v in receipt.items() if k!="diagnostics_hash"}
    evidence["tables"]={k:v for k,v in receipt["tables"].items() if k!="history_resource_audit"}
    return hash_dict(evidence)


def history_query(con, source, grade, threshold, availability):
    """Cumulative sums/counts of whole availability blocks + strict ASOF lookup.

    A excludes timestamp ties. B accumulates whole availability days, so all
    current-day matches share previous-day state. No ID/file order breaks ties.
    """
    if grade not in {"Grade A", "Grade B"}:
        raise ValueError("Grade C cannot construct a historical modeling dataset.")
    columns = [r[0] for r in con.execute(f"DESCRIBE SELECT * FROM read_parquet({literal(source)})").fetchall()]
    required = {"match_id", "player_name", "team_id", "date"} | {v[0] for v in FEATURES.values()}
    if required - set(columns):
        raise ValueError(f"History missing columns: {sorted(required-set(columns))}")
    if not availability or availability.get("status") != "verified" or not availability.get("evidence"):
        raise ValueError("Availability pending: verify source evidence before history.")
    def column(name):
        if name not in columns:
            raise ValueError(f"Availability column missing: {name}")
        return '"' + name.replace('"', '""') + '"'
    policy = availability.get("policy")
    if policy == "explicit_columns":
        if availability.get("timestamp_semantics") != "prediction_and_statistic_availability":
            raise ValueError("Explicit columns require documented prediction/availability semantics.")
        prediction = f"TRY_CAST({column(availability.get('prediction_column'))} AS TIMESTAMPTZ)"
        available = f"TRY_CAST({column(availability.get('available_column'))} AS TIMESTAMPTZ)"
    elif policy == "start_plus_verified_duration":
        if availability.get("timestamp_semantics") != "match_start" or availability.get("duration_unit") != "seconds":
            raise ValueError("Requires verified match_start and duration seconds.")
        duration = column(availability.get("duration_column"))
        if duration == '"player_survive_time"':
            raise ValueError("Player survival is not match completion duration.")
        prediction = "TRY_CAST(date AS TIMESTAMPTZ)"
        available = f"{prediction} + TRY_CAST({duration} AS DOUBLE)*INTERVAL 1 SECOND"
    else:
        raise ValueError(f"Unsupported availability policy: {policy}")
    mode = "team_size_mode" if "team_size_mode" in columns else "'unknown'"
    con.execute(f"""CREATE OR REPLACE TEMP VIEW history_input AS SELECT *,
        {prediction} AS prediction_at, {available} AS available_at, {mode} AS history_mode
        FROM read_parquet({literal(source)})""")
    bad = con.execute("""SELECT count(*) FROM history_input WHERE
        prediction_at IS NULL OR available_at IS NULL OR available_at < prediction_at
        OR TRY_CAST(date AS TIMESTAMPTZ) IS NULL
        OR prediction_at < TRY_CAST(date AS TIMESTAMPTZ)
        OR match_id IS NULL OR length(trim(match_id))=0""").fetchone()[0]
    if bad:
        raise ValueError(f"Invalid prediction/availability times: {bad} rows.")
    valid = "player_name IS NOT NULL AND length(trim(player_name))>0"
    dup = con.execute(f"SELECT count(*) FROM (SELECT match_id,player_name FROM history_input WHERE {valid} GROUP BY 1,2 HAVING count(*)>1)").fetchone()[0]
    conflict = con.execute("""SELECT count(*) FROM (SELECT match_id FROM history_input GROUP BY 1
        HAVING count(DISTINCT prediction_at)!=1 OR count(DISTINCT available_at)!=1)""").fetchone()[0]
    if dup or conflict:
        raise ValueError("Duplicate player-match or conflicting match availability; repair upstream.")
    block = "available_at" if grade=="Grade A" else "date_trunc('day',available_at)"
    cutoff = "prediction_at" if grade=="Grade A" else "date_trunc('day',prediction_at)"
    aggregates, states, features = [], [], []
    for key, (raw, mean, _) in FEATURES.items():
        predicate = f"isfinite({raw}) AND {raw}>=0" + (f" AND {raw}<=1" if key=="placement" else "")
        value = f"CASE WHEN {predicate} THEN {raw} END"
        aggregates += [f"count({value}) AS {key}_n", f"sum({value}) AS {key}_sum"]
        states += [f"sum({key}_n) OVER w AS {key}_n", f"sum({key}_sum) OVER w AS {key}_sum"]
        features += [f"coalesce(h.{key}_n,0)::BIGINT AS hist_{key}_count",
                     f"h.{key}_sum/nullif(h.{key}_n,0) AS {mean}"]
    eligible = "false" if threshold is None else f"coalesce(h.games,0)>={threshold}"
    return f"""WITH blocks AS (
      SELECT player_name,{block} AS block_at,count(*) AS games,max(available_at) AS max_available,
        {', '.join(aggregates)} FROM history_input WHERE {valid} GROUP BY 1,2
    ), states AS (
      SELECT player_name,block_at,sum(games) OVER w AS games,max(max_available) OVER w AS max_available,
        {', '.join(states)} FROM blocks WINDOW w AS (PARTITION BY player_name ORDER BY block_at
          ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW)
    ), current_rows AS (SELECT *,{cutoff} AS history_cutoff FROM history_input WHERE {valid})
    SELECT ('match:'||length(c.match_id)||':'||c.match_id||'|player:'||length(c.player_name)||':'||c.player_name) AS row_id,
      c.match_id,c.player_name,c.team_id,c.date,CAST(timezone('UTC',c.prediction_at) AS DATE) AS match_date,
      c.history_mode AS team_size_mode,c.prediction_at,c.history_cutoff,h.max_available AS max_history_available_at,
      '{grade}' AS chronology_grade,'{policy}' AS availability_policy,
      '{'strict_timestamp' if grade=='Grade A' else 'strict_previous_days'}' AS history_policy,
      c.player_survive_time AS current_survive_time,c.normalized_placement AS current_normalized_placement,
      coalesce(h.games,0)::BIGINT AS hist_games_played,{', '.join(features)},({eligible}) AS has_sufficient_history
    FROM current_rows c ASOF LEFT JOIN states h
      ON c.player_name=h.player_name AND c.history_cutoff>h.block_at"""


def verify_chronology(con, source, metadata, report):
    if report.get("metadata_checksum") != hash_file(metadata):
        raise ValueError("Stale chronology report: rerun Notebook 02.")
    grade = report.get("grade")
    if grade not in {"Grade A","Grade B","Grade C"}:
        raise ValueError("Missing/invalid chronology grade.")
    mismatch = con.execute(f"""WITH input AS (SELECT match_id,
      min(TRY_CAST(date AS TIMESTAMPTZ)) AS t,count(DISTINCT TRY_CAST(date AS TIMESTAMPTZ)) AS n,
      count(*) FILTER (WHERE TRY_CAST(date AS TIMESTAMPTZ) IS NULL) AS missing
      FROM read_parquet({literal(source)}) GROUP BY 1)
      SELECT count(*) FROM input i FULL OUTER JOIN read_parquet({literal(metadata)}) m USING(match_id)
      WHERE i.match_id IS NULL OR m.match_id IS NULL OR i.n>1
        OR i.t IS DISTINCT FROM TRY_CAST(m.match_date AS TIMESTAMPTZ)
        OR (i.missing>0 AND TRY_CAST(m.match_date AS TIMESTAMPTZ) IS NOT NULL)""").fetchone()[0]
    if mismatch:
        raise ValueError(f"Chronology/player-match mismatch: {mismatch} matches.")
    if grade!="Grade C" and (report.get("null_date_count")!=0 or report.get("timezone_normalized")!="UTC"):
        raise ValueError("Report does not establish valid UTC dates.")
    if grade=="Grade A" and not report.get("has_exact_order_evidence"):
        raise ValueError("Grade A requires explicit exact-order evidence, not timestamp precision.")
    dates=con.execute(f"""SELECT count(*),count(DISTINCT match_id),
        count(*) FILTER (WHERE TRY_CAST(match_date AS TIMESTAMPTZ) IS NULL),
        count(DISTINCT date_trunc('day',TRY_CAST(match_date AS TIMESTAMPTZ)))
        FROM read_parquet({literal(metadata)})""").fetchone()
    if dates[0]!=dates[1] or (grade!="Grade C" and dates[2]) or (grade=="Grade B" and dates[3]<3):
        raise ValueError("Chronology grade unsupported by actual metadata grain/date coverage.")
    return grade


def inputs(paths):
    return {"source_checksum": paths["processed"] / "player_match_features.parquet",
        "metadata_checksum": paths["interim"] / "match_metadata.parquet",
        "split_checksum": paths["interim"] / "split_assignments.parquet",
        "chronology_checksum": paths["manifests"] / "chronology_report.json"}


def diagnostics(con, cfg, paths):
    source = inputs(paths)["source_checksum"]
    split = inputs(paths)["split_checksum"]
    settings = cfg["rq3"]["historical"]
    grade = verify_chronology(con, source, inputs(paths)["metadata_checksum"], read_json(inputs(paths)["chronology_checksum"]))
    receipt = {"chronology_grade": grade, **{k: hash_file(p) for k,p in inputs(paths).items()},
        "code_hash": code_hash(), "settings_hash": hash_dict(diagnostic_settings(settings)),
        "runtime_scope":cfg["runtime"]["mode"],
        "selection_scope": "development: train+validation only", "outcome_used_for_selection": False, "tables": {}}
    previous_path=paths["manifests"]/"history_diagnostics_receipt.json"
    if previous_path.is_file():
        previous=read_json(previous_path)
        keys=[key for key in receipt if key!="tables"]
        if all(previous.get(key)==receipt[key] for key in keys) and previous.get("diagnostics_hash")==receipt_hash(previous):
            cached={name:paths["tables"]/f"{name}.csv" for name in previous["tables"]}
            if all(path.is_file() and hash_file(path)==previous["tables"][name] for name,path in cached.items()):
                return previous,{**cached,"diagnostics_receipt":previous_path}
    artifacts = {}
    def save(name, frame):
        frame["analysis_scope"] = (cfg["runtime"]["mode"]+": feasibility toàn input"
            if name in {"history_identity_exclusions","history_chronology_collisions","history_resource_audit"}
            else receipt["selection_scope"])
        path = paths["tables"] / f"{name}.csv"
        atomic_write_csv(path, frame)
        artifacts[name]=path
        receipt["tables"][name]=hash_file(path)
    save("history_identity_exclusions", con.execute(f"""SELECT count(*) AS total_rows,
      count(*) FILTER (WHERE player_name IS NULL OR length(trim(player_name))=0) AS excluded_identity_rows,
      count(*) FILTER (WHERE player_name IS NOT NULL AND length(trim(player_name))>0) AS valid_identity_rows
      FROM read_parquet({literal(source)})""").df())
    save("history_chronology_collisions", con.execute(f"""WITH counts AS (SELECT player_name,
      date_trunc('day',TRY_CAST(date AS TIMESTAMPTZ)) AS day,TRY_CAST(date AS TIMESTAMPTZ) AS t,count(*) AS n
      FROM read_parquet({literal(source)}) WHERE player_name IS NOT NULL AND length(trim(player_name))>0 GROUP BY 1,2,3),
      days AS (SELECT player_name,day,sum(n) AS n FROM counts GROUP BY 1,2)
      SELECT 'same_timestamp_player_blocks' AS kind,count(*) FILTER (WHERE n>1) AS colliding_blocks,
        coalesce(sum(n) FILTER (WHERE n>1),0) AS affected_rows,coalesce(sum(n),0) AS total_rows FROM counts
      UNION ALL SELECT 'same_day_player_blocks',count(*) FILTER (WHERE n>1),
        coalesce(sum(n) FILTER (WHERE n>1),0),coalesce(sum(n),0) FROM days""").df())
    tmp=paths["temp_dir"]
    tmp.mkdir(parents=True,exist_ok=True)
    resource=pd.DataFrame([{"source_bytes":source.stat().st_size,"spill_disk_free_bytes":shutil.disk_usage(tmp).free,
        "measured_at_utc":datetime.now(timezone.utc).isoformat(),
        "planning_spill_bytes":source.stat().st_size*4,"duckdb_memory_limit":con.execute("SELECT current_setting('memory_limit')").fetchone()[0],
        "threads":con.execute("SELECT current_setting('threads')").fetchone()[0],"partition_policy":"DuckDB availability-block aggregation/spill; no sampling",
        "limitation":"4x bytes is planning, not guaranteed peak, RAM or Drive quota"}])
    save("history_resource_audit",resource)
    reason="blocked_by_chronology" if grade=="Grade C" else None
    availability=settings["availability"]
    if not reason and (availability.get("status")!="verified" or not availability.get("evidence")):
        reason="blocked_by_availability"
    if reason:
        receipt.update(status="blocked",reason_code=reason)
    else:
        if resource.spill_disk_free_bytes.iloc[0]<resource.planning_spill_bytes.iloc[0]:
            raise MemoryError("Insufficient spill disk; stop, do not sample.")
        bad=con.execute(f"SELECT count(*) FROM read_parquet({literal(split)}) WHERE split IS NULL OR split NOT IN ('train','validation','test')").fetchone()[0]
        dup=con.execute(f"SELECT count(*)-count(DISTINCT match_id) FROM read_parquet({literal(split)})").fetchone()[0]
        unmatched=con.execute(f"""SELECT count(*) FROM (SELECT DISTINCT match_id FROM read_parquet({literal(source)})) a
          FULL OUTER JOIN read_parquet({literal(split)}) s USING(match_id) WHERE a.match_id IS NULL OR s.match_id IS NULL""").fetchone()[0]
        if bad or dup or unmatched:
            raise ValueError("Invalid split identity/coverage; rerun Notebook 02.")
        with tempfile.TemporaryDirectory(dir=tmp,prefix="history_diag_") as directory:
            development=Path(directory)/"development.parquet"
            copy_query_to_parquet(con,f"SELECT a.* FROM read_parquet({literal(source)}) a JOIN read_parquet({literal(split)}) s USING(match_id) WHERE s.split IN ('train','validation')",development)
            query=history_query(con,development,grade,None,availability)
            con.execute(f"CREATE OR REPLACE TEMP TABLE history_diagnostics AS SELECT * FROM ({query})")
        candidates=settings["threshold_candidates"]
        if not candidates or len(set(candidates))!=len(candidates):
            raise ValueError("Nonempty unique diagnostic thresholds required.")
        coverage,stability=[],[]
        for t in candidates:
            if threshold_value(t) is None:
                raise ValueError("Diagnostic threshold cannot be null.")
            coverage.append(con.execute(f"""SELECT {t} AS threshold,count(*) AS total_rows,
              count(*) FILTER (WHERE hist_games_played>={t}) AS eligible_rows,
              count(*) FILTER (WHERE hist_games_played>={t})::DOUBLE/nullif(count(*),0) AS eligible_fraction
              FROM history_diagnostics""").df())
            for key,(_,mean,unit) in FEATURES.items():
                if key in {"survival","placement"}:
                    continue
                stability.append(con.execute(f"""WITH delta AS (SELECT *,abs({mean}-lag({mean}) OVER (
                  PARTITION BY player_name ORDER BY history_cutoff)) AS mean_change FROM
                  (SELECT DISTINCT player_name,history_cutoff,hist_games_played,{mean},hist_{key}_count FROM history_diagnostics))
                  SELECT {t} AS threshold,'{mean}' AS feature,'{unit}' AS unit,count({mean}) AS valid_rows,
                    count(mean_change) AS valid_transitions,avg(hist_{key}_count) AS mean_valid_history_count,
                    avg(mean_change) AS mean_absolute_history_change,stddev_samp({mean}) AS between_row_std
                    FROM delta WHERE hist_games_played>={t}""").df())
        save("history_coverage",pd.concat(coverage,ignore_index=True))
        save("history_stability",pd.concat(stability,ignore_index=True))
        save("history_depth",con.execute("SELECT hist_games_played,count(*) AS rows FROM history_diagnostics GROUP BY 1 ORDER BY 1").df())
        save("history_development_coverage",con.execute(f"""SELECT s.split,h.team_size_mode,h.match_date,
          count(*) AS total_rows,count(*) FILTER (WHERE hist_games_played=0) AS cold_start_rows,
          avg(hist_games_played) AS mean_history_depth FROM history_diagnostics h
          JOIN read_parquet({literal(split)}) s USING(match_id) GROUP BY 1,2,3 ORDER BY 1,2,3""").df())
        receipt.update(status="completed",reason_code=None)
    receipt["diagnostics_hash"]=receipt_hash(receipt)
    receipt_path=paths["manifests"]/"history_diagnostics_receipt.json"
    atomic_write_json(receipt_path,receipt)
    artifacts["diagnostics_receipt"]=receipt_path
    return receipt,artifacts


def leakage_audit(con,path):
    cold=" OR ".join(f"{v[1]} IS NOT NULL" for v in FEATURES.values())
    checks={"cold_start_means_missing":f"hist_games_played=0 AND ({cold})",
        "strict_past_availability":"max_history_available_at>=history_cutoff OR (hist_games_played>0 AND max_history_available_at IS NULL)",
        "finite_history_means":" OR ".join(f"({v[1]} IS NOT NULL AND NOT isfinite({v[1]}))" for v in FEATURES.values())}
    rows=[]
    for name,predicate in checks.items():
        n,violations=con.execute(f"SELECT count(*),count(*) FILTER (WHERE {predicate}) FROM read_parquet({literal(path)})").fetchone()
        rows.append({"check":name,"expected_violations":0,"observed_violations":violations,"total_rows":n,
            "status":"PASSED" if violations==0 else "FAILED",
            "limitation":"Depends on verified source availability; mutation invariants checked on fixture separately"})
    n,unique=con.execute(f"SELECT count(*),count(DISTINCT row_id) FROM read_parquet({literal(path)})").fetchone()
    rows.append({"check":"unique_nonmissing_row_identity","expected_violations":0,
        "observed_violations":n-unique,"total_rows":n,"status":"PASSED" if n==unique else "FAILED",
        "limitation":"Uniqueness is not proof of cross-match identity stability"})
    return pd.DataFrame(rows)


def publish(con,cfg,paths,receipt,checkpoint,registry=None):
    settings=cfg["rq3"]["historical"]
    threshold=threshold_value(cfg["rq3"]["minimum_history_threshold"])
    grade=receipt["chronology_grade"]
    signature=hash_dict({"diagnostics_hash":receipt["diagnostics_hash"],"config":cfg["rq3"],"scope":cfg["runtime"]["mode"]})
    output=paths["processed"]/"historical_player_match_features.parquet"
    status_path=paths["manifests"]/"historical_status.json"
    if checkpoint.is_compatible("historical",signature):
        require_historical_dataset(paths,cfg)
        return read_json(status_path),{name:Path(path) for name,path in checkpoint.restore("historical")["artifacts"].items()}
    checkpoint.invalidate_descendants("historical")
    status={**{k:v for k,v in receipt.items() if k.endswith("checksum") or k=="code_hash"},
        "status":"pending","reason_code":"historical_build_not_committed","decision_gate":"G3",
        "chronology_grade":grade,"min_history_threshold":threshold,"signature":signature,
        "config_hash":hash_dict(cfg["rq3"]),"stale_output_present":output.exists(),
        "output_path":None,"output_checksum":None,"evaluation_protocol":settings["evaluation_protocol"],
        "availability_policy":settings["availability"],"analysis_scope":cfg["runtime"]["mode"],"eligible_historical_records":0}
    atomic_write_json(status_path,status)
    checkpoint.record_blocked("historical",signature,status["reason_code"],status)
    for key,path in inputs(paths).items():
        if receipt[key]!=hash_file(path):
            raise ValueError(f"Stale diagnostics input: {key}")
    if receipt["code_hash"]!=code_hash() or receipt["settings_hash"]!=hash_dict(diagnostic_settings(settings)):
        raise ValueError("Stale diagnostics code/settings; rerun diagnostics.")
    if receipt["diagnostics_hash"]!=receipt_hash(receipt):
        raise ValueError("Invalid diagnostics receipt hash.")
    for name,checksum in receipt["tables"].items():
        if hash_file(paths["tables"]/f"{name}.csv")!=checksum:
            raise ValueError(f"Stale diagnostic table: {name}")
    reason=receipt.get("reason_code")
    if not reason and threshold is None:
        reason="minimum_history_threshold_pending"
    if not reason and (not settings["threshold_decision_reason"] or settings["threshold_diagnostics_hash"]!=receipt["diagnostics_hash"]):
        reason="threshold_decision_receipt_pending_or_stale"
    if not reason and threshold not in settings["threshold_candidates"]:
        raise ValueError("Threshold absent from diagnosed candidates; rerun diagnostics.")
    if not reason and settings["evaluation_protocol"]!="walk_forward_fixed_model":
        reason="historical_evaluation_protocol_pending"
    artifacts={name:paths["tables"]/f"{name}.csv" for name in receipt["tables"]}
    artifacts["diagnostics_receipt"]=paths["manifests"]/"history_diagnostics_receipt.json"
    if reason:
        status.update(status="blocked" if grade=="Grade C" or reason=="blocked_by_availability" else "pending",reason_code=reason)
    else:
        try:
            if shutil.disk_usage(paths["temp_dir"]).free < inputs(paths)["source_checksum"].stat().st_size*4:
                raise MemoryError("Insufficient spill disk at build; stop without sampling.")
            with tempfile.TemporaryDirectory(dir=paths["temp_dir"],prefix="history_build_") as directory:
                local=Path(directory)/"history.parquet"
                query=history_query(con,inputs(paths)["source_checksum"],grade,threshold,settings["availability"])
                rows=copy_query_to_parquet(con,query,local)
                audit=leakage_audit(con,local)
                if audit.observed_violations.sum():
                    raise ValueError("Historical leakage audit failed; old output stays blocked.")
                eligible=con.execute(f"SELECT count(*) FROM read_parquet({literal(local)}) WHERE has_sufficient_history").fetchone()[0]
                publish_file(local,output)
            status.update(status="completed" if eligible else "blocked",reason_code=None if eligible else "no_eligible_history",
                total_player_records=rows,eligible_historical_records=eligible,coverage_ratio=eligible/rows if rows else 0.,
                output_path=str(output),output_checksum=hash_file(output),stale_output_present=False,
                diagnostics_hash=receipt["diagnostics_hash"],threshold_decision_reason=settings["threshold_decision_reason"])
            audit_path=paths["tables"]/"historical_leakage_audit.csv"
            atomic_write_csv(audit_path,audit)
            coverage=con.execute(f"""SELECT s.split,h.team_size_mode,h.match_date,count(*) AS total_rows,
              count(*) FILTER (WHERE hist_games_played=0) AS cold_start_rows,
              count(*) FILTER (WHERE hist_games_played>0 AND NOT has_sufficient_history) AS under_threshold_rows,
              count(*) FILTER (WHERE has_sufficient_history) AS eligible_rows FROM read_parquet({literal(output)}) h
              JOIN read_parquet({literal(inputs(paths)['split_checksum'])}) s USING(match_id) GROUP BY 1,2,3 ORDER BY 1,2,3""").df()
            coverage["analysis_scope"]=cfg["runtime"]["mode"]+": fixed walk-forward coverage; not threshold selection"
            coverage_path=paths["tables"]/"history_model_coverage.csv"
            atomic_write_csv(coverage_path,coverage)
            artifacts.update(historical_features=output,leakage_audit=audit_path,model_coverage=coverage_path)
        except Exception as error:
            status.update(status="resource_limited" if isinstance(error,(MemoryError,duckdb.OutOfMemoryException)) else "failed",
                          reason_code="historical_build_failed",error=str(error))
            atomic_write_json(status_path,status)
            checkpoint.record_failure("historical",signature,str(error),resource_limited=status["status"]=="resource_limited")
            raise
    atomic_write_json(status_path,status)
    artifacts["historical_status"]=status_path
    checkpoint.commit("historical_feasibility",signature,artifacts,metadata={"model_status":status["status"]})
    if status["status"]=="completed":
        checkpoint.commit("historical",signature,artifacts,metadata=status)
        manifest=checkpoint.load_manifest()
        for task in TASKS:
            manifest["stages"][task]={"status":"planned","signature":signature,"artifacts":{},
                "metadata":{"history_ready":True,"historical_signature":signature}}
            if registry:
                registry.update_status(task,"planned",reason_code=None)
        checkpoint.save_manifest(manifest)
    else:
        checkpoint.record_blocked("historical",signature,status["reason_code"],status)
        for task in TASKS:
            checkpoint.record_blocked(task,signature,status["reason_code"],status)
            if registry:
                registry.update_status(task,"blocked",reason_code=status["reason_code"])
    return status,artifacts


def require_historical_dataset(paths,cfg):
    """Fail closed for stale bytes, code, config, grade or missing current status."""
    status=read_json(paths["manifests"]/"historical_status.json")
    if status.get("status")!="completed":
        raise ValueError(f"Historical consumer blocked: {status.get('reason_code','not_completed')}")
    if status.get("analysis_scope")!=cfg["runtime"]["mode"]:
        raise ValueError("Historical scope mismatch; fixture/development is not full-data.")
    for key,path in {**inputs(paths),"output_checksum":paths["processed"]/"historical_player_match_features.parquet"}.items():
        if status.get(key)!=hash_file(path):
            raise ValueError(f"Stale historical artifact: {key}; rerun Notebook 08.")
    if status.get("code_hash")!=code_hash() or status.get("config_hash")!=hash_dict(cfg["rq3"]):
        raise ValueError("Stale historical code/config; rerun Notebook 08.")
    from src.data.checkpoints import CheckpointManager
    checkpoint=CheckpointManager(paths["checkpoints"]/"checkpoint_manifest.json")
    if not checkpoint.is_compatible("historical",status["signature"]):
        raise ValueError("Historical checkpoint/status corrupt or incomplete; rerun Notebook 08.")
    return paths["processed"]/"historical_player_match_features.parquet"


def create_figures(paths,receipt,status,artifacts):
    """Five diagnostic figures from exact persisted summaries, no raw point sampling."""
    import matplotlib.pyplot as plt
    from matplotlib.ticker import MaxNLocator
    catalog=[]
    def save(figure,ident,name,table,caption,how,limitation):
        path=paths["figures"]/f"history_{name}.png"
        figure.tight_layout()
        with tempfile.TemporaryDirectory(prefix="history_figure_") as directory:
            local=Path(directory)/"figure.png"
            figure.savefig(local,dpi=140)
            publish_file(local,path)
        plt.close(figure)
        artifacts[name+"_figure"]=path
        catalog.append({"figure_id":ident,"research_question":"RQ3 historical feasibility",
            "source_table":str(table),"path":str(path),"caption":caption,"how_to_read":how,
            "limitation":limitation,"scope":("feasibility toàn input" if name=="collisions" else
                status["analysis_scope"]+": coverage after G3" if name=="model_coverage" else receipt["selection_scope"]),
            "version":status["signature"],"report_ready":False,"sampling":"none; SQL summary of declared scope"})
    collision=paths["tables"]/"history_chronology_collisions.csv"
    c=pd.read_csv(collision)
    fig,ax=plt.subplots(figsize=(9,4))
    ax.bar(["Khối cùng timestamp","Khối cùng ngày"],c.affected_rows)
    ax.set(ylabel="Số player-match bị ảnh hưởng",title="08-04: Va chạm chronology (feasibility toàn input)")
    ax.yaxis.set_major_locator(MaxNLocator(integer=True))
    save(fig,"08-04","collisions",collision,f"Va chạm; N hợp lệ={int(c.total_rows.iloc[0])}; không dùng thứ tự ID.",
         "Hai thanh có thể chồng quan sát; không cộng chúng thành tổng số dòng lỗi.","Timestamp chính xác không chứng minh availability.")
    if receipt["status"]=="completed":
        depth_path=paths["tables"]/"history_depth.csv"
        d=pd.read_csv(depth_path)
        fig,ax=plt.subplots(figsize=(9,4))
        ax.bar(d.hist_games_played,d.rows,width=.8)
        ax.set(xlabel="Số trận quá khứ đã sẵn sàng",ylabel="Số player-match",title=f"08-01: Độ sâu lịch sử development; N={int(d.rows.sum())}")
        ax.yaxis.set_major_locator(MaxNLocator(integer=True))
        ax.xaxis.set_major_locator(MaxNLocator(integer=True))
        save(fig,"08-01","depth",depth_path,"Mỗi thanh là exact count, không lấy mẫu.",
             "Depth=0 là cold start, không phải mean kills bằng 0.","Chỉ train+validation; test không dùng chọn threshold.")
        cov_path=paths["tables"]/"history_coverage.csv"
        c=pd.read_csv(cov_path)
        fig,ax=plt.subplots(figsize=(9,4))
        ax.plot(c.threshold,c.eligible_fraction,marker="o")
        ax.set(xlabel="Ngưỡng ứng viên (số trận)",ylabel="Tỷ lệ eligible (0-1)",ylim=(0,1.05),title="08-02: Retention theo ngưỡng development")
        save(fig,"08-02","retention",cov_path,f"Tử số eligible_rows / mẫu số total_rows; N={int(c.total_rows.iloc[0])}.",
             "Ngưỡng cao giữ ít dòng hơn; đường này không tự chọn ngưỡng.","Không dùng test MAE hoặc outcomes để chọn.")
        stab_path=paths["tables"]/"history_stability.csv"
        s=pd.read_csv(stab_path)
        fig,axes=plt.subplots(2,3,figsize=(12,7))
        for ax,(feature,frame) in zip(axes.flat,s.groupby("feature",sort=True)):
            ax.plot(frame.threshold,frame.mean_absolute_history_change,marker="o")
            ax.set(title=feature,xlabel="Ngưỡng (trận)",ylabel=f"Thay đổi mean ({frame.unit.iloc[0]})")
            ax.xaxis.set_major_locator(MaxNLocator(integer=True))
            missing=frame.loc[frame.mean_absolute_history_change.isna(),"threshold"].tolist()
            if missing:
                ax.text(.02,.95,f"Thiếu transition ở ngưỡng {missing}",transform=ax.transAxes,va="top",fontsize=8)
        fig.suptitle("08-03: Ổn định lịch sử development, không dùng survival/placement")
        save(fig,"08-03","stability",stab_path,"Độ ổn định descriptive = mean |mean_t - mean_previous_cutoff|; valid_transitions là mẫu số.",
             "Đọc riêng từng feature và đơn vị; thiếu transition thì NaN, không phải 0.","Không phải độ chính xác dự đoán; between_row_std không là within-player stability.")
    if "model_coverage" in artifacts:
        coverage_path=artifacts["model_coverage"]
        c=pd.read_csv(coverage_path)
        fig,axes=plt.subplots(1,3,figsize=(15,5))
        for ax,group in zip(axes,["split","team_size_mode","match_date"]):
            summary=c.groupby(group)[["cold_start_rows","under_threshold_rows","eligible_rows"]].sum()
            if group=="split":
                summary=summary.reindex([s for s in ["train","validation","test"] if s in summary.index])
            summary=summary.rename(columns={"cold_start_rows":"Chưa có lịch sử",
                "under_threshold_rows":"Chưa đủ ngưỡng","eligible_rows":"Đủ ngưỡng"})
            summary.plot.bar(stacked=True,ax=ax)
            ax.set(xlabel=group,ylabel="Số player-match",title=f"Coverage theo {group}")
            ax.set_ylim(0,max(1,summary.sum(axis=1).max())*1.4)
            ax.yaxis.set_major_locator(MaxNLocator(integer=True))
            ax.tick_params(axis="x",labelrotation=45)
        fig.suptitle(f"08-05: Coverage walk-forward, N={int(c.total_rows.sum())}; không chọn ngưỡng từ test")
        save(fig,"08-05","model_coverage",coverage_path,"Cold start + under threshold + eligible = total_rows theo split/mode/ngày.",
             "Test chỉ là coverage sau quyết định khóa; không quay lại tune ngưỡng.","Không phải metric mô hình; S2/P3 vẫn chưa được huấn luyện ở NB08.")
    catalog_path=paths["tables"]/"history_figure_catalog.csv"
    atomic_write_csv(catalog_path,pd.DataFrame(catalog))
    artifacts["figure_catalog"]=catalog_path
    return artifacts


def illustrative_history(con,temp_dir):
    """Independent labelled teaching fixture; never merged with research input."""
    frame=pd.DataFrame({"match_id":["demo1","demo2","demo3","demo4"],"player_name":["demo"]*4,
        "team_id":["demo_team"]*4,"date":["2020-01-01T10:00:00Z","2020-01-01T10:00:00Z",
        "2020-01-01T12:00:00Z","2020-01-02T10:00:00Z"],"player_kills":[2.,4.,8.,10.]})
    frame["prediction_time"]=frame.date
    frame["available_time"]=frame.date
    for raw,_,_ in FEATURES.values():
        if raw not in frame:
            frame[raw]=1.
    availability={"status":"verified","evidence":"Synthetic zero-duration teaching fixture, not source evidence",
        "policy":"explicit_columns","timestamp_semantics":"prediction_and_statistic_availability",
        "prediction_column":"prediction_time","available_column":"available_time"}
    with tempfile.TemporaryDirectory(dir=temp_dir,prefix="history_example_") as directory:
        path=Path(directory)/"example.parquet"
        frame.to_parquet(path,index=False)
        rows=[]
        for grade in ["Grade A","Grade B"]:
            query=history_query(con,path,grade,1,availability)
            rows.append(con.execute(f"SELECT chronology_grade,match_id,date,history_cutoff,max_history_available_at,hist_games_played,hist_kills_count,hist_kills_mean FROM ({query}) ORDER BY match_id").df())
    return pd.concat(rows,ignore_index=True)
