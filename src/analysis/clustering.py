import hashlib
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
    "mean_kills", "std_kills", "mean_damage", "std_damage",
    "mean_walk_distance", "mean_ride_distance", "mean_walk_ratio",
    "mean_assists", "mean_dbno", "mean_assist_ratio",
    "avg_early_kill_ratio", "avg_mid_kill_ratio", "avg_late_kill_ratio",
    "early_combat_match_ratio",
]


def _profile_values(profile_df: pd.DataFrame, columns: List[str], log_features: Optional[List[str]] = None) -> np.ndarray:
    values = profile_df[columns].replace([np.inf, -np.inf], np.nan).copy()
    log_features = log_features or []
    unknown = sorted(set(log_features) - set(columns))
    if unknown:
        raise ValueError(f"Log-transform features are not clustering inputs: {unknown}")
    for feature in log_features:
        if (values[feature].dropna() < 0).any():
            raise ValueError(f"log1p requires non-negative values: {feature}")
        values[feature] = np.log1p(values[feature])
    return values.to_numpy(dtype=float)


def fit_clustering_pipeline(profile_df: pd.DataFrame, scaler_type: str = "standard",
                            log_transform_features: Optional[List[str]] = None):
    """Fit imputer and scaler on behavioral profiles, returning matrix and fitted transformers."""
    if scaler_type not in ("standard", "robust"):
        raise ValueError("scaler must be standard or robust")
    columns = [c for c in CORE_PROFILE_FEATURES if c in profile_df]
    if not columns:
        raise ValueError("No behavioral profile columns available for clustering")
    
    values = _profile_values(profile_df, columns, log_transform_features)
    if len(values) == 0:
        return values, None, None, columns
    imputer = SimpleImputer(strategy="mean", keep_empty_features=True)
    values = imputer.fit_transform(values)
    scaler = StandardScaler() if scaler_type == "standard" else RobustScaler()
    X_scaled = scaler.fit_transform(values)
    return X_scaled, imputer, scaler, columns


def prepare_clustering_matrix(profile_df: pd.DataFrame, scaler_type: str = "standard",
                              log_transform_features: Optional[List[str]] = None) -> np.ndarray:
    X_scaled, _, _, _ = fit_clustering_pipeline(profile_df, scaler_type, log_transform_features)
    return X_scaled


def predict_clusters(fitted: Any, profile_df: pd.DataFrame) -> np.ndarray:
    """Assign profiles with a persisted pipeline without refitting any component."""
    artifact = joblib.load(fitted) if isinstance(fitted, (str, Path)) else fitted
    columns = artifact["feature_cols"]
    values = _profile_values(profile_df, columns, artifact.get("log_transform_features"))
    return artifact["kmeans"].predict(artifact["scaler"].transform(artifact["imputer"].transform(values)))


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
        
        is_combat = (kills_z > 0.3) or (dmg_z > 0.3)
        is_mobile = (walk_z > 0.3) or (ride_z > 0.3)
        is_early = early_z > 0.3
        is_support = (assist_z > 0.3) or (dbno_z > 0.3)
        
        if is_combat and is_early:
            label = "Aggressive Rusher"
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
    sample_size_for_silhouette: Optional[int] = None,
    device: str = 'cpu',
) -> pd.DataFrame:
    """Evaluate candidate cluster counts across inertia, silhouette, and Davies-Bouldin metrics."""
    results = []

    # Subsample for silhouette if dataset is massive
    n_samples = X.shape[0]
    if sample_size_for_silhouette is not None and sample_size_for_silhouette < 2:
        raise ValueError("sample_size_for_silhouette must be null or >= 2")
    if sample_size_for_silhouette is not None and n_samples > sample_size_for_silhouette:
        rng = np.random.RandomState(random_state)
        sample_indices = rng.choice(n_samples, size=sample_size_for_silhouette, replace=False)
        X_eval = X[sample_indices]
    else:
        X_eval = X
        sample_indices = np.arange(n_samples, dtype=np.int64)
    sample_digest = hashlib.sha256(np.asarray(sample_indices, dtype=np.int64).tobytes()).hexdigest()

    for k in k_range:
        if k >= n_samples:
            continue
        km = make_kmeans(device, n_clusters=k, random_state=random_state, n_init=10)
        labels = km.fit_predict(X)
        seed_labels = make_kmeans(device, n_clusters=k, random_state=random_state + 100, n_init=10).fit_predict(X)
        labels_eval = labels if len(X_eval) == n_samples else km.predict(X_eval)

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
            "diagnostic_sample_n": len(X_eval),
            "diagnostic_population_n": n_samples,
            "diagnostic_sample_sha256": sample_digest,
        })

    return pd.DataFrame(results, columns=["k", "inertia", "silhouette_score",
                                         "davies_bouldin_score", "min_cluster_share", "max_cluster_share", "seed_stability_ari",
                                         "diagnostic_sample_n", "diagnostic_population_n", "diagnostic_sample_sha256"])


def execute_rq2_clustering(
    profile_df: pd.DataFrame,
    outcome_df: pd.DataFrame,
    n_clusters: int,
    output_dir: Path,
    scaler_type: str = "standard",
    random_state: int = 42,
    device: str = 'cpu',
    c2_max_profiles: Optional[int] = None,
    log_transform_features: Optional[List[str]] = None,
    experiments: Optional[Dict[str, bool]] = None,
    timing_exclusion_features: Optional[List[str]] = None,
    sensitivity_scalers: Optional[List[str]] = None,
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
    experiments = experiments or {}
    if experiments.get("c1_main_clustering", True) is not True:
        raise ValueError("C1 main clustering is mandatory and cannot be disabled")
    X_scaled, imputer, scaler, feature_cols = fit_clustering_pipeline(
        profile_df, scaler_type, log_transform_features)
    if n_clusters < 2:
        raise ValueError("n_clusters must be at least 2")
    if len(X_scaled) < n_clusters or len(np.unique(X_scaled, axis=0)) < n_clusters:
        centers = pd.DataFrame(columns=["cluster_label", *feature_cols, "profile_count", "profile_percentage", "behavioral_name"])
        outcomes = pd.DataFrame(columns=["cluster_label", "n_players", "mean_survival", "median_survival",
                                         "mean_placement", "median_placement", "win_rate",
                                         "survival_valid_players", "placement_valid_players", "win_rate_valid_players",
                                         "survival_valid_matches", "placement_valid_matches", "win_rate_valid_matches"])
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

    # 3. C2 Hierarchical validation. No hidden research threshold: an optional
    # cap must come from config after a resource audit; otherwise use all rows.
    c2_enabled = experiments.get("c2_hierarchical_validation", True)
    if c2_enabled and c2_max_profiles is not None and (type(c2_max_profiles) is not int or c2_max_profiles < n_clusters):
        raise ValueError("c2_max_profiles must be null or an integer >= n_clusters")
    subset_size = min(c2_max_profiles or len(X_scaled), len(X_scaled)) if c2_enabled else 0
    if not c2_enabled:
        sub_indices = np.array([], dtype=np.int64)
        c2_sampling_rule, c2_ari, c2_status, c2_reason = "not_run", np.nan, "skipped", "disabled_by_config"
    elif subset_size == len(X_scaled):
        sub_indices = np.arange(len(X_scaled), dtype=np.int64)
        c2_sampling_rule, c2_status, c2_reason = "full_eligible", "completed", "full_eligible_supporting_comparison"
    else:
        rng = np.random.RandomState(random_state)
        sub_indices = np.sort(rng.choice(len(X_scaled), size=subset_size, replace=False))
        c2_sampling_rule, c2_status, c2_reason = "uniform_without_replacement_configured_cap", "completed", "configured_resource_cap"
    if c2_enabled:
        agg = AgglomerativeClustering(n_clusters=n_clusters, linkage="ward")
        agg_labels = agg.fit_predict(X_scaled[sub_indices])
        c2_ari = adjusted_rand_score(labels[sub_indices], agg_labels)
    np.save(output_dir / "c2_sample_indices.npy", sub_indices)
    c2_sample_digest = hashlib.sha256(sub_indices.tobytes()).hexdigest()

    # 4. C3 changes only the representation by adding games_played. Core
    # values are imputed once, then the same scaler family is fitted once.
    c3_enabled = experiments.get("c3_games_played_sensitivity", True)
    core_values = _profile_values(profile_df, feature_cols, log_transform_features)
    core_imputed = imputer.transform(core_values)
    games_values = profile_df[["games_played"]].replace([np.inf, -np.inf], np.nan).to_numpy(dtype=float)
    games_imputed = SimpleImputer(strategy="median").fit_transform(games_values)
    X_c3_raw = np.column_stack([core_imputed, games_imputed])
    if c3_enabled:
        scaler_c3 = StandardScaler() if scaler_type == "standard" else RobustScaler()
        X_c3_scaled = scaler_c3.fit_transform(X_c3_raw)
        km_c3 = make_kmeans(device, n_clusters=n_clusters, random_state=random_state, n_init=10)
        c3_labels = km_c3.fit_predict(X_c3_scaled)
        c3_ari, c3_status, c3_reason = adjusted_rand_score(labels, c3_labels), "completed", "games_played_added_only"
    else:
        c3_ari, c3_status, c3_reason = np.nan, "skipped", "disabled_by_config"

    # Stability across random seeds
    km_seed = make_kmeans(device, n_clusters=n_clusters, random_state=random_state + 100, n_init=10)
    seed_labels = km_seed.fit_predict(X_scaled)
    seed_ari = adjusted_rand_score(labels, seed_labels)

    robustness_records = [
        {"comparison": "C1_Main_KMeans", "metric": "fit_status", "value": 1.0,
         "n_sample": len(labels), "population_size": len(labels), "seed": random_state,
         "sampling_rule": "full_eligible", "sample_identity_sha256": None,
         "scope": "main_descriptive", "status": "completed", "reason": "full_eligible_kmeans"},
        {"comparison": "C2_Hierarchical_vs_KMeans", "metric": "Adjusted_Rand_Index", "value": float(c2_ari),
         "n_sample": subset_size, "population_size": len(X_scaled), "seed": random_state,
         "sampling_rule": c2_sampling_rule, "sample_identity_sha256": c2_sample_digest,
         "scope": "supporting_validation", "status": c2_status, "reason": c2_reason},
        {"comparison": "C3_Games_Played_Sensitivity", "metric": "Adjusted_Rand_Index", "value": float(c3_ari),
         "n_sample": len(labels), "population_size": len(X_scaled), "seed": random_state,
         "sampling_rule": "full_eligible", "sample_identity_sha256": None,
         "scope": f"supporting_sensitivity_{scaler_type}", "status": c3_status, "reason": c3_reason},
        {"comparison": "Seed_Stability", "metric": "Adjusted_Rand_Index", "value": float(seed_ari),
         "n_sample": len(labels), "population_size": len(X_scaled), "seed": random_state + 100,
         "sampling_rule": "full_eligible", "sample_identity_sha256": None,
         "scope": "supporting_stability", "status": "completed", "reason": "alternate_seed_same_profiles"},
    ]

    timing_features = timing_exclusion_features or []
    if timing_features:
        unknown = sorted(set(timing_features) - set(feature_cols))
        if unknown:
            raise ValueError(f"Unknown timing sensitivity features: {unknown}")
        reduced = [c for c in feature_cols if c not in timing_features]
        X_timing, _, _, _ = fit_clustering_pipeline(profile_df[reduced], scaler_type,
                                                     [c for c in (log_transform_features or []) if c in reduced])
        timing_labels = make_kmeans(device, n_clusters=n_clusters, random_state=random_state, n_init=10).fit_predict(X_timing)
        robustness_records.append({"comparison": "D01_Timing_Exclusion_Sensitivity", "metric": "Adjusted_Rand_Index",
                                   "value": float(adjusted_rand_score(labels, timing_labels)), "n_sample": len(labels),
                                   "population_size": len(labels), "seed": random_state, "sampling_rule": "full_eligible",
                                   "sample_identity_sha256": None, "scope": "supporting_sensitivity",
                                   "status": "completed", "reason": "configured_evidence"})
    else:
        robustness_records.append({"comparison": "D01_Timing_Exclusion_Sensitivity", "metric": "Adjusted_Rand_Index",
                                   "value": np.nan, "n_sample": 0, "population_size": len(labels), "seed": random_state,
                                   "sampling_rule": "not_run", "sample_identity_sha256": None,
                                   "scope": "supporting_sensitivity", "status": "skipped", "reason": "no_evidence_configured"})

    for sensitivity_scaler in sensitivity_scalers or []:
        if sensitivity_scaler == scaler_type or sensitivity_scaler not in ("standard", "robust"):
            raise ValueError("sensitivity_scalers must contain the alternate supported scaler")
        X_alt = prepare_clustering_matrix(profile_df, sensitivity_scaler, log_transform_features)
        alt_labels = make_kmeans(device, n_clusters=n_clusters, random_state=random_state, n_init=10).fit_predict(X_alt)
        robustness_records.append({"comparison": f"Scaler_Sensitivity_{sensitivity_scaler}",
                                   "metric": "Adjusted_Rand_Index", "value": float(adjusted_rand_score(labels, alt_labels)),
                                   "n_sample": len(labels), "population_size": len(labels), "seed": random_state,
                                   "sampling_rule": "full_eligible", "sample_identity_sha256": None,
                                   "scope": "supporting_sensitivity", "status": "completed", "reason": "configured_evidence"})
    robustness_df = pd.DataFrame(robustness_records)

    # 5. C5 Outcome comparison (strictly descriptive post-hoc!)
    c5_enabled = experiments.get("c5_outcome_comparison", True)
    c5_table = outcome_df.groupby("cluster_label").agg(
        n_players=("player_name", "count"),
        survival_valid_players=("mean_survive_time", "count"),
        placement_valid_players=("mean_normalized_placement", "count"),
        win_rate_valid_players=("win_rate", "count"),
        survival_valid_matches=("mean_survive_time_valid_matches", "sum"),
        placement_valid_matches=("mean_normalized_placement_valid_matches", "sum"),
        win_rate_valid_matches=("win_rate_valid_matches", "sum"),
        mean_survival=("mean_survive_time", "mean"),
        median_survival=("mean_survive_time", "median"),
        mean_placement=("mean_normalized_placement", "mean"),
        median_placement=("mean_normalized_placement", "median"),
        win_rate=("win_rate", "mean"),
    ).reset_index()
    c5_table["behavioral_name"] = c5_table["cluster_label"].map(behavioral_names)
    if not c5_enabled:
        c5_table = c5_table.iloc[:0]
    robustness_df.loc[len(robustness_df)] = {
        "comparison": "C5_Outcome_Comparison", "metric": "descriptive_status", "value": 1.0 if c5_enabled else np.nan,
        "n_sample": len(outcome_df) if c5_enabled else 0, "population_size": len(outcome_df), "seed": random_state,
        "sampling_rule": "posthoc_locked_assignments" if c5_enabled else "not_run", "sample_identity_sha256": None,
        "scope": "posthoc_descriptive", "status": "completed" if c5_enabled else "skipped",
        "reason": "posthoc_locked_assignments" if c5_enabled else "disabled_by_config",
    }
    atomic_write_csv(output_dir / "clustering_robustness.csv", robustness_df)
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
        "log_transform_features": log_transform_features or [],
        "algorithm": "kmeans",
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
