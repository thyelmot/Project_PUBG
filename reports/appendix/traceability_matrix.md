# Phụ lục: Ma trận truy vết yêu cầu (Traceability Matrix)

**Ngày lập:** 24/09/2026  
**Căn cứ:** [PUBG_RESEARCH_SPEC.md](../../../PUBG_RESEARCH_SPEC.md) v3.0, [PUBG_IMPLEMENTATION_PLAN.md](../../../PUBG_IMPLEMENTATION_PLAN.md) §14.3.  

Tài liệu này xác nhận mối quan hệ 1-1 giữa các yêu cầu trong Đặc tả nghiên cứu v3.0, các gói công việc (Work Packages W00–W13) và các phép kiểm tra kiểm chứng tương ứng.

---

## Bảng ma trận truy vết

| Cụm yêu cầu đặc tả v3.0 | Gói triển khai | Artifacts & Modules chính | Tiêu chí kiểm chứng chính |
|---|---|---|---|
| **§2–8: RQ, Dataset, Targets, Modes** | W00, W02–W04 | `configs/{data,schema,preprocessing}.yaml`, `src/data/schema.py`, `src/features/placement.py` | Schema contract pass, đơn vị chuẩn hóa, mode mapping (Solo/Duo/Squad, TPP/FPP), công thức target chính xác |
| **§9–18: Data grain, Features, Combat Timing, Profiles, History** | W03–W05, W08–W09 | `src/features/{combat,movement,support,combat_timing,profiles,historical}.py` | Hạt dữ liệu (grain) chuẩn xác, xử lý mẫu số 0 ra NaN, reduce multi-chunk chính xác, không rò rỉ tương lai |
| **§19–24: Clustering, Prediction, Leakage, Splits, Feature Selection** | W07–W11 | `src/features/registry.py`, `src/models/splits.py`, `src/models/{baselines,linear,training}.py` | Không target rò rỉ vào feature sets, cùng trận đấu nằm cùng split, imputer/scaler chỉ fit trên tập train |
| **§25–30: EDA 8 pha, Chart Catalog, DQ, Identity, RQ1 Analysis** | W03, W05–W07 | `src/analysis/{eda,correlation,mode_analysis,rq1}.py`, `configs/eda.yaml` | Đủ 8 pha EDA, danh mục biểu đồ A01–I03, bảng tương quan Pearson/Spearman theo task allowlist |
| **§31–36: Experiment Matrix (C/S/P/T/ABL), Metrics, Protocol** | W08–W11 | `src/evaluation/{metrics,bootstrap,ablation,error_analysis}.py`, `configs/rq3.yaml` | Đủ các thí nghiệm C1–C5, S1, S2, P1, P2, P3, T0, T1, Ablation; MAE/RMSE/R² đa tầng, paired bootstrap |
| **§37–49: Cloud, Storage, Scaling, Checkpoint, Resume, Logging** | W00–W02, W10–W12 | `src/data/{checkpoints,io}.py`, `src/utils/{logging,hashing,runtime}.py` | Signature xác định phụ thuộc, ghi staging trước khi commit manifest, resume sau crash không nhân bản |
| **§50–57: Config, Reproducibility, Manifests, Reports** | W00–W01, W12–W13 | `configs/*.yaml`, `src/evaluation/finalize.py`, `artifacts/manifests/` | 10 file config với null cho data-dependent params, run metadata, final results manifest, figure manifest |
| **§58–63: 13 Notebooks, Modules, README** | W00–W13 | `notebooks/00_setup.ipynb` đến `12_final_results_summary.ipynb`, `README.md` | Notebook chỉ điều phối gọi `src/`, tuân thủ precondition gates, hướng dẫn khắc phục sự cố rõ ràng |
| **§64–70: Tests, TBD Gates, Outliers, Model Selection** | W03, W06, W10, W13 | `tests/`, `tests/test_*.py` | Bộ synthetic unit test bao phủ toàn bộ invariant quan trọng; fail-fast khi gặp tham số null chưa chốt |
| **§71–79: Report, Limitations, Literature, Privacy, Code Quality** | W00, W07–W13 | `reports/appendix/literature_mapping.md`, `reports/tables/`, code comments | Không dump danh sách tên người chơi thật, ghi rõ giới hạn hồi quy quan sát, không suy diễn quan hệ nhân quả |
| **§80–89: Definitions, Audit, Final Canonical Workflow** | W12–W13 | `Project_PUBG/README.md`, `PUBG_IMPLEMENTATION_PLAN.md` | Tách biệt ranh giới DoD code-ready và DoD full-run; 15 câu hỏi audit đều đạt YES hoặc giải trình rõ |
