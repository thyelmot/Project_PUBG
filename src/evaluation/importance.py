"""Fitted-model descriptions. Never infer scaling or suppress failed importance."""
import numpy as np
import pandas as pd
from sklearn.inspection import permutation_importance
from src.data.io import atomic_write_csv


def extract_feature_importance(model, feature_names, X_val=None, y_val=None, output_table_path=None,
                               *, n_repeats=5, random_state=42, max_memory_gb=8., scope="validation"):
    records=[]
    pipeline=getattr(model,"pipeline",None)
    names=list(feature_names)
    if hasattr(model,"coefficient_names"):
        names=list(model.coefficient_names())
    elif pipeline is not None and "imputer" in pipeline.named_steps:
        names=list(pipeline.named_steps["imputer"].get_feature_names_out(feature_names))
    coefs=getattr(model,"coefficients",None)
    if coefs is not None and len(coefs)==len(names):
        kind="standardized_transformed_coefficient" if getattr(model,"standardize",False) else "unstandardized_coefficient"
        for name,value in zip(names,coefs):
            records.append({"feature":name,"importance_type":kind,"importance_value":float(value),
                "absolute_importance":abs(float(value)),"scope":"train_fit","status":"completed"})
    tree=getattr(model,"model",None)
    if pipeline is not None and "regressor" in pipeline.named_steps:
        tree=pipeline.named_steps["regressor"]
    if tree is not None and hasattr(tree,"feature_importances_"):
        for name,value in zip(feature_names,tree.feature_importances_):
            records.append({"feature":name,"importance_type":"regression_impurity_decrease","importance_value":float(value),
                "absolute_importance":abs(float(value)),"scope":"train_fit","status":"completed"})
    if X_val is not None and y_val is not None:
        if scope!="validation":
            raise ValueError("Final-test permutation requires separately pre-registered descriptive recipe")
        metadata={"scope":scope,"n":len(y_val),"repeats":n_repeats,"seed":random_state,"sampled":False,"max_memory_gb":max_memory_gb}
        from src.utils.runtime import collect_runtime_info
        free=collect_runtime_info().get("available_ram_gb")
        if not isinstance(free,(float,int)) or np.asarray(X_val).nbytes*4>min(free,max_memory_gb)*1024**3:
            records.append({**metadata,"status":"resource_limited","reason":"permutation_memory_budget"})
        else:
            try:
                perm=permutation_importance(model,X_val,y_val,n_repeats=n_repeats,random_state=random_state,scoring="neg_mean_absolute_error",n_jobs=1)
                for name,mean,std in zip(feature_names,perm.importances_mean,perm.importances_std):
                    records.append({**metadata,"feature":name,"importance_type":"permutation_mae_increase","importance_value":float(mean),
                        "absolute_importance":abs(float(mean)),"std":float(std),"status":"completed","reason":None})
            except Exception as error:
                records.append({**metadata,"status":"failed","reason":str(error)})
    frame=pd.DataFrame(records)
    if "absolute_importance" in frame:
        frame=frame.sort_values("absolute_importance",ascending=False).reset_index(drop=True)
    if output_table_path:
        atomic_write_csv(output_table_path,frame if len(frame.columns) else pd.DataFrame(columns=["status","reason"]))
    return frame
