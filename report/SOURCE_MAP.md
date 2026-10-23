# Nguồn báo cáo hoàn thiện

Bảng lấy từ CSV đầy đủ, SHA256 khớp handoff. Hình cũ vẫn giữ ánh xạ notebook tại evidence/index.json.

- {"table": "inventory", "source": "evidence/full_results/source_inventory.csv", "selected_rows": 10, "columns": ["group", "file", "rows"]}
- {"table": "eda", "source": "evidence/full_results/eda_statistics.csv", "selected_rows": 7, "columns": ["feature", "mean", "median", "max", "missing"]}
- {"table": "correlation", "source": "evidence/full_results/rq1_relationships.csv", "selected_rows": 9, "columns": ["feature", "n", "pearson", "spearman"]}
- {"table": "correlation_modes", "source": "evidence/full_results/rq1_relationships.csv", "selected_rows": 4, "columns": ["mode", "n", "pearson", "spearman"]}
- {"table": "clusters", "source": "evidence/full_results/cluster_sizes.csv", "selected_rows": 9, "columns": ["mode", "cluster", "profiles", "share"]}
- {"table": "validation", "source": "evidence/full_results/model_metrics.csv", "selected_rows": 7, "columns": ["experiment", "n", "mae", "rmse", "r2"]}
- {"table": "test_survival", "source": "evidence/full_results/model_metrics.csv", "selected_rows": 3, "columns": ["experiment", "n", "mae", "rmse", "r2"]}
- {"table": "test_placement", "source": "evidence/full_results/model_metrics.csv", "selected_rows": 4, "columns": ["experiment", "n", "mae", "rmse", "r2"]}
- {"table": "timing", "source": "evidence/full_results/timing_comparison.csv", "selected_rows": 9, "columns": ["aggregation", "metric", "T0", "T1", "delta", "n"]}
- {"table": "errors", "source": "evidence/full_results/error_analysis.csv", "selected_rows": 6, "columns": ["experiment", "group", "n", "mae", "rmse", "r2"]}
- {"table": "error_regions", "source": "evidence/full_results/error_analysis.csv", "selected_rows": 3, "columns": ["group", "n", "mae", "rmse", "r2"]}
- {"table": "cohorts", "source": "evidence/full_results/model_cohorts.csv", "selected_rows": 6, "columns": ["task", "split", "rows", "matches"]}
- {"table": "retention", "source": "evidence/full_results/profile_retention.csv", "selected_rows": 3, "columns": ["mode", "total_profiles", "retained", "coverage", "median_games"]}
- {"table": "k_selected", "source": "evidence/full_results/k_diagnostics.csv", "selected_rows": 3, "columns": ["mode", "k", "profiles", "silhouette", "seed_ari", "min_cluster_share"]}
- {"table": "centers", "source": "evidence/full_results/cluster_centers.csv", "selected_rows": 9, "columns": ["mode", "cluster", "avg_kills", "avg_damage", "avg_walk", "avg_assists"]}
- {"table": "coefficients", "source": "evidence/full_results/coefficients.csv", "selected_rows": 7, "columns": ["feature", "coefficient"]}
- {"table": "feature_recipe", "source": "evidence/full_results/feature_dictionary.csv", "selected_rows": 19, "columns": ["feature", "S1_predictor", "P2_predictor", "T0_predictor"]}
- {"table": "coverage", "source": "evidence/full_results/coverage_summary.csv", "selected_rows": 4, "columns": ["timing_status", "n_rows", "percent"], "derived_from": "timing_coverage.csv: sum n_rows by status; percent of total"}
- {"figure": "placement_validation_test.png", "source": "evidence/full_results/model_metrics.csv"}
- {"figure": "k_stability.png", "source": "evidence/full_results/k_diagnostics.csv"}