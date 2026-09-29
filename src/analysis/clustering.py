import joblib
from pathlib import Path
from src.data.io import atomic_write_csv
from typing import Any, Dict, List, Optional, Tuple
import numpy as np
import pandas as pd
from sklearn.cluster import AgglomerativeClustering, KMeans, MiniBatchKMeans
from sklearn.metrics import adjusted_rand_score, davies_bouldin_score, silhouette_score
from sklearn.preprocessing import RobustScaler, StandardScaler
from sklearn.impute import SimpleImputer
from src.utils.logging import get_logger
from src.features.profiles import profile_keys
from src.models.compute import make_kmeans

logger = get_logger("pubg_clustering")

CORE_PROFILE_FEATURES = [
    "mean_kills", "std_kills", "mean_damage", "std_damage", "mean_damage_per_kill",
    "mean_walk_distance", "mean_ride_distance", "mean_walk_ratio",
    "mean_assists", "mean_dbno", "mean_assist_ratio",
    "avg_early_kill_ratio", "avg_mid_kill_ratio", "avg_late_kill_ratio",
    "early_combat_match_ratio",
]


def fit_clustering_pipeline(profile_df: pd.DataFrame, scaler_type: str = "standard"):
    """Fit imputer and scaler on behavioral profiles, returning matrix and fitted transformers."""
    if scaler_type not in ("standard", "robust"):
        raise ValueError("scaler must be standard or robust")
    columns = [c for c in CORE_PROFILE_FEATURES if c in profile_df]
    if not columns:
        raise ValueError("No behavioral profile columns available for clustering")
    
    # Purposeful domain imputation before general mean imputation:
    # Combat ratios and counts for players with 0 combat/assists represent 0 engagement intensity
    df_imputed = profile_df[columns].copy()
    zero_fill_combat = [
        "mean_damage_per_kill", "mean_assist_ratio", "avg_early_kill_ratio",
        "avg_mid_kill_ratio", "avg_late_kill_ratio", "early_combat_match_ratio"
    ]
    for col in zero_fill_combat:
        if col in df_imputed.columns:
            df_imputed[col] = df_imputed[col].fillna(0.0)
            
    values = df_imputed.replace([np.inf, -np.inf], np.nan).to_numpy(dtype=float)
    if len(values) == 0:
        return values, None, None, columns
    imputer = SimpleImputer(strategy="mean", keep_empty_features=True)
    values = imputer.fit_transform(values)
    scaler = StandardScaler() if scaler_type == "standard" else RobustScaler()
    X_scaled = scaler.fit_transform(values)
    return X_scaled, imputer, scaler, columns


def prepare_clustering_matrix(profile_df: pd.DataFrame, scaler_type: str = "standard") -> np.ndarray:
    X_scaled, _, _, _ = fit_clustering_pipeline(profile_df, scaler_type)
    return X_scaled


def assign_behavioral_cluster_names(centers_standardized_df: pd.DataFrame) -> Dict[int, str]:
    """Assign descriptive behavioral archetype labels based on standardized behavioral centers.
    
    Rules strictly use behavioral inputs (combat, movement, timing, support)
    and NEVER rely on game outcomes (win rate, survive time, placement).
    """
    names = {}
    for idx, row in centers_standardized_df.iterrows():
        kills_z = float(row.get("mean_kills", 0.0))
        dmg_z = float(row.get("mean_damage", 0.0))
        walk_z = float(row.get("mean_walk_distance", 0.0))
        ride_z = float(row.get("mean_ride_distance", 0.0))
        early_z = float(row.get("avg_early_kill_ratio", 0.0))
        assist_z = float(row.get("mean_assists", 0.0))
        dbno_z = float(row.get("mean_dbno", 0.0))
        dpk_z = float(row.get("mean_damage_per_kill", 0.0))
        
        is_combat = (kills_z > 0.3) or (dmg_z > 0.3)
        is_mobile = (walk_z > 0.3) or (ride_z > 0.3)
        is_early = early_z > 0.3
        is_support = (assist_z > 0.3) or (dbno_z > 0.3)
        is_sniper = dpk_z > 0.5 and not is_early
        
        if is_combat and is_early:
            label = "Aggressive Rusher"
        elif is_sniper:
            label = "Distance Marksman"
        elif is_combat:
            label = "Combat Specialist"
        elif is_support and not is_combat:
            label = "Tactical Support"
        elif is_mobile and not is_combat:
            label = "Cautious Navigator"
        elif not is_combat and not is_mobile:
            label = "Passive Explorer"
        else:
            label = "Balanced Operator"
        names[int(idx)] = label
    
    # Disambiguate duplicate names with unique archetype suffixes
    counts = {}
    for idx, name in names.items():
        counts[name] = counts.get(name, 0) + 1
    seen = {}
    assigned = {}
    for idx, name in names.items():
        if counts[name] > 1:
            seen[name] = seen.get(name, 0) + 1
            assigned[idx] = f"{name} (Type {seen[name]})"
        else:
            assigned[idx] = name
    return assigned


def run_k_diagnostics(
    X: np.ndarray,
    k_range: List[int] = [2, 3, 4, 5, 6, 7, 8],
    random_state: int = 42,
    sample_size_for_silhouette: int = 10000,
    device: str = 'cpu',
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
        km = make_kmeans(device, n_clusters=k, random_state=random_state, n_init=10)
        labels = km.fit_predict(X)
        seed_labels = make_kmeans(device, n_clusters=k, random_state=random_state + 100, n_init=10).fit_predict(X)
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
            "seed_stability_ari": float(adjusted_rand_score(labels, seed_labels)),
        })

    return pd.DataFrame(results, columns=["k", "inertia", "silhouette_score",
                                         "davies_bouldin_score", "min_cluster_share", "max_cluster_share", "seed_stability_ari"])


def execute_rq2_clustering(
    profile_df: pd.DataFrame,
    outcome_df: pd.DataFrame,
    n_clusters: int,
    output_dir: Path,
    scaler_type: str = "standard",
    random_state: int = 42,
    device: str = 'cpu',
) -> Dict[str, Any]:
    """Execute complete RQ2 experimental suite: C1 (main), C2 (hierarchical), C3 (games_played), C5 (outcomes)."""
    output_dir.mkdir(parents=True, exist_ok=True)
    profile_df = profile_df.copy()
    keys = profile_keys(profile_df)
    outcome_df = profile_df[keys].merge(outcome_df, on=keys, how="left", validate="one_to_one", indicator=True)
    if (outcome_df["_merge"] != "both").any():
        raise ValueError("Missing outcome profile for a player")
    outcome_df = outcome_df.drop(columns="_merge")

    # Invariant: Features MUST NOT include games_played or outcomes in C1!
    feature_cols = [c for c in CORE_PROFILE_FEATURES if c in profile_df.columns]
    X_scaled, imputer, scaler, feature_cols = fit_clustering_pipeline(profile_df, scaler_type)
    if n_clusters < 2:
        raise ValueError("n_clusters must be at least 2")
    if len(X_scaled) < n_clusters or len(np.unique(X_scaled, axis=0)) < n_clusters:
        centers = pd.DataFrame(columns=["cluster_label", *feature_cols, "profile_count", "profile_percentage", "behavioral_name"])
        outcomes = pd.DataFrame(columns=["cluster_label", "n_players", "mean_survival", "median_survival",
                                         "mean_placement", "median_placement", "win_rate"])
        robustness = pd.DataFrame(columns=["comparison", "metric", "value", "n_sample", "population_size", "seed", "sampling_rule"])
        atomic_write_csv(output_dir / "cluster_profile.csv", centers)
        atomic_write_csv(output_dir / "cluster_centers_standardized.csv", pd.DataFrame(columns=["cluster_id", *feature_cols, "behavioral_name"]))
        atomic_write_csv(output_dir / "c5_outcome_comparison.csv", outcomes)
        atomic_write_csv(output_dir / "clustering_robustness.csv", robustness)
        logger.warning("Clustering skipped: insufficient distinct eligible profiles for K=%s", n_clusters)
        return {"status": "skipped_insufficient_profiles", "centers_raw": centers,
                "robustness": robustness, "outcome_comparison": outcomes}

    # 2. C1 Main Clustering (K-Means)
    km = make_kmeans(device, n_clusters=n_clusters, random_state=random_state, n_init=10)
    labels = km.fit_predict(X_scaled)
    profile_df["cluster_label"] = labels
    outcome_df["cluster_label"] = labels

    # Cluster Centers: Raw and Standardized
    centers_scaled = pd.DataFrame(km.cluster_centers_, columns=feature_cols)
    centers_scaled.index.name = "cluster_id"

    # Compute behavioral archetypes based on standardized centers without outcomes
    behavioral_names = assign_behavioral_cluster_names(centers_scaled)
    centers_scaled["behavioral_name"] = centers_scaled.index.map(behavioral_names)

    # Compute raw cluster centers directly from profile dataframe
    centers_raw = profile_df.groupby("cluster_label")[feature_cols].mean()
    centers_raw["profile_count"] = profile_df.groupby("cluster_label").size()
    centers_raw["profile_percentage"] = (centers_raw["profile_count"] / len(profile_df)) * 100.0
    centers_raw["behavioral_name"] = centers_raw.index.map(behavioral_names)

    profile_df["behavioral_name"] = profile_df["cluster_label"].map(behavioral_names)
    atomic_write_csv(output_dir / "cluster_assignments.csv", profile_df[keys + ["cluster_label", "behavioral_name"]])

    atomic_write_csv(output_dir / "cluster_profile.csv", centers_raw, index=True)
    atomic_write_csv(output_dir / "cluster_centers_standardized.csv", centers_scaled, index=True)

    # 3. C2 Hierarchical validation (on representative subset if large)
    subset_size = min(3000, len(X_scaled))
    rng = np.random.RandomState(random_state)
    sub_indices = rng.choice(len(X_scaled), size=subset_size, replace=False)
    agg = AgglomerativeClustering(n_clusters=n_clusters, linkage="ward")
    agg_labels = agg.fit_predict(X_scaled[sub_indices])
    c2_ari = adjusted_rand_score(labels[sub_indices], agg_labels)
    np.save(output_dir / "c2_sample_indices.npy", sub_indices)

    # 4. C3 games_played sensitivity (clustering with games_played included, using consistent scaler policy)
    X_c3_raw = np.column_stack([X_scaled, profile_df["games_played"].values])
    scaler_c3 = StandardScaler() if scaler_type == "standard" else RobustScaler()
    X_c3_scaled = scaler_c3.fit_transform(X_c3_raw)
    km_c3 = make_kmeans(device, n_clusters=n_clusters, random_state=random_state, n_init=10)
    c3_labels = km_c3.fit_predict(X_c3_scaled)
    c3_ari = adjusted_rand_score(labels, c3_labels)

    # Stability across random seeds
    km_seed = make_kmeans(device, n_clusters=n_clusters, random_state=random_state + 100, n_init=10)
    seed_labels = km_seed.fit_predict(X_scaled)
    seed_ari = adjusted_rand_score(labels, seed_labels)

    robustness_df = pd.DataFrame([
        {"comparison": "C2_Hierarchical_vs_KMeans", "metric": "Adjusted_Rand_Index", "value": float(c2_ari),
         "n_sample": subset_size, "population_size": len(X_scaled), "seed": random_state, "sampling_rule": "uniform_without_replacement"},
        {"comparison": "C3_Games_Played_Sensitivity", "metric": "Adjusted_Rand_Index", "value": float(c3_ari),
         "n_sample": len(labels), "population_size": len(X_scaled), "seed": random_state, "sampling_rule": "full_eligible"},
        {"comparison": "Seed_Stability", "metric": "Adjusted_Rand_Index", "value": float(seed_ari),
         "n_sample": len(labels), "population_size": len(X_scaled), "seed": random_state + 100, "sampling_rule": "full_eligible"},
    ])
    atomic_write_csv(output_dir / "clustering_robustness.csv", robustness_df)

    # 5. C5 Outcome comparison (strictly descriptive post-hoc!)
    c5_table = outcome_df.groupby("cluster_label").agg(
        n_players=("player_name", "count"),
        mean_survival=("mean_survive_time", "mean"),
        median_survival=("mean_survive_time", "median"),
        mean_placement=("mean_normalized_placement", "mean"),
        median_placement=("mean_normalized_placement", "median"),
        win_rate=("win_rate", "mean"),
    ).reset_index()
    c5_table["behavioral_name"] = c5_table["cluster_label"].map(behavioral_names)
    atomic_write_csv(output_dir / "c5_outcome_comparison.csv", c5_table)

    # Save fitted model artifacts for reproducibility and inference
    artifacts_dict = {
        "imputer": imputer,
        "scaler": scaler,
        "kmeans": km,
        "feature_cols": feature_cols,
        "behavioral_names": behavioral_names,
        "scaler_type": scaler_type,
        "n_clusters": n_clusters,
        "random_state": random_state,
        "device": device,
    }
    model_artifact_path = output_dir / "fitted_clustering_artifacts.joblib"
    joblib.dump(artifacts_dict, model_artifact_path)

    logger.info(f"RQ2 Clustering C1-C5 completed for K={n_clusters}. Output saved to {output_dir}")

    return {
        "centers_raw": centers_raw,
        "centers_scaled": centers_scaled,
        "robustness": robustness_df,
        "outcome_comparison": c5_table,
        "fitted_artifacts_path": model_artifact_path,
        "behavioral_names": behavioral_names,
    }
