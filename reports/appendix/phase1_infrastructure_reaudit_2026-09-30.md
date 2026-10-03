# Tai nghiem thu Giai doan 1: ha tang dung chung

Ngay nghiem thu: 2026-09-30

Pham vi: INF-01 den INF-29. Khong chay du lieu that, khong chay notebook tong hop va khong chot cac quyet dinh can bang chung du lieu.

## Ket qua

| ID | Ket qua va bang chung chinh |
|---|---|
| INF-01 | Dung lai `publish_file`, checksum va retry trong `src/data/io.py`; khong them co che publish thu hai. |
| INF-02 | `CheckpointManager.commit` luu path, SHA-256, byte size, row count va schema theo dinh dang. |
| INF-03 | Batch ingest ghi `.partial`, dong Parquet, publish, doc lai kiem tra roi moi commit. |
| INF-04 | `publish_file` xu ly mounted Drive bang upload tam, kiem tra lai va fallback copy; khong dua vao atomic rename cua local disk. |
| INF-05 | Loi publish giu ban canonical cu va recovery copy; manifest co snapshot lich su cung recovery canonical. |
| INF-06 | Output, handover va figure catalog dung ten canonical, thay hang cua stage thay vi sinh ban `(1)`, `(2)`. |
| INF-07 | Manifest cu duoc snapshot truoc ghi de; final manifest hop le duoc khoa thanh ban timestamp truoc khi thay. |
| INF-08 | Resume doi status completed, chu ky khop, artifact ton tai, khac 0 byte va checksum/metadata khop. |
| INF-09 | Commit khong co artifact hoac artifact 0 byte bi tu choi. |
| INF-10 | Co `write_handover` va `write_figure_metadata`; generator goi hai ham sau moi notebook 01-11. |
| INF-11 | `writer_id` khoa mot nguoi ghi; takeover phai bat ro; handover luu path, status, version, error, next step va thoi gian. |
| INF-12 | Row ID dung key co length-prefix, khong dung index; null va duplicate bi chan. |
| INF-13 | `summarize_cohort` luu eligibility, exclusions va counts rows/matches/teams/players theo split/mode. |
| INF-14 | Cohort so sanh dung cung `valid_placement` truoc fit; helper kiem tra row ID, target va split. Ablation dung cung input cohort cho moi nhanh. |
| INF-15 | Canonical registry co P1/P2/P3/S1/S2/T0/T1 va baseline mean/median. |
| INF-16 | Registry co run/dataset/feature/pipeline/config versions, counts, chronology, scope, artifact paths va signatures. |
| INF-17 | Notebook signature gom configs, dependency signatures/checksums, toan bo source, cohort, split, registry, feature set va backend. |
| INF-18 | RQ2 signature bam workflow, clustering helper va compute helper; doi helper lam checkpoint khong tuong thich. |
| INF-19 | Lifecycle co planned/running/completed/failed/resource_limited/blocked/stale; metric cua trang thai chua completed la null. |
| INF-20 | DAG tach profile, diagnostics, per-mode clustering, historical, prediction, comparison va finalization; per-experiment lifecycle nam trong registry. |
| INF-21 | Notebook 08-11 commit artifact tuong minh; wrapper `commit({})` da bi loai. |
| INF-22 | RQ2 resume doc lap diagnostics va tung mode; stage tong chi completed sau khi moi artifact mode hop le. |
| INF-23 | Grade C hoan tat feasibility audit nhung S2/P3 ghi blocked, khong co metric gia va khong duoc goi completed. |
| INF-24 | Giu cau truc du an hien huu; `raw_root` cau hinh duoc, khong sao chep raw chi de doi cay thu muc. |
| INF-25 | Feature status ho tro candidate/confirmed/optional/excluded; decision log, traceability va ignore secrets/temp/large outputs da duoc kiem tra. |
| INF-26 | Shard ID dua tren source hash; ingest manifest co running/completed; lineage on dinh theo source file/source row; stale lan den RQ2 per-mode. |
| INF-27 | Structured stage log co du truong bat buoc; commit dong bo canonical, recovery va checksum de restore kiem chung. |
| INF-28 | Row ID tranh collision ky tu phan cach; dong thieu ten dung `source_file/source_row`, khong gop UNKNOWN. |
| INF-29 | Bootstrap danh gia doi hai tap row ID bang nhau; khong lay giao nho hon de che dong mat. |

## Kiem thu

- `python -m py_compile` cho cac module ha tang da sua: dat.
- `python -m unittest discover -s tests -p "test_phase1_infrastructure_contract.py" -v`: 5/5 dat.
- `python -m unittest discover -s tests -v`: 161 test, dat 158, bo qua 3 test co dieu kien; khong co loi.
- Ba test bo qua: CUDA/cuML that, All-in-One va chmod read-only tren Windows.
- Notebook 00-12 va All-in-One chi duoc tai tao tu generator; moi code cell van co `execution_count = null` va khong co output.

## Thay doi co chu dich nhung chua chot bang du lieu

- `mode_strategy` giu `per_mode` theo quyet dinh nguoi dung.
- K cua Solo/Duo/Squad giu `null` den khi Notebook 07 tao diagnostics tu du lieu that.
- Ty le split RQ3 giu `null` den gate du lieu tuong ung.
- Khong fallback am tham tu GPU sang estimator khac khi thieu tai nguyen.

## Anh huong nghien cuu

Khong doi cau hoi nghien cuu, cohort khoa hoc, feature contract, target, estimator hay metric. Thay doi chi lam chat tinh toan ven, kha nang resume, ban giao nhom va kha nang tai lap.

## Diem dung

Giai doan 1 hoan tat o muc code, fixture va kiem thu synthetic/static. Chua bat dau Giai doan 2 va chua chay notebook du lieu that.