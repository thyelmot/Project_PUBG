"""Các mặc định chung; đường dẫn không phụ thuộc thư mục chạy lệnh."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = ROOT / "data" / "raw"
INTERIM_DIR = ROOT / "data" / "interim"
PROCESSED_DIR = ROOT / "data" / "processed"
ARTIFACTS_DIR = ROOT / "artifacts"
REPORTS_DIR = ROOT / "reports"
SEED = 42
CHUNK_SIZE = 100_000
SAMPLE_MATCHES = 50_000
MAX_TRAIN_ROWS = 1_000_000
TRAIN_FRACTION = 0.70
VALIDATION_FRACTION = 0.15
TEST_FRACTION = 0.15
MIN_CLASS_FRACTION = 0.01
MAX_TIME_SECONDS = 2700
MAP_SIZE = 800_000
COORDINATE_UNITS_PER_METER = 100

# Data contract and feature sets.
RAW_COLUMNS = (
    "killed_by", "killer_name", "killer_placement", "killer_position_x",
    "killer_position_y", "map", "match_id", "time", "victim_name",
    "victim_placement", "victim_position_x", "victim_position_y",
)
TARGET = "weapon_group"
GROUP = "match_id"
FORBIDDEN_FEATURES = ("killed_by", "cause_for_audit", TARGET, GROUP, "killer_name", "victim_name")
DISTANCE_FEATURES = ("kill_distance_m",)
CONTEXT_FEATURES = ("time", "time_phase", "map")
POSITION_FEATURES = (
    "killer_x_norm", "killer_y_norm", "victim_x_norm", "victim_y_norm",
    "killer_center_dist", "victim_center_dist",
)
# Chỉ bật trong thí nghiệm riêng sau khi xác minh thời điểm biết thứ hạng.
PLACEMENT_FEATURES = ("killer_placement", "victim_placement", "placement_gap")
HISTORY_FEATURES = (
    "has_prior_kill", "prior_kills_in_match", "last_weapon_group",
    "last_kill_distance_m", "time_since_last_kill", "dominant_prior_weapon",
)
FEATURE_SETS = {
    "distance": DISTANCE_FEATURES,
    "context": DISTANCE_FEATURES + ("time",),
    "no_position": DISTANCE_FEATURES + ("log_kill_distance",) + CONTEXT_FEATURES,
    "full": DISTANCE_FEATURES + ("log_kill_distance",) + CONTEXT_FEATURES + POSITION_FEATURES,
}
FEATURE_SETS['loadout_history'] = FEATURE_SETS['full'] + HISTORY_FEATURES
