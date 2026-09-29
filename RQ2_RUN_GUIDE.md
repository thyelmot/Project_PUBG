# Notebook 07: safe handoff after the 2026-09-28 fix

## Deployment

The local notebook is updated but NOT executed on real data. Updating only the
notebook on Drive is insufficient: an existing Drive project keeps its own src
and configs. Back up the corresponding Drive files, then copy these files from
this project to the SAME relative locations in the shared Drive project:

- src/analysis/rq2_workflow.py
- src/analysis/clustering.py
- src/features/profiles.py
- configs/rq2.yaml (preserve any real, documented team decisions)
- notebooks/07_rq2_clustering.ipynb

Restart the Colab session after updating source files. Do not run All-in-One.
Keep the four storage settings: drive; root
/content/drive/MyDrive/PUBG_Project/Project_PUBG; require existing project true;
batch rows 50000. Only one member writes at a time. The selected mode is now
per_mode and device is cuda. See GPU_PER_MODE_GUIDE.md for the updated source
deployment list and T4 setup. The CPU backend remains available only by explicit config.

## Run cells in order

1. Run storage, bootstrap and initialization. Notebook 04 data and notebook 05
   mode_analysis.json must already exist. Read mode_summary.csv and the mode EDA.
2. In configs/rq2.yaml, explicitly set mode_strategy and mode_decision_reason.
   Leave profile_level as auto, or set it consistently with the strategy.
   If team_size_mode is missing, verify the source party_size encoding and set
   party_size_mapping. Never treat match_mode (camera perspective) as team size.
3. Run the profiles cell. It uses DuckDB for all valid named-player rows, saves
   reduced profiles and separate outcomes, and writes rq2_retention.csv.
4. Choose a provisional minimum_games_threshold from retention. Run diagnostics
   for K, seed stability and threshold stability. Inspect k_diagnostics.csv and
   rq2_min_games_stability.csv. If the threshold changes, rerun diagnostics.
5. Record n_clusters (overall/player_mode) or n_clusters_by_mode (per_mode), and
   selection_reason. Do not select these using survival, placement or win rate.
6. Run the final cell. Only a successful run commits output checksums. Inspect
   results before saving/downloading the EXECUTED notebook to both notebook folders.
   This fix does not manufacture executed outputs or mark notebook 07 completed.

Missing research choices intentionally raise an explanatory error. They are not
silently replaced by min-games=5 or K=4. On quota exhaustion, stop, switch account,
mount the same shared folder via shortcut, and restart the cells in order.
Completed profile checkpoints are verified and reused; an interrupted aggregation
or clustering fit restarts that operation, not from the middle of its computation.

## Outputs relative to the shared project root

- data/processed/player_profile_features.parquet: behavioral inputs and counts.
- data/processed/player_profile_outcomes.parquet: isolated outcome summaries.
- reports/tables/rq2_retention.csv: retained players/profiles/rows by threshold.
- reports/tables/k_diagnostics.csv: K metrics and seed stability.
- reports/tables/rq2_min_games_stability.csv: ARI on common profile keys per K.
- reports/tables/cluster_profile.csv: raw behavioral means by cluster.
- reports/tables/cluster_assignments.csv: player/profile-to-cluster membership.
- reports/tables/cluster_centers_standardized.csv: standardized cluster centers.
- reports/tables/clustering_robustness.csv: C2, C3 and seed comparisons.
- reports/tables/c4_min_games_sensitivity.csv: threshold sensitivity for chosen K.
- reports/tables/c5_outcome_comparison.csv: descriptive post-clustering outcomes.
- artifacts/manifests/rq2_diagnostics.json and rq2_decisions.json: choice provenance.
- artifacts/checkpoints/checkpoint_manifest.json: verified artifact checkpoints.

For per_mode, the six final CSV files instead live under reports/tables/rq2/Solo,
Duo or Squad. Cluster labels are local to each mode. Updated notebooks 11/12
lock and read the completed per-mode artifacts by checkpoint and relative path.
Stale root-level final RQ2 tables from an overall run are excluded from the manifest.

## Scope and limitations

This is a descriptive full-eligible-profile KMeans workflow, not a held-out
generalization evaluation. Original behavioral formulas, ddof=1 and legacy ratio
fill-zero/early-combat denominator policies are preserved, not newly approved.
A development/validation protocol and missing-ratio semantics need separate
research decisions. No player-match sampling or estimator change was introduced.
Silhouette/DB use a declared fixed-seed diagnostic subset up to 10000; C2 up to
3000; KMeans fits all eligible profiles. Reduced profiles and clustering matrices
still need RAM. DuckDB limits/spills aggregation, but this is not a whole-process
RAM guarantee. Checksumming a large input on resume incurs disk/Drive reads.

No real-data run, peak-memory benchmark, Colab quota test or Drive synchronization
was performed in this local fix. Other notebooks and their saved outputs stay intact.
