# Notebook 07: per_mode, quyết định và bàn giao
Cập nhật 03/10/2026. Đặc tả/kế hoạch ưu tiên; chỉ code/fixture đã kiểm, chưa full-data/Drive/GPU thật.

## I. Trước khi chạy
Đồng bộ source/config/notebook bằng đúng file ID/version rồi restart; không chỉ upload ipynb. Giữ storage drive, root /content/drive/MyDrive/PUBG_Project/Project_PUBG, require-existing=True, batch50000, per_mode, device=cuda. Một người ghi mỗi stage. Cần checkpoint04/05 tương thích, player_match_features, split và mode_analysis.json khớp source/split/scope. Mapping mode chưa verified không được suy từ camera perspective.

## II. Chạy lần lượt
1. Storage/bootstrap/init: bảng provenance/config/resource; GPU thiếu phải dừng, không CPU fallback.
2. Profiles development từ train/validation: giữ structural NaN, valid counts/active denominators, std ddof=1/singleton; outcomes tách riêng, không input clustering.
3. Retention và stability cho min_games candidates; chọn ngưỡng bằng reliability/coverage/resource, không survival/placement hoặc test score.
4. Diagnostics K cùng transform policy C1: inertia/silhouette/DB/sizes/seed ARI, sample n/seed/rule/digest khi có; K null hướng dẫn và dừng, không K4.
5. Chốt n_clusters_by_mode/selection_reason sau diagnostics. Receipt kiểm source/profile/split/evidence/code/settings hashes; sửa threshold/backend/scaler cần diagnostics/decision mới.
6. Sau khóa fit full eligible descriptive profiles từng mode, không heldout generalization; lưu imputer/scaler/model/feature order để reload/assign không refit.
7. Đọc centers/sizes/C2-C4/coverage/stability, rồi C5 outcomes/valid N sau assignments. Cluster ID cục bộ từng mode, đặt tên hành vi không tên thắng/thua.
8. Đọc checkpoint/handover, save notebook có output và thay đúng Drive/local; không numbered copies.

## III. Đầu ra
Paths tương đối root, đối chiếu paths resolved trong notebook:
- data/processed/player_profile_{features,outcomes}_development.parquet: scope chọn quyết định.
- data/processed/player_profile_{features,outcomes}.parquet: full eligible descriptive sau khóa.
- reports/tables/rq2_retention.csv, k_diagnostics.csv, rq2_min_games_stability.csv: diagnostics, không final score.
- reports/tables/rq2/<mode>/: cluster_assignments, cluster_profile, cluster_centers_standardized, clustering_robustness, c4_min_games_sensitivity, c5_outcome_comparison CSV.
- artifacts/models/rq2/<mode>/: fitted artifacts; đường dẫn thật đọc checkpoint, không đoán theo tên.
- artifacts/manifests/rq2_diagnostics.json, rq2_decisions.json và figure catalog; artifacts/checkpoints/checkpoint_manifest.json.
- Hình retention/K/centers/sizes/sensitivity/outcomes inline và PNG, source/N/scope/caption đọc cùng manifest.

## IV. Giới hạn và tiếp tục
C1 đúng14features Design3, không games_played/mean_damage_per_kill/outcomes. C3 chỉ thêm games_played, giữ scaling policy; main StandardScaler, robust/log là sensitivity có evidence. C2 Ward supporting full/subset theo resource receipt, không cap3000 ngầm; silhouette sampling cũng explicit, không mặc định10000 nghiên cứu.
KMeans fit đủ eligible, chưa MiniBatch recipe; không estimator fallback. D01 phase ratios dùng duration proxy hậu trận, không hoàn toàn độc lập outcome; sensitivity không chọn bằng outcome.
Compatible completed mode có thể reuse, corrupt/stale chỉ xử lý nhánh liên quan; profile matrices vẫn cần RAM. Quota/OOM dừng giữ committed checkpoint và báo lỗi; resume runtime được phép qua shortcut cùng root, không bypass giới hạn dịch vụ.
NB11 chọn đúng completed artifacts/receipts; NB12 chỉ đọc release snapshot cụ thể. Null/K/history/G4/units production vẫn chờ evidence, không sao quyết định fixture.
