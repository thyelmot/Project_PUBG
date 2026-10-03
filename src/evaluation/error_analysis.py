"""Descriptive slices: metadata and bins approved before test, never data-driven tiers."""
import numpy as np
import pandas as pd
from src.data.io import atomic_write_csv
from src.evaluation.metrics import compute_regression_metrics


def validate_bins(edges, name):
    if not isinstance(edges, list) or len(edges)<2 or not np.isfinite(edges).all() or not all(a<b for a,b in zip(edges,edges[1:])):
        raise ValueError(f"Invalid/overlapping locked bins: {name}")


def bin_labels(values, edges):
    """Left closed/right open; include final endpoint. Missing/outside remain explicit."""
    validate_bins(edges, "slice")
    labels=[f"[{a}, {b}{']' if i==len(edges)-2 else ')'}" for i,(a,b) in enumerate(zip(edges,edges[1:]))]
    result=pd.cut(values,bins=edges,labels=labels,right=False).astype(object)
    result.loc[values==edges[-1]]=labels[-1]
    result=result.fillna("outside_locked_bins")
    result.loc[values.isna()]="missing"
    return result, labels+["outside_locked_bins","missing"]


def analyze_prediction_errors(pred_df, output_table_path, *, target_name=None, error_bins=None, min_matches=2):
    columns=["slice_category","slice_value","n_observations","n_matches","coverage","mae","rmse","r2","r2_reason","mean_residual","status","unit","scope"]
    test=pred_df.loc[pred_df["split"]=="test"].copy()
    if test.empty:
        result=pd.DataFrame(columns=columns)
        atomic_write_csv(output_table_path,result)
        return result
    if target_name is None:
        if "target" not in test or test.target.nunique()!=1:
            raise ValueError("Explicit target metadata required; cannot infer task from value range")
        target_name=test.target.iloc[0]
    placement=target_name in {"normalized_placement","current_normalized_placement"}
    if target_name not in {"normalized_placement","current_normalized_placement","player_survive_time","current_survive_time"}:
        raise ValueError("Unsupported target metadata")
    if not error_bins:
        raise ValueError("Error bins must be locked at G4 before reading test")
    if not np.isfinite(test.target_actual).all() or not np.isfinite(test.target_predicted).all():
        raise ValueError("Non-finite error targets/predictions; source repair required")
    slices=[("mode",test.team_size_mode.fillna("unknown"),None)] if "team_size_mode" in test else [("mode",pd.Series("unavailable",index=test.index),None)]
    name="placement" if placement else "survival"
    labels,levels=bin_labels(test.target_actual,error_bins[name])
    slices.append((name+"_region",labels,levels))
    if "hist_games_played" in test:
        if "history_depth" not in error_bins:
            raise ValueError("Historical depth bins must be approved at G4")
        labels,levels=bin_labels(test.hist_games_played,error_bins["history_depth"])
        slices.append(("history_depth",labels,levels))
    records=[]
    unit="score [0,1]" if placement else "source time unit (pending verification)"
    for category,labels,levels in slices:
        for label in levels or sorted(labels.unique()):
            group=test.loc[labels==label]
            metrics=compute_regression_metrics(group.target_actual.to_numpy(),group.target_predicted.to_numpy())
            matches=group.match_id.nunique()
            records.append({"slice_category":category,"slice_value":label,"n_observations":len(group),
                "n_matches":matches,"coverage":len(group)/len(test),**{key:metrics[key] for key in ["mae","rmse","r2","r2_reason"]},
                "mean_residual":float((group.target_actual-group.target_predicted).mean()) if len(group) else np.nan,
                "status":"insufficient" if not len(group) else "unstable_small_slice" if matches<min_matches else "descriptive",
                "unit":unit,"scope":"locked_test_descriptive_not_selection"})
    result=pd.DataFrame(records,columns=columns)
    atomic_write_csv(output_table_path,result)
    return result
