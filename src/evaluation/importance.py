from pathlib import Path
from typing import Any, Dict, List, Optional
import numpy as np
import pandas as pd
from sklearn.inspection import permutation_importance
from src.utils.logging import get_logger

logger = get_logger("pubg_importance")


def extract_feature_importance(
    model: Any,
    feature_names: List[str],
    X_val: Optional[np.ndarray] = None,
    y_val: Optional[np.ndarray] = None,
    output_table_path: Optional[Path] = None,
) -> pd.DataFrame:
    """Extract model feature importance / linear coefficients with non-causal interpretation guidelines."""
    records = []

    # 1. Linear coefficients if available
    coefs = getattr(model, "coefficients", None)
    if coefs is not None and len(coefs) == len(feature_names):
        for feat, c in zip(feature_names, coefs):
            records.append({
                "feature": feat,
                "importance_type": "standardized_linear_coefficient",
                "importance_value": float(c),
                "absolute_importance": float(abs(c)),
            })

    # 2. Tree feature importances if available
    tree_model = getattr(model, "model", None) or getattr(model, "pipeline", None)
    if tree_model is not None and hasattr(tree_model, "feature_importances_"):
        fi = tree_model.feature_importances_
        if len(fi) == len(feature_names):
            for feat, imp in zip(feature_names, fi):
                records.append({
                    "feature": feat,
                    "importance_type": "tree_gini_impurity",
                    "importance_value": float(imp),
                    "absolute_importance": float(imp),
                })

    # 3. Permutation importance if validation set provided
    if X_val is not None and y_val is not None and len(X_val) >= 20:
        try:
            perm_res = permutation_importance(model, X_val, y_val, n_repeats=5, random_state=42, scoring="neg_mean_absolute_error")
            for feat, mean_imp, std_imp in zip(feature_names, perm_res.importances_mean, perm_res.importances_std):
                records.append({
                    "feature": feat,
                    "importance_type": "permutation_mae_drop",
                    "importance_value": float(mean_imp),
                    "absolute_importance": float(abs(mean_imp)),
                })
        except Exception as e:
            logger.warning(f"Could not compute permutation importance: {e}")

    df_imp = pd.DataFrame(records)
    if not df_imp.empty:
        df_imp = df_imp.sort_values(by="absolute_importance", ascending=False).reset_index(drop=True)

    if output_table_path:
        output_table_path.parent.mkdir(parents=True, exist_ok=True)
        df_imp.to_csv(output_table_path, index=False)
        logger.info(f"Saved feature importance table -> {output_table_path.name}")

    return df_imp
