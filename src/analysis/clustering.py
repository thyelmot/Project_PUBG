from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import numpy as np
import pandas as pd
from sklearn.cluster import AgglomerativeClustering, KMeans, MiniBatchKMeans
from sklearn.metrics import adjusted_rand_score, davies_bouldin_score, silhouette_score
from sklearn.preprocessing import RobustScaler, StandardScaler
from src.utils.logging import get_logger

logger = get_logger("pubg_clustering")

CORE_PROFILE_FEATURES = [
    "mean_kills", "std_kills", "mean_damage", "std_damage", "mean_damage_per_kill",
    "mean_walk_distance", "mean_ride_distance", "mean_walk_ratio",
    "mean_assists", "mean_dbno", "mean_assist_ratio",
    "avg_early_kill_ratio", "avg_mid_kill_ratio", "avg_late_kill_ratio",
    "early_combat_match_ratio",
]


def run_k_diagnostics(
    X: np.ndarray,
    k_range: List[int] = [2, 3, 4, 5, 6, 7, 8],
    random_state: int = 42,
    sample_size_for_silhouette: int = 10000,
) -> pd.DataFrame:
    """Evaluate candidate cluster counts across inertia, silhouette, and Davies-Bouldin metrics."""
    results = []

    # Subsample for silhouette if dataset is massive
    n_samples = X.shape[0]
    if n_samples > sample_size_for_silhouette:
        rng = np.random.RandomState(random_state)
        sample_indices = rng.choice(n_samples, size=sample_size_for_silhouette, replace=False)
        X_eval = X[sample_indices]
    else:
        X_eval = X

    for k in k_range:
        if k >= n_samples:
            continue
        km = KMeans(n_clusters=k, random_state=random_state, n_init=10)
        labels = km.fit_predict(X)
        labels_eval = labels if n_samples <= sample_size_for_silhouette else km.predict(X_eval)

        valid_labels = 1 < len(np.unique(labels_eval)) < len(X_eval)
        sil = silhouette_score(X_eval, labels_eval) if valid_labels else np.nan
        db = davies_bouldin_score(X_eval, labels_eval) if valid_labels else np.nan

        # Size distribution
        sizes = pd.Series(labels).value_counts(normalize=True).to_dict()
        min_size = min(sizes.values())
        max_size = max(sizes.values())

        results.append({
            "k": k,
            "inertia": float(km.inertia_),
            "silhouette_score": float(sil),
            "davies_bouldin_score": float(db),
            "min_cluster_share": float(min_size),
            "max_cluster_share": float(max_size),
        })

    return pd.DataFrame(results)


def execute_rq2_clustering(
    profile_df: pd.DataFrame,
    outcome_df: pd.DataFrame,
    n_clusters: int,
    output_dir: Path,
    scaler_type: str = "standard",
    random_state: int = 42,
) -> Dict[str, Any]:
    """Execute complete RQ2 experimental suite: C1 (main), C2 (hierarchical), C3 (games_played), C5 (outcomes)."""
    output_dir.mkdir(parents=True, exist_ok=True)

    # Invariant: Features MUST NOT include games_played or outcomes in C1!
    feature_cols = [c for c in CORE_PROFILE_FEATURES if c in profile_df.columns]
    X_raw = profile_df[feature_cols].values

    # 1. Scaling
    scaler = StandardScaler() if scaler_type == "standard" else RobustScaler()
    X_scaled = scaler.fit_transform(X_raw)

    # 2. C1 Main Clustering (K-Means)
    km = KMeans(n_clusters=n_clusters, random_state=random_state, n_init=10)
    labels = km.fit_predict(X_scaled)
    profile_df["cluster_label"] = labels
    outcome_df["cluster_label"] = labels

    # Cluster Centers: Raw and Standardized
    centers_scaled = pd.DataFrame(km.cluster_centers_, columns=feature_cols)
    centers_scaled.index.name = "cluster_id"

    # Compute raw cluster centers directly from profile dataframe
    centers_raw = profile_df.groupby("cluster_label")[feature_cols].mean()
    centers_raw["profile_count"] = profile_df.groupby("cluster_label").size()
    centers_raw["profile_percentage"] = (centers_raw["profile_count"] / len(profile_df)) * 100.0

    centers_raw.to_csv(output_dir / "cluster_profile.csv")
    centers_scaled.to_csv(output_dir / "cluster_centers_standardized.csv")

    # 3. C2 Hierarchical validation (on representative subset if large)
    subset_size = min(3000, len(X_scaled))
    rng = np.random.RandomState(random_state)
    sub_indices = rng.choice(len(X_scaled), size=subset_size, replace=False)
    agg = AgglomerativeClustering(n_clusters=n_clusters, linkage="ward")
    agg_labels = agg.fit_predict(X_scaled[sub_indices])
    c2_ari = adjusted_rand_score(labels[sub_indices], agg_labels)

    # 4. C3 games_played sensitivity (clustering with games_played included)
    X_c3_raw = profile_df[feature_cols + ["games_played"]].values
    X_c3_scaled = StandardScaler().fit_transform(X_c3_raw)
    km_c3 = KMeans(n_clusters=n_clusters, random_state=random_state, n_init=10)
    c3_labels = km_c3.fit_predict(X_c3_scaled)
    c3_ari = adjusted_rand_score(labels, c3_labels)

    # Stability across random seeds
    km_seed = KMeans(n_clusters=n_clusters, random_state=random_state + 100, n_init=10)
    seed_labels = km_seed.fit_predict(X_scaled)
    seed_ari = adjusted_rand_score(labels, seed_labels)

    robustness_df = pd.DataFrame([
        {"comparison": "C2_Hierarchical_vs_KMeans", "metric": "Adjusted_Rand_Index", "value": float(c2_ari), "n_sample": subset_size},
        {"comparison": "C3_Games_Played_Sensitivity", "metric": "Adjusted_Rand_Index", "value": float(c3_ari), "n_sample": len(labels)},
        {"comparison": "Seed_Stability", "metric": "Adjusted_Rand_Index", "value": float(seed_ari), "n_sample": len(labels)},
    ])
    robustness_df.to_csv(output_dir / "clustering_robustness.csv", index=False)

    # 5. C5 Outcome comparison (strictly descriptive post-hoc!)
    c5_table = outcome_df.groupby("cluster_label").agg(
        n_players=("player_name", "count"),
        mean_survival=("mean_survive_time", "mean"),
        median_survival=("mean_survive_time", "median"),
        mean_placement=("mean_normalized_placement", "mean"),
        median_placement=("mean_normalized_placement", "median"),
        win_rate=("win_rate", "mean"),
    ).reset_index()
    c5_table.to_csv(output_dir / "c5_outcome_comparison.csv", index=False)

    logger.info(f"RQ2 Clustering C1-C5 completed for K={n_clusters}. Output saved to {output_dir}")

    return {
        "centers_raw": centers_raw,
        "robustness": robustness_df,
        "outcome_comparison": c5_table,
    }
