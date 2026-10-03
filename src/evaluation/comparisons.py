"""NB10: consume verified G4 artifacts, never fit/select a model from final test."""
from pathlib import Path
import joblib
import numpy as np
import pandas as pd
import pyarrow.parquet as pq
from src.data.io import read_json, atomic_write_json, atomic_write_csv
from src.data.checkpoints import CheckpointManager
from src.evaluation.bootstrap import pair_predictions, run_paired_match_bootstrap
from src.evaluation.metrics import compute_hierarchical_metrics
from src.evaluation.error_analysis import analyze_prediction_errors
from src.evaluation.importance import extract_feature_importance
from src.models.rq3_selection import validate_selection_lock
from src.features.registry import FeatureRegistry
from src.utils.hashing import hash_dict, hash_file


def comparison_context(paths, cfg):
    manager=CheckpointManager(paths["checkpoints"]/"checkpoint_manifest.json")
    lock=paths["manifests"]/"rq3_selection_lock.json"
    if not lock.is_file():
        manager.record_blocked("ablation_error","pending_G4","pending_G4; review NB09 before NB10")
        raise ValueError("NB10 closed: explicit G4 selection lock required")
    recipe=read_json(lock)
    validate_selection_lock(paths,cfg,recipe)
    if not manager.is_compatible("rq3_prediction",recipe["recipe_hash"]):
        manager.record_blocked("ablation_error",recipe["recipe_hash"],"stale_or_incomplete_NB09_predictions")
        raise ValueError("NB09 prediction checkpoint missing/stale/corrupt; do not read test")
    committed=manager.load_manifest()["stages"]["rq3_prediction"]["artifacts"]
    committed={key:str((manager.manifest_path.parent/Path(value)).resolve()) for key,value in committed.items()}
    files={}
    for key in recipe["models"]:
        file=paths["experiments"]/f"predictions_final_{key}.parquet"
        if str(file.resolve()) not in committed.values():
            raise ValueError(f"Prediction not committed by NB09: {key}")
        files[key]=file
    signature=hash_dict({"recipe":recipe["recipe_hash"],"config":cfg,
        "predictions":{key:hash_file(file) for key,file in files.items()},
        "code":{str(file):hash_file(file) for file in sorted(Path(__file__).parent.glob("*.py"))}})
    # Verify closure and common development recipes before reading final predictions.
    registry=FeatureRegistry()
    anchor_id={"p2":"p2_ols_no_direct_survival","p1":"p1_ols_direct_survival","s1":"s1_retrospective_survival"}[cfg["rq3"]["experiments"]["ablation_full_task"]]
    anchor=recipe["models"][anchor_id]
    for key,entry in recipe["models"].items():
        if "_validation_ablation_" in key:
            group=key.rsplit("_",1)[1]
            remaining=list(anchor["features"])
            for name in ["combat_timing_absolute","combat_timing_phase"] if group=="timing" else [group]:
                remaining=registry.remove_group_and_descendants(remaining,name)
            if remaining!=entry["features"] or not same_preprocessing_policy(entry,anchor,cfg) or entry["cohort_hash"]!=anchor["cohort_hash"] or entry["compute"]!=anchor["compute"]:
                raise ValueError(f"Ablation recipe/closure mismatch: {key}")
        if key in {"t0_timing_ols","t1_timing_ols"}:
            p2=recipe["models"]["p2_ols_no_direct_survival"]
            if not same_preprocessing_policy(entry,p2,cfg) or entry["cohort_hash"]!=p2["cohort_hash"]:
                raise ValueError("Timing recipe/cohort mismatch")
            if key.startswith("t1") and entry["features"]!=p2["features"]:
                raise ValueError("T1 must anchor P2")
    return {"recipe":recipe,"files":files,"signature":signature,"manager":manager}


def same_preprocessing_policy(entry,anchor,cfg):
    # log indices differ when columns are removed; compare policy, not positional indices.
    for item in (entry,anchor):
        indices=tuple(i for i,name in enumerate(item["features"]) if name in cfg["features"]["transforms"]["log_transform_features"])
        if tuple(item["model_params"].get("log_indices",()))!=indices:
            return False
    return {k:v for k,v in entry["model_params"].items() if k!="log_indices"}=={k:v for k,v in anchor["model_params"].items() if k!="log_indices"}


def load_prediction(context, key, cfg):
    file=context["files"][key]
    from src.utils.runtime import collect_runtime_info
    free=collect_runtime_info().get("available_ram_gb")
    # Parquet uncompressed footprint is an estimate, not peak RAM proof.
    meta=pq.ParquetFile(file).metadata
    estimate=sum(meta.row_group(i).total_byte_size for i in range(meta.num_row_groups))*12+meta.num_rows*1024
    if not isinstance(free,(float,int)) or estimate>min(free,cfg["models"]["resource_limits"]["max_memory_gb"])*1024**3:
        raise MemoryError("Saved-prediction collect budget exceeded; no sample/fallback")
    frame=pd.read_parquet(file)
    entry=context["recipe"]["models"][key]
    for column,value in {"split":"test","experiment_id":key,"run_id":entry["run_id"],"target":entry["target"],"task":entry["task"],"recipe_hash":context["recipe"]["recipe_hash"]}.items():
        if column not in frame or frame.empty or not frame[column].eq(value).all():
            raise ValueError(f"Prediction metadata mismatch: {key}/{column}")
    pair_predictions(frame,frame)
    return frame


def run_locked_comparisons(paths,cfg,context=None):
    current=comparison_context(paths,cfg)
    if context is not None and context["signature"]!=current["signature"]:
        raise ValueError("Comparison inputs changed after context review")
    context=current
    manager,signature=context["manager"],context["signature"]
    if manager.is_compatible("ablation_error",signature):
        return {"status":"completed","reused":True,"artifacts":{key:(manager.manifest_path.parent/Path(value)).resolve() for key,value in manager.load_manifest()["stages"]["ablation_error"]["artifacts"].items()},"context":context}
    manager.invalidate_descendants("ablation_error")
    manager.mark_running("ablation_error",signature)
    artifacts={}
    try:
        recipe=context["recipe"]
        comparisons=[]
        settings=cfg["rq3"]["evaluation"]["bootstrap"]
        if settings.get("level")!="match":
            raise ValueError("Only registered match-level paired bootstrap supported")
        budget=cfg["models"]["resource_limits"]["max_memory_gb"]
        for index,pair in enumerate(recipe["decision"]["comparisons"]):
            reference_id,candidate_id=pair["reference"],pair["candidate"]
            stage=f"ablation_error/comparison_{index:03d}"
            output=paths["tables"]/f"rq3_comparison_{index:03d}.csv"
            receipt=paths["manifests"]/f"rq3_bootstrap_{index:03d}.json"
            pair_signature=hash_dict({"stage":signature,"pair":pair})
            if manager.is_compatible(stage,pair_signature):
                comparisons.append(pd.read_csv(output))
                artifacts[f"comparison_{index:03d}"],artifacts[f"bootstrap_{index:03d}"]=output,receipt
                continue
            candidate,reference=pair_predictions(load_prediction(context,candidate_id,cfg),load_prediction(context,reference_id,cfg))
            task=recipe["models"][candidate_id]["task"]
            target=recipe["models"][candidate_id]["target"]
            mc=compute_hierarchical_metrics(candidate,task,target)
            mr=compute_hierarchical_metrics(reference,task,target)
            boot=run_paired_match_bootstrap(candidate,reference,n_replicates=settings["replicates"],random_state=settings["random_state"],max_memory_gb=budget) if settings["enabled"] else {"status":"blocked","reason":"disabled_by_config"}
            saved_boot=dict(boot)
            for name in ["delta_mae","delta_rmse","delta_r2"]:
                if name in saved_boot:
                    saved_boot[name]={key:None if isinstance(value,(float,np.floating)) and not np.isfinite(value) else value
                                      for key,value in saved_boot[name].items()}
            atomic_write_json(receipt,saved_boot)
            if boot["status"]=="resource_limited":
                manager.record_failure(stage,pair_signature,boot["reason"],resource_limited=True)
                raise MemoryError(boot["reason"])
            rows=[]
            for aggregation in ["micro","match_aware","team_aware"]:
                if aggregation=="team_aware" and not mc[aggregation]["applicable"]:
                    continue
                for metric in ["mae","rmse","r2"]:
                    a,b=mc[aggregation].get(metric,np.nan),mr[aggregation].get(metric,np.nan)
                    ci=boot.get("delta_"+metric,{}) if aggregation=="micro" else {}
                    rows.append({"reference":reference_id,"candidate":candidate_id,"aggregation":aggregation,"metric":metric,
                        "reference_value":b,"candidate_value":a,"delta":a-b,"ci_lower":ci.get("ci_lower"),"ci_upper":ci.get("ci_upper"),
                        "valid_replicates":ci.get("valid_replicates"),"ci_status":boot["status"] if aggregation=="micro" else "not_requested",
                        "ci_reason":ci.get("reason") if aggregation=="micro" else "CI not registered for this aggregation",
                        "r2_reason":mc[aggregation].get("r2_reason"),"n_rows":len(candidate),"n_matches":candidate.match_id.nunique(),
                        "unit":"score [0,1]" if "placement" in target else "source time unit (pending verification)",
                        "scope":"locked_test","recipe_hash":recipe["recipe_hash"],"candidate_run_id":recipe["models"][candidate_id]["run_id"],
                        "reference_run_id":recipe["models"][reference_id]["run_id"],"coverage":1.,"pairing":"exact row/identity/target/split"})
            frame=pd.DataFrame(rows)
            atomic_write_csv(output,frame)
            manager.commit(stage,pair_signature,{"table":output,"bootstrap":receipt})
            comparisons.append(frame)
            artifacts[f"comparison_{index:03d}"],artifacts[f"bootstrap_{index:03d}"]=output,receipt
        combined=pd.concat(comparisons,ignore_index=True)
        artifacts["comparisons"]=paths["tables"]/"rq3_paired_comparisons.csv"
        atomic_write_csv(artifacts["comparisons"],combined)
        artifacts["ablation"]=paths["tables"]/"ablation_results.csv"
        atomic_write_csv(artifacts["ablation"],combined.loc[combined.candidate.str.contains("_validation_ablation_")])
        errors,metrics,features,importance,residuals=[],[],[],[],[]
        # One file/model at a time; do not keep every full prediction in RAM.
        for key,entry in recipe["models"].items():
            frame=load_prediction(context,key,cfg)
            measured=compute_hierarchical_metrics(frame,entry["task"],entry["target"])
            for aggregation in ["micro","match_aware","team_aware"]:
                metrics.append({"experiment_id":key,"aggregation":aggregation,**measured[aggregation],"n_rows":len(frame),"n_matches":frame.match_id.nunique(),"scope":"locked_test"})
            output=paths["tables"]/f"error_slices_{key}.csv"
            slices=analyze_prediction_errors(frame,output,target_name=entry["target"],error_bins=recipe["decision"]["error_bins"])
            slices["experiment_id"],slices["recipe_hash"]=key,recipe["recipe_hash"]
            errors.append(slices)
            artifacts["errors_"+key]=output
            base=recipe["models"].get("p2_ols_no_direct_survival",entry)["features"]
            features.append({"experiment_id":key,"task":entry["task"],"feature_count":len(entry["features"]),"kept_features":", ".join(entry["features"]),
                "removed_vs_p2":", ".join(name for name in base if name not in entry["features"]),"train_n":entry["train_samples"],"validation_n":entry["val_samples"],
                "test_n":len(frame),"test_matches":frame.match_id.nunique(),"cohort_hash":entry["cohort_hash"],"run_id":entry["run_id"],"model_hash":entry["model_hash"],
                "recipe_hash":recipe["recipe_hash"],"model_params":str(entry["model_params"]),"scope":"train_fit_locked_test_evaluation"})
            imp=extract_feature_importance(joblib.load(entry["model_path"]),entry["features"])
            if not imp.empty:
                imp["experiment_id"]=key
                importance.append(imp)
            else:
                importance.append(pd.DataFrame([{"experiment_id":key,"importance_type":"not_available","scope":"train_fit",
                    "status":"not_applicable","reason":"constant baseline or estimator without native importance; see validation permutation"}]))
            residual=frame.target_actual-frame.target_predicted
            if key in {"s1_retrospective_survival","p2_ols_no_direct_survival","s2_historical_survival","p3_historical_placement"}:
                # Exact histogram over the entire eligible file, no row sampling.
                counts,edges=np.histogram(residual,bins=20)
                for count,left,right in zip(counts,edges[:-1],edges[1:]):
                    residuals.append({"experiment_id":key,"left":left,"right":right,"n":int(count),"total_n":len(frame),"scope":"locked_test","source":str(context["files"][key])})
        validation_receipt=read_json(paths["manifests"]/"rq3_feature_diagnostics_receipt.json")
        for key in ["importance","correlations"]:
            item=validation_receipt["tables"][key]
            if hash_file(item["path"])!=item["sha256"]:
                raise ValueError("Stale development importance evidence")
            artifacts["validation_"+key]=Path(item["path"])
        for key,frame in [("metrics",pd.DataFrame(metrics)),("features",pd.DataFrame(features)),("errors",pd.concat(errors,ignore_index=True)),
                          ("importance",pd.concat(importance,ignore_index=True) if importance else pd.DataFrame(columns=["status","reason"])),("residuals",pd.DataFrame(residuals))]:
            artifacts[key]=paths["tables"]/f"rq3_{key}_evaluation.csv"
            atomic_write_csv(artifacts[key],frame)
        artifacts["error_analysis"]=paths["tables"]/"error_analysis.csv"
        atomic_write_csv(artifacts["error_analysis"],pd.concat(errors,ignore_index=True))
        artifacts.update(create_comparison_figures(paths,artifacts,recipe))
        receipt=paths["manifests"]/"rq3_comparison_receipt.json"
        atomic_write_json(receipt,{"signature":signature,"recipe_hash":recipe["recipe_hash"],"scope":"locked_test",
            "artifacts":{key:{"path":str(file),"sha256":hash_file(file)} for key,file in artifacts.items()},
            "final_test_permutation":"not_requested; validation evidence reused; no feature reselection",
            "prior_test_exposure":recipe["prior_test_exposure"],"report_ready":False,
            "limitations":["CPU fixture is not full-data/GPU/Drive proof","Match bootstrap does not remove cross-match repeated-player dependence","RAM estimates are not peak guarantees"]})
        artifacts["receipt"]=receipt
        manager.commit("ablation_error",signature,artifacts,metadata={"scope":"locked_test","gate":"G4","report_ready":False})
        return {"status":"completed","reused":False,"artifacts":artifacts,"context":context}
    except Exception as error:
        manager.record_failure("ablation_error",signature,str(error),resource_limited=isinstance(error,MemoryError))
        raise


def create_comparison_figures(paths,artifacts,recipe):
    import matplotlib.pyplot as plt
    comparisons=pd.read_csv(artifacts["comparisons"])
    errors=pd.read_csv(artifacts["errors"])
    residuals=pd.read_csv(artifacts["residuals"])
    importance=pd.read_csv(artifacts["validation_importance"])
    produced,catalog={},{}
    def save(fig,key,source,caption):
        fig.suptitle(recipe["decision"].get("data_scope","Locked test, chưa G5"),fontsize=12)
        fig.tight_layout()
        output=paths["figures"]/f"rq3_evaluation_{key}.png"
        fig.savefig(output,dpi=150,bbox_inches="tight")
        plt.close(fig)
        produced["figure_"+key]=output
        catalog[key]={"path":str(output),"source":str(artifacts[source]),"source_sha256":hash_file(artifacts[source]),"figure_sha256":hash_file(output),
            "caption":caption,"scope":"validation" if key=="importance" else "locked_test","recipe_hash":recipe["recipe_hash"],"sampled":False,"report_ready":False}
        catalog[key]["counts_source"]={"path":str(artifacts["features"]),"sha256":hash_file(artifacts["features"])}
    micro=comparisons.loc[(comparisons.aggregation=="micro")&(comparisons.metric=="mae")].copy()
    for key,subset in [("comparisons",micro.loc[~micro.candidate.str.contains("ablation")]),("ablation",micro.loc[micro.candidate.str.contains("ablation")])]:
        if subset.empty:
            continue
        groups=list(subset.groupby("unit",sort=True))
        fig,axes=plt.subplots(len(groups),1,figsize=(11,max(4,len(subset)*.4)),squeeze=False)
        for ax,(unit,group) in zip(axes[:,0],groups):
            ax.barh([f"{a} vs {b}" for a,b in zip(group.candidate,group.reference)],group.delta)
            ax.axvline(0,color="black",lw=1)
            ax.set_xlabel(f"Delta MAE candidate-reference ({unit}); âm tốt hơn")
            ax.set_title(f"{key}: locked test; N={sorted(group.n_rows.unique().tolist())}; trận={sorted(group.n_matches.unique().tolist())}")
        save(fig,key,"comparisons","Cùng cohort/recipe; delta âm giảm lỗi. Bỏ nhóm là contribution dự đoán, không nhân quả.")
    ci=micro.loc[micro.ci_lower.notna() & micro.ci_upper.notna()]
    if not ci.empty:
        groups=list(ci.groupby("unit",sort=True))
        fig,axes=plt.subplots(len(groups),1,figsize=(12,max(5,len(ci)*.4)),squeeze=False)
        for ax,(unit,group) in zip(axes[:,0],groups):
            positions=np.arange(len(group))
            ax.hlines(positions,group.ci_lower,group.ci_upper)
            ax.scatter(group.delta,positions,label="Observed delta")
            ax.set_yticks(positions,[f"{a} vs {b}" for a,b in zip(group.candidate,group.reference)])
            ax.axvline(0,color="black",lw=1)
            ax.set_xlabel(f"Delta MAE ({unit}); 95% percentile match bootstrap")
            ax.set_title(f"Locked test; N={sorted(group.n_rows.unique().tolist())}; trận={sorted(group.n_matches.unique().tolist())}")
        save(fig,"forest","comparisons","CI chứa 0: chưa rõ chiều cải thiện; lặp player qua trận vẫn là giới hạn. Chỉ CI micro đã tính được vẽ.")
    for key,column,label in [("error","mae","MAE"),("coverage","n_observations","Số player-match")]:
        group=errors.loc[errors.slice_category=="mode"]
        # Do not mix survival and placement error scales.
        groups=list(group.groupby("unit"))
        fig,axes=plt.subplots(len(groups),1,figsize=(10,max(5,len(group)*.5+2*len(groups))),squeeze=False)
        for ax,(unit,group) in zip(axes[:,0],groups):
            matrix=group.pivot(index="experiment_id",columns="slice_value",values=column)
            shown=ax.imshow(np.ma.masked_invalid(matrix.to_numpy()),aspect="auto",cmap="viridis",vmin=0,vmax=max(1e-12,float(np.nanmax(matrix.to_numpy()))))
            ax.set_xticks(range(len(matrix.columns)),matrix.columns)
            ax.set_yticks(range(len(matrix)),matrix.index)
            displayed_unit=unit if key=="error" else "player-match rows"
            ax.set_title(f"Locked test; {label} ({displayed_unit})\nN/mode={sorted(group.n_observations.unique().tolist())}; trận/mode={sorted(group.n_matches.unique().tolist())}; ít trận = không ổn định")
            fig.colorbar(shown,ax=ax,label=label)
        save(fig,key,"errors","Mode canonical; missing/empty không thay bằng 0 MAE; đọc cùng counts, coverage và trạng thái slice.")
    if not residuals.empty:
        groups=list(residuals.groupby("experiment_id"))
        fig,axes=plt.subplots(len(groups),1,figsize=(10,3*len(groups)),squeeze=False)
        for ax,(name,group) in zip(axes[:,0],groups):
            ax.bar(group.left,group.n,width=group.right-group.left,align="edge")
            ax.axvline(0,color="black")
            ax.set_title(f"{name}; locked test N={group.total_n.iloc[0]}; đủ toàn file")
            unit="score [0,1]" if "placement" in recipe["models"][name]["target"] else "source time unit (pending verification)"
            ax.set_xlabel(f"Residual actual-predicted ({unit})")
            ax.set_ylabel("Số player-match")
        save(fig,"residual","residuals","Residual dương: dự đoán thấp hơn actual; phân bố toàn cohort, không clip prediction. Histogram test chỉ mô tả.")
    group=importance.loc[importance.experiment_id=="p2_ols_no_direct_survival"] if "experiment_id" in importance else pd.DataFrame()
    if not group.empty and "mae_increase_mean" in group:
        group=group.loc[group.status=="completed"].sort_values("mae_increase_mean")
        fig,ax=plt.subplots(figsize=(10,6))
        ax.barh(group.feature,group.mae_increase_mean,xerr=group.mae_increase_std)
        ax.set_title(f"P2 validation permutation; N={group.n.iloc[0]}; repeats={group.repeats.iloc[0]}; seed={group.seed.iloc[0]}")
        ax.set_xlabel("MAE tăng khi xáo trộn feature (score); thanh sai số = std, không phải CI")
        save(fig,"importance","validation_importance","Tái sử dụng evidence validation đã duyệt; tương quan làm phân tán importance. Không chọn lại feature bằng test; group ablation là bằng chứng contribution chính.")
    output=paths["manifests"]/"rq3_evaluation_figure_catalog.json"
    atomic_write_json(output,catalog)
    produced["figure_catalog"]=output
    return produced
