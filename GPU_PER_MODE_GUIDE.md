# Per-mode and GPU handoff

## What changed

Notebook 07 fits separate KMeans models/scalers for Solo, Duo and Squad. K remains
an explicit per-mode choice after diagnostics; empty n_clusters_by_mode is a gate,
not a default. The user's per_mode choice is recorded; the mode EDA file from 05
is still required. Verify party_size_mapping if team_size_mode is absent.

Notebook 07 KMeans (including K diagnostics, seed stability, C3 and C4), notebook
09 P1/P2 ordinary least squares, and notebook 10 paired linear ablations now use
cuML on GPU when device: cuda. C2 Ward hierarchical clustering, preprocessing,
DuckDB and evaluation remain on CPU. Unused tree wrappers were not substituted
for the actual estimators. GPU/CPU results need not be bitwise identical: different
initialization/numerical implementations can change labels/coefficients. Record
the backend and rerun diagnostics when switching it. No sampling is introduced.

## Files to update on Drive

Use Manage versions / Upload new version for existing files, preserving the file
ID and exact original name. New files are uploaded once. A numbered copy of a .py
file is not the module Python imports. Update these paths relative to Project_PUBG:

- src/models/compute.py (new)
- src/models/linear.py
- src/models/training.py
- src/analysis/clustering.py
- src/analysis/rq2_workflow.py
- src/evaluation/ablation.py
- src/evaluation/finalize.py
- src/utils/config.py
- src/utils/generate_notebooks.py
- configs/rq2.yaml
- configs/rq3.yaml
- notebooks/07_rq2_clustering.ipynb
- notebooks/09_rq3_prediction.ipynb
- notebooks/10_ablation_error_analysis.ipynb
- notebooks/11_finalize_results.ipynb
- notebooks/12_final_results_summary.ipynb
- tests/test_gpu_compute.py (for the real GPU smoke check)

Preserve documented data-specific choices when merging config. The required
storage settings are unchanged: drive, existing shared project, batch 50000,
/content/drive/MyDrive/PUBG_Project/Project_PUBG.

## Colab

1. Select Runtime / Change runtime type / T4 GPU for 07, 09 and 10. Restart the
   session after updating source files. Metadata requests T4 but cannot allocate
   GPU on behalf of Colab or bypass quotas.
2. Run storage, bootstrap and initialization. With missing cuML, initialization
   checks NVIDIA availability before installing cuml-cu12==26.8.*. This path targets
   Linux/Colab with CUDA 12; it does not install GPU libraries on your Windows PC.
   Restart if Colab requests it after installation. Incompatible CUDA/Python/library
   environments stop with an error; consult the official installation guide below.
3. The printed Training backend must show device cuda, backend cuml and the GPU
   name. A CPU runtime never silently substitutes CPU when cuda was requested.
4. Run the GPU check once in a Colab cell after bootstrap (no real dataset used):

```python
import os, subprocess, sys
os.environ['PUBG_TEST_GPU'] = '1'
subprocess.run([sys.executable, '-m', 'unittest', 'discover', '-s', 'tests',
                '-p', 'test_gpu_compute.py', '-v'], check=True)
```

5. In 07 inspect retention, set minimum_games_threshold, run diagnostics, then set
   n_clusters_by_mode to a K for each observed mode and record selection_reason.
   Choose K separately per mode, never using outcomes. After final clustering,
   11 validates the current configuration and artifacts; 12 only reads the locked
   tables. Neither reporting notebook requires GPU.
6. If GPU quota is exhausted, stop and switch account; mount the same shared
   project through its shortcut. GPU out-of-memory is a separate issue: stop and
   reassess VRAM/batch strategy, not reduce the cohort silently. Pandas/model
   matrices still use host RAM. Interrupted fits restart; completed profile
   checkpoints are reusable. Do not assume a T4 makes every step faster.

## Outputs and verification

Per-mode results live in reports/tables/rq2/<Solo|Duo|Squad>/ with one model's
cluster labels per directory. rq2_decisions.json records per-mode run IDs and
compute backend/version/device. Prediction metadata is experiments/compute_<run>.json
under artifacts; saved predictions also contain compute_device. Ablation records
the device in its result table. Notebook 11 uses only completed matching RQ2
artifacts and locks nested table paths; old overall RQ2 result tables are excluded.
Notebook 12 verifies checksums, including metadata, and labels each mode separately.

Local CPU tests cover routing, failure gates and report selection. The real-GPU
test is skipped unless explicitly enabled with PUBG_TEST_GPU=1. No real Colab run,
speedup or full-data VRAM fit has been verified in this local implementation.

Official references checked for the implementation:
- https://docs.nvidia.com/cuml/26.08/api/generated/cuml.cluster.KMeans/
- https://docs.rapids.ai/api/cuml/stable/api/generated/cuml.linear_model.linearregression/
- https://docs.nvidia.com/datascience/deployment/latest/platforms/colab/
- https://docs.nvidia.com/datascience/install/
