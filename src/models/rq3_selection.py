"""Explicit G4 receipt. Reading test targets is allowed only after this lock validates."""
import hashlib
from pathlib import Path
import joblib
import numpy as np
import pandas as pd
from src.data.io import atomic_write_json, atomic_write_parquet, atomic_write_csv, read_json, get_duckdb_connection, publish_file
from src.data.cohort import ensure_row_id
from src.data.checkpoints import CheckpointManager
from src.utils.hashing import hash_dict, hash_file
from src.evaluation.metrics import compute_hierarchical_metrics


def selection_inputs(paths):
    files={"features":paths["processed"]/"player_match_features.parquet",
           "split":paths["interim"]/"split_assignments.parquet"}
    return {key:{"path":str(file),"sha256":hash_file(file)} for key,file in files.items()}


def lock_rq3_selection(paths, cfg):
    """No decision means pending, never an implicit approval or lowest-MAE winner."""
    decision_path=paths["manifests"]/"rq3_selection_decision.json"
    if not decision_path.is_file():
        return None
    decision=read_json(decision_path)
    if decision.get("approved") is not True or not decision.get("approved_by"):
        raise ValueError("G4 requires explicit approval and reviewer identity")
    if decision.get("fit_protocol")!="fit_train_only":
        raise ValueError("Refit train+validation requires a separate authorized research protocol")
    if cfg['runtime']['mode'] == 'full':
        design = decision.get('descriptive_design', {})
        if (design.get('rq1') != 'full_descriptive_locked' or design.get('no_reselection') is not True
                or design.get('rq2_config_hash') != hash_dict(cfg['rq2'])):
            raise ValueError('Full run: register descriptive RQ1/RQ2 design before G4/test')
    reasons=decision.get("selection_reasons",{})
    for key in ["performance","generalization","interpretability","stability","compute"]:
        if not isinstance(reasons.get(key),str) or not reasons[key].strip():
            raise ValueError(f"G4 selection reason missing: {key}")
    bins=decision.get("error_bins")
    if not isinstance(bins,dict) or not {"survival","placement"}<=set(bins) or set(bins)-{"survival","placement","history_depth"}:
        raise ValueError("G4 must pre-register survival and placement error bins")
    for task,edges in bins.items():
        if not isinstance(edges,list) or len(edges)<2 or not np.isfinite(edges).all() or not all(a<b for a,b in zip(edges,edges[1:])):
            raise ValueError(f"Invalid/overlapping error bins: {task}")
    if bins["placement"][0]!=0 or bins["placement"][-1]!=1:
        raise ValueError("Placement error bins must cover [0,1]")
    registry_path=paths["manifests"]/"rq3_development_registry.json"
    diagnostics_path=paths["manifests"]/"rq3_feature_diagnostics_receipt.json"
    diagnostics=read_json(diagnostics_path)
    if decision.get("diagnostics_hash")!=diagnostics.get("diagnostics_hash") or diagnostics.get("importance_failures"):
        raise ValueError("G4 requires current successful feature diagnostics and explicit review")
    for item in diagnostics["tables"].values():
        if hash_file(item["path"])!=item["sha256"]:
            raise ValueError("Feature diagnostics changed after review")
    table_path=paths["tables"]/"rq3_development_validation.csv"
    if decision.get("registry_hash")!=hash_file(registry_path) or decision.get("validation_hash")!=hash_file(table_path):
        raise ValueError("Stale validation/registry decision; review current candidates")
    records=read_json(registry_path)["experiments"]
    provenance=read_json(paths["manifests"]/"rq3_development_inputs.json")
    if provenance!=selection_inputs(paths):
        raise ValueError("Development data/split changed after fitting; rerun candidates before G4")
    selected=decision.get("selected_experiments")
    if not isinstance(selected,list) or not selected or len(set(selected))!=len(selected):
        raise ValueError("G4 requires an explicit unique experiment list")
    required=set()
    for task,model in [("s1","s1_retrospective_survival"),("p1","p1_ols_direct_survival"),("p2","p2_ols_no_direct_survival")]:
        required.update([model,f"{task}_baseline_mean",f"{task}_baseline_median"])
    if records.get("t0_timing_ols",{}).get("status")=="completed":
        required.update(["t0_timing_ols","t1_timing_ols"])
    for task,model in [("s2","s2_historical_survival"),("p3","p3_historical_placement")]:
        if records.get(model,{}).get("status")=="completed":
            if "history_depth" not in bins:
                raise ValueError("G4 must pre-register history_depth bins for historical models")
            required.update([model,f"{task}_baseline_mean",f"{task}_baseline_median"])
    required.update(key for key,record in records.items() if "_validation_ablation_" in key and record.get("status")=="completed")
    if not required<=set(selected):
        raise ValueError("G4 requires core models and paired train-only baselines/timing branches")
    comparisons=decision.get("comparisons")
    if not isinstance(comparisons,list) or not comparisons:
        raise ValueError("G4 must pre-register comparison recipes, not just select lowest metric")
    for pair in comparisons:
        if not isinstance(pair,dict) or not {pair.get("reference"),pair.get("candidate")}<=set(selected):
            raise ValueError("Comparison recipe refers to unselected experiments")
    mandatory={("p1_ols_direct_survival","p2_ols_no_direct_survival")}
    if "t0_timing_ols" in selected:
        mandatory.add(("t0_timing_ols","t1_timing_ols"))
    main={"s1":"s1_retrospective_survival","p1":"p1_ols_direct_survival","p2":"p2_ols_no_direct_survival",
          "s2":"s2_historical_survival","p3":"p3_historical_placement"}
    for task,model in main.items():
        if model in selected:
            mandatory.update((f"{task}_baseline_{kind}",model) for kind in ["mean","median"])
    anchor=main[cfg["rq3"]["experiments"]["ablation_full_task"]]
    mandatory.update((anchor,key) for key in selected if "_validation_ablation_" in key)
    if not mandatory<={(pair["reference"],pair["candidate"]) for pair in comparisons}:
        raise ValueError("G4 must register core/baseline/timing/ablation comparisons before test")
    manager=CheckpointManager(paths["checkpoints"]/"checkpoint_manifest.json")
    models={}
    for exp_id in selected:
        exp=records.get(exp_id)
        if exp is None or exp["status"]!="completed" or exp["split_scope"]!="development_train_validation":
            raise ValueError(f"Cannot select unavailable candidate: {exp_id}")
        signature=exp["signatures"]["recipe"]
        if not manager.is_compatible("rq3_development/"+exp_id,signature):
            raise ValueError(f"Candidate checkpoint corrupt/stale: {exp_id}")
        meta_path=Path(exp["artifact_paths"]["metadata"])
        meta=read_json(meta_path)
        if decision.get("features_by_experiment",{}).get(exp_id)!=meta["features"]:
            raise ValueError(f"Final feature order must match an actually fitted candidate: {exp_id}")
        models[exp_id]={"task":exp["task"],"target":meta["target"],"features":meta["features"],
            "model_params":meta["model_params"],"compute":meta["compute"],"run_id":meta["run_id"],
            "train_samples":meta["train_samples"],"val_samples":meta["val_samples"],
            "cohort_hash":meta["cohort_hash"],
            "model_path":exp["artifact_paths"]["model"],"model_hash":hash_file(exp["artifact_paths"]["model"]),
            "metadata_hash":hash_file(meta_path),"candidate_signature":signature}
    for pair in comparisons:
        a,b=models[pair["reference"]],models[pair["candidate"]]
        if a["cohort_hash"]!=b["cohort_hash"] or a["target"]!=b["target"]:
            raise ValueError("Paired comparisons require identical development rows/targets/splits")
    # Count split metadata only; no test target/behavior before the receipt is locked.
    splits=pd.read_parquet(paths["interim"]/"split_assignments.parquet",columns=["match_id","split"])
    if splits.match_id.duplicated().any() or not splits.split.isin(["train","validation","test"]).all() or set(splits.split)!={"train","validation","test"}:
        raise ValueError("G4 requires nonempty, unique match split assignments")
    recipe={"gate":"G4_SELECTION_LOCK","status":"LOCKED","decision":decision,
        "config_hash":hash_dict(cfg),"inputs":provenance,"models":models,
        "reviewed_artifacts":{str(file):hash_file(file) for file in [registry_path,table_path,diagnostics_path]},
        "split_match_counts":splits.groupby("split").size().to_dict(),
        "pipeline_policy":"fitted objects serialized with each train-only model",
        "prior_test_exposure":decision.get("prior_test_exposure","unknown; previous code could expose test"),
        "code_hash":hash_dict({str(p):hash_file(p) for p in sorted(Path(__file__).parents[1].rglob("*.py"))})}
    recipe["config_files"]={str(p):hash_file(p) for p in sorted((Path(__file__).parents[2]/"configs").glob("*.yaml"))}
    if any(model["task"] in {"s2","p3"} for model in models.values()):
        from src.features.history_workflow import require_historical_dataset
        history=require_historical_dataset(paths,cfg)
        recipe["inputs"]["history"]={"path":str(history),"sha256":hash_file(history)}
        recipe["history_protocol"]=cfg["rq3"]["historical"]["evaluation_protocol"]
    recipe["recipe_hash"]=hash_dict(recipe)
    output=paths["manifests"]/"rq3_selection_lock.json"
    atomic_write_json(output,recipe)
    manager.commit("rq3_selection",recipe["recipe_hash"],{"selection_lock":output},metadata={"test_not_read_yet":True})
    return recipe


def validate_selection_lock(paths,cfg,recipe):
    """Shared fail-closed producer/consumer validation before any test data read."""
    if recipe is None or recipe.get("status")!="LOCKED":
        raise ValueError("Final test is closed until an explicit G4 selection lock")
    if recipe.get("recipe_hash")!=hash_dict({key:value for key,value in recipe.items() if key!="recipe_hash"}):
        raise ValueError("Corrupt G4 recipe")
    if recipe["config_hash"]!=hash_dict(cfg) or recipe["code_hash"]!=hash_dict({str(p):hash_file(p) for p in sorted(Path(__file__).parents[1].rglob("*.py"))}):
        raise ValueError("G4 code/config stale; no final test read")
    if any(hash_file(file)!=checksum for file,checksum in recipe["config_files"].items()):
        raise ValueError("G4 configuration files changed; no final test read")
    if any(hash_file(file)!=checksum for file,checksum in recipe["reviewed_artifacts"].items()):
        raise ValueError("G4 reviewed evidence changed; no final test read")
    for item in recipe["inputs"].values():
        if hash_file(item["path"])!=item["sha256"]:
            raise ValueError("G4 dataset/split changed; no final test read")
    for model in recipe["models"].values():
        if hash_file(model["model_path"])!=model["model_hash"]:
            raise ValueError("G4 trained model changed; no final test read")
    manager=CheckpointManager(paths["checkpoints"]/"checkpoint_manifest.json")
    if not manager.is_compatible("rq3_selection",recipe["recipe_hash"]):
        raise ValueError("G4 selection checkpoint stale/corrupt")


def evaluate_locked_test(paths,cfg,recipe,batch_size=50000):
    """Load one test cohort/model at a time, predict only; never refit on test or validation."""
    validate_selection_lock(paths,cfg,recipe)
    if batch_size<1:
        raise ValueError("batch_size must be positive")
    from src.models.rq3_resources import resource_snapshot
    con=get_duckdb_connection()
    rows,artifacts=[],{}
    try:
        for exp_id,entry in recipe["models"].items():
            task=entry["task"]
            historical=task in {"s2","p3"}
            source=recipe["inputs"]["history" if historical else "features"]["path"].replace("'","''").replace("\\","/")
            split=recipe["inputs"]["split"]["path"].replace("'","''").replace("\\","/")
            columns=list(dict.fromkeys(["row_id","match_id","player_name","team_id","team_size_mode",entry["target"]]+entry["features"]))
            schema=[r[0] for r in con.execute(f"DESCRIBE SELECT * FROM read_parquet('{source}')").fetchall()]
            if "row_id" not in schema:
                columns.remove("row_id")
            if historical:
                columns.append("hist_games_played")
                condition="f.has_sufficient_history"
            else:
                condition="isfinite(f.player_survive_time) AND f.player_survive_time>0"
            if task not in {"s1","s2"}:
                condition+=f' AND isfinite(f."{entry["target"]}") AND f."{entry["target"]}" BETWEEN 0 AND 1'
            else:
                condition+=f' AND isfinite(f."{entry["target"]}") AND f."{entry["target"]}">0'
            projection=", ".join('f."'+name.replace('"','""')+'"' for name in dict.fromkeys(columns))
            query=f"SELECT {projection},s.split FROM read_parquet('{source}') f JOIN read_parquet('{split}') s USING(match_id) WHERE s.split='test' AND ({condition})"
            n=con.execute(f"SELECT count(*) FROM ({query})").fetchone()[0]
            if not n:
                raise ValueError(f"No eligible final test rows: {exp_id}")
            # Bound collect before allocation; model-specific measured gate follows.
            from src.utils.runtime import collect_runtime_info
            free=collect_runtime_info().get("available_ram_gb")
            if not isinstance(free,(float,int)) or n*max(1,len(columns))*256>min(free,cfg["models"]["resource_limits"]["max_memory_gb"])*1024**3:
                raise MemoryError("Final-test collect budget exceeded; no sample/substitution")
            frame=ensure_row_id(con.execute(query+" ORDER BY f.match_id,f.player_name").df())
            resource=resource_snapshot(frame,entry["features"],entry["compute"]["device"],cfg["models"]["resource_limits"]["max_memory_gb"])
            if resource["status"]!="ready":
                raise MemoryError(resource["reason_code"])
            model=joblib.load(entry["model_path"])
            values=np.concatenate([model.predict(frame.iloc[start:start+batch_size][entry["features"]].to_numpy())
                for start in range(0,len(frame),batch_size)])
            pred=frame[[name for name in ["row_id","match_id","player_name","team_id","team_size_mode","split","hist_games_played"] if name in frame]].copy()
            pred["actual"]=frame[entry["target"]].to_numpy(dtype=float)
            pred["predicted"]=values
            pred["target_actual"],pred["target_predicted"]=pred.actual,pred.predicted
            pred["compute_device"]=entry["compute"]["device"]
            pred["residual"]=pred.actual-pred.predicted
            pred["task"],pred["target"],pred["experiment_id"],pred["run_id"]=task,entry["target"],exp_id,entry["run_id"]
            pred["recipe_hash"]=recipe["recipe_hash"]
            metrics=compute_hierarchical_metrics(pred,task=task,target_name=entry["target"])
            output=paths["experiments"]/f"predictions_final_{exp_id}.parquet"
            atomic_write_parquet(output,pred)
            artifacts[exp_id]=output
            rows.append({"experiment_id":exp_id,"task":task,"scope":"final_test","n":len(frame),"n_matches":frame.match_id.nunique(),
                "target":entry["target"],"unit":"source time unit (pending verification)" if task in {"s1","s2"} else "score [0,1]",
                "mae":metrics["micro"]["mae"],"rmse":metrics["micro"]["rmse"],"r2":metrics["micro"]["r2"],
                "r2_reason":metrics["micro"].get("r2_reason"),"match_mae":metrics["match_aware"]["mae"],
                "team_mae":metrics["team_aware"]["mae"],"recipe_hash":recipe["recipe_hash"]})
    except Exception as error:
        manager=CheckpointManager(paths["checkpoints"]/"checkpoint_manifest.json")
        manager.record_failure("rq3_prediction",recipe["recipe_hash"],str(error),resource_limited=isinstance(error,MemoryError),
            metadata={"final_test_exposure":"possible; evaluation started after G4","completed_experiments":list(artifacts)})
        raise
    finally:
        con.close()
    table=pd.DataFrame(rows)
    output=paths["tables"]/"rq3_final_test_comparison.csv"
    atomic_write_csv(output,table)
    artifacts["comparison"]=output
    # Publish consumer aliases only after every selected final evaluation succeeds.
    for task,exp_id in [("p1","p1_ols_direct_survival"),("p2","p2_ols_no_direct_survival")]:
        alias=paths["experiments"]/f"predictions_{task}_linear.parquet"
        publish_file(artifacts[exp_id],alias)
        artifacts["handoff_"+task]=alias
    return table,artifacts
