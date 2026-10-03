"""Development-only feature evidence, never mechanically deletes a column or opens test."""
import numpy as np
import pandas as pd
from sklearn.linear_model import LinearRegression
from src.data.io import atomic_write_csv, atomic_write_json, read_json
from src.utils.hashing import hash_file, hash_dict


def feature_diagnostics(cohorts, features, models, paths, registry, max_memory_gb=8.):
    records, correlations, coefficients, importance = [], [], [], []
    for task,cohort in cohorts.items():
        train=cohort.loc[cohort.split=="train",features[task]].astype(float)
        if train.empty:
            continue
        for name in features[task]:
            col=train[name]
            records.append({"task":task,"feature":name,"fit_scope":"train","n":len(col),
                "valid_n":int(col.notna().sum()),"missing_fraction":float(col.isna().mean()),
                "zero_fraction":float((col==0).mean()),"variance":float(col.var(ddof=0)),
                "all_missing":bool(col.isna().all()),"constant_observed":bool(col.nunique()<=1),
                "vif":None,"vif_reason":"not_a_suitable_raw_subset","automatic_drop":False})
        raw=[name for name in features[task] if registry.get(name) and not registry.get(name).depends_on
             and train[name].nunique()>1 and train[name].notna().any()]
        matrix=train[raw].fillna(train[raw].mean()).to_numpy()
        for index,name in enumerate(raw):
            reason=None
            if matrix.shape[0] <= len(raw) or len(raw)<2:
                value=np.nan
                reason="too_few_rows_or_predictors"
            else:
                r2=LinearRegression().fit(np.delete(matrix,index,axis=1),matrix[:,index]).score(np.delete(matrix,index,axis=1),matrix[:,index])
                value=1/(1-r2) if r2<1 else np.inf
                reason="exact_collinearity" if not np.isfinite(value) else None
            next(row for row in records if row["task"]==task and row["feature"]==name).update(vif=value,vif_reason=reason)
        for method in ["pearson","spearman"]:
            corr=train.corr(method=method)
            for i,left in enumerate(corr.columns):
                for right in corr.columns[i+1:]:
                    correlations.append({"task":task,"method":method,"left":left,"right":right,
                        "joint_valid_n":int(train[[left,right]].notna().all(axis=1).sum()),
                        "correlation":corr.loc[left,right],"fit_scope":"train","automatic_drop":False})
    for exp_id,model in models.items():
        meta=read_json(paths["models"]/f"meta_{exp_id}.json")
        if hasattr(model,"coefficients"):
            names=model.coefficient_names() if hasattr(model,"coefficient_names") else model.pipeline.named_steps["imputer"].get_feature_names_out(meta["features"])
            for name,value in zip(names,model.coefficients):
                coefficients.append({"experiment_id":exp_id,"transformed_feature":str(name),"coefficient":float(value),
                    "type":"standardized_linear_coefficient" if model.standardize else "unstandardized_linear_coefficient",
                    "scope":"train_fit","limitation":"correlated features; not causal"})
        if meta["features"] and "ablation" not in exp_id and not exp_id.startswith(("t0_","t1_")):
            validation=cohorts[meta["task"]].loc[cohorts[meta["task"]].split=="validation"]
            from src.models.rq3_resources import resource_snapshot
            budget=resource_snapshot(validation,meta["features"],meta["compute"]["device"],max_memory_gb)
            metadata={"n":len(validation),"scope":"validation","repeats":3,"seed":42,"sampled":False,
                "configured_memory_bytes":budget["configured_memory_bytes"],"estimated_working_bytes":budget["estimated_working_bytes"],
                "ram_available_bytes":budget["ram_available_bytes"],"vram_free_bytes":budget["vram_free_bytes"],"budget_measured_at":budget["measured_at_utc"]}
            if budget["status"]!="ready":
                importance.append({"experiment_id":exp_id,**metadata,"status":"resource_limited","reason":budget["reason_code"]})
                continue
            from sklearn.inspection import permutation_importance
            try:
                measured=permutation_importance(model,validation[meta["features"]].to_numpy(),validation[meta["target"]].to_numpy(),
                    n_repeats=3,random_state=42,scoring="neg_mean_absolute_error",n_jobs=1)
                for name,mean,std in zip(meta["features"],measured.importances_mean,measured.importances_std):
                    importance.append({"experiment_id":exp_id,"feature":name,"mae_increase_mean":float(mean),
                        "mae_increase_std":float(std),**metadata,"status":"completed","reason":None})
            except Exception as error:
                importance.append({"experiment_id":exp_id,**metadata,"status":"failed","reason":str(error)})
    artifacts={}
    for key,frame in [("features",pd.DataFrame(records)),("correlations",pd.DataFrame(correlations)),
                      ("coefficients",pd.DataFrame(coefficients)),("importance",pd.DataFrame(importance))]:
        output=paths["tables"]/f"rq3_{key}_diagnostics.csv"
        # Header-only tables remain explicit if all experiments are disabled.
        if not len(frame.columns):
            frame=pd.DataFrame(columns=["status","reason"])
        atomic_write_csv(output,frame)
        artifacts[key]=output
    receipt={"scope":"train_statistics_validation_models","automatic_feature_deletion":False,
        "tables":{key:{"path":str(path),"sha256":hash_file(path)} for key,path in artifacts.items()},
        "importance_failures":sum(row.get("status") in {"failed","resource_limited"} for row in importance),
        "limitation":"VIF raw numeric subset only; final feature/transform/importance review requires explicit approval"}
    receipt["diagnostics_hash"]=hash_dict(receipt)
    output=paths["manifests"]/"rq3_feature_diagnostics_receipt.json"
    atomic_write_json(output,receipt)
    artifacts["receipt"]=output
    return artifacts
