# Phụ lục: Truy vết yêu cầu nghiên cứu PUBG

Cập nhật: 29/09/2026.

Nguồn nghiên cứu: [PUBG_RESEARCH_SPEC.md](../../PUBG_RESEARCH_SPEC.md), phiên bản 3.0.
Nguồn kế hoạch và tiến độ duy nhất: [PUBG_IMPLEMENTATION_PLAN.md](../../PUBG_IMPLEMENTATION_PLAN.md).

Bảng ánh xạ đầy đủ yêu cầu cũ W00-W13 và các phần bổ sung sang giai đoạn mới nằm tại [Truy vết yêu cầu](../../PUBG_IMPLEMENTATION_PLAN.md#traceability). Phụ lục này không duy trì checklist song song.

| Phạm vi | Vị trí thực hiện | Bằng chứng chính |
|---|---|---|
| Kiểm kê, hợp đồng và hạ tầng | Giai đoạn 0-1; INV/INF | Inventory, config/registry, checkpoint/cohort tests |
| Notebook 00-06 | Giai đoạn 2-8; NB00-NB06 | Môi trường, ingest/DQ/features/timing/EDA/RQ1 |
| Notebook 07-10 | Giai đoạn 9-12; NB07-NB10 | C1-C5, lịch sử, S/P/T/ABL, predictions/metrics/CI |
| Notebook 11-12 | Giai đoạn 13-14; NB11/NB12 | G5, locked release và summary 12 phần |
| Kiểm thử và tài liệu | Giai đoạn 15; QA | Synthetic/integration, README, audit G0 |
| Chạy thật và bàn giao | Giai đoạn 16; RUN | Full-data/GPU/Drive evidence, notebook output và resume |

Một công việc chỉ được tích sau khi có bằng chứng theo [quy tắc theo dõi](../../PUBG_IMPLEMENTATION_PLAN.md#tracking-rules). Dấu tích lịch sử được giữ trong bản lưu kế hoạch; không tự coi chúng là nghiệm thu hiện tại. Nhật ký thay đổi tiếp tục được ghi nối tiếp trong CHANGELOG_FIXES.md.
