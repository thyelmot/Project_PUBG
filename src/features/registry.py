from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Set

import pandas as pd

VALID_FEATURE_STATES = {"candidate", "confirmed", "optional", "excluded"}
CORE_TASKS = ["rq1_survival", "rq1_placement", "rq2", "s1", "p1", "p2", "t0", "t1", "ablation"]
PLACEMENT_TASKS = ["rq1_placement", "rq2", "p1", "p2", "t1", "ablation"]


@dataclass
class FeatureDefinition:
    name: str
    group: str
    source_columns: List[str]
    formula: str
    unit: str
    dtype: str
    missing_semantics: str
    status: str = "candidate"
    level: str = "player_match"
    depends_on: List[str] = field(default_factory=list)
    availability: str = "post_match"
    missing_indicator: bool = False
    aggregation_denominator: Optional[str] = None
    target_derived: bool = False
    description: str = ""
    allowed_tasks: List[str] = field(default_factory=list)
    allowed_targets: List[str] = field(default_factory=list)
    forbidden_targets: List[str] = field(default_factory=list)
    leakage_reason: str = ""
    requires_current_outcome: bool = False
    requires_survival: bool = False
    requires_placement: bool = False
    version: str = "v1"

    def __post_init__(self) -> None:
        if self.status not in VALID_FEATURE_STATES:
            raise ValueError(f"Invalid feature status: {self.status}")
        if not self.name or not self.formula or not self.source_columns:
            raise ValueError("Feature name, formula and source_columns are required")


class FeatureRegistry:
    """Canonical feature dictionary and leakage allowlist."""

    def __init__(self) -> None:
        self._registry: Dict[str, FeatureDefinition] = {}
        self._init_defaults()

    def register(self, feature: FeatureDefinition) -> None:
        self._registry[feature.name] = feature

    def get(self, name: str) -> Optional[FeatureDefinition]:
        return self._registry.get(name)

    def list_all(self) -> List[FeatureDefinition]:
        return list(self._registry.values())

    def _add(
        self, name: str, group: str, source_columns: List[str], formula: str,
        unit: str, dtype: str, missing_semantics: str, *,
        depends_on: Optional[List[str]] = None, denominator: Optional[str] = None,
        tasks: Optional[List[str]] = None, targets: Optional[List[str]] = None,
        forbidden: Optional[List[str]] = None, target_derived: bool = False,
        description: str = "", availability: str = "post_match",
        requires_current_outcome: bool = False, requires_survival: bool = False,
        requires_placement: bool = False,
    ) -> None:
        self.register(FeatureDefinition(
            name=name, group=group, source_columns=source_columns, formula=formula,
            unit=unit, dtype=dtype, missing_semantics=missing_semantics,
            status="confirmed", depends_on=depends_on or [], availability=availability,
            aggregation_denominator=denominator, target_derived=target_derived,
            description=description, allowed_tasks=tasks or [],
            allowed_targets=targets or [], forbidden_targets=forbidden or [],
            leakage_reason=(
                "Contains current-match survival information; forbidden for survival prediction and primary survival association."
                if "survival" in (forbidden or []) else ""
            ),
            requires_current_outcome=requires_current_outcome,
            requires_survival=requires_survival,
            requires_placement=requires_placement,
        ))

    def _init_defaults(self) -> None:
        from src.features.history_workflow import FEATURES
        self.register(FeatureDefinition(
            name="hist_kd", group="historical", source_columns=["past_kills", "past_verified_deaths"],
            formula="past_total_kills / past_verified_deaths", unit="ratio", dtype="float64",
            missing_semantics="Unknown death denominator or zero deaths: missing; no epsilon.",
            status="candidate", availability="pre_match", level="player_history",
            description="D06: death denominator unverified; excluded from confirmed historical inputs."))
        for key, (raw, mean, unit) in FEATURES.items():
            for name, formula, dtype, semantics in [
                (f"hist_{key}_count", f"strict_past_valid_count({raw})", "int64", "0 means no valid past values."),
                (mean, f"strict_past_sum({raw}) / strict_past_valid_count({raw})", "float64", "No valid past values: missing, not zero.")]:
                self.register(FeatureDefinition(name=name, group="historical", source_columns=[raw],
                    formula=formula, unit="count" if dtype=="int64" else unit, dtype=dtype,
                    missing_semantics=semantics, status="confirmed", level="player_history",
                    allowed_tasks=["s2", "p3"], allowed_targets=["survival", "placement"],
                    availability="strict_past_verified", aggregation_denominator=f"hist_{key}_count"))
        self.register(FeatureDefinition(name="hist_games_played", group="historical", source_columns=["match_id"],
            formula="count(strict_past_completed_matches)", unit="count", dtype="int64",
            missing_semantics="Cold start: 0", status="confirmed", availability="strict_past_verified",
            level="player_history", allowed_tasks=["s2","p3"], allowed_targets=["survival","placement"]))
        self._add("player_kills", "combat", ["player_kills"], "identity", "count", "int64",
                  "Data-error missing only; zero means no recorded kill.", tasks=CORE_TASKS,
                  targets=["survival", "placement"], description="Confirmed player kills.")
        self._add("player_dmg", "combat", ["player_dmg"], "identity", "damage points", "float64",
                  "Data-error missing only; zero means no recorded damage.", tasks=CORE_TASKS,
                  targets=["survival", "placement"], description="Damage inflicted.")
        self._add("damage_per_kill", "combat", ["player_dmg", "player_kills"],
                  "player_dmg / player_kills", "damage points per kill", "float64",
                  "Structural missing when player_kills = 0.", depends_on=["player_dmg", "player_kills"],
                  denominator="player_kills", tasks=CORE_TASKS, targets=["survival", "placement"],
                  description="Damage per recorded kill.")
        self._add("player_dist_walk", "movement", ["player_dist_walk"], "identity", "metres", "float64",
                  "Data-error missing only; zero means no recorded walking.", tasks=CORE_TASKS,
                  targets=["survival", "placement"], description="Distance walked.")
        self._add("player_dist_ride", "movement", ["player_dist_ride"], "identity", "metres", "float64",
                  "Data-error missing only; zero means no recorded riding.", tasks=CORE_TASKS,
                  targets=["survival", "placement"], description="Distance ridden.")
        self._add("total_distance", "movement", ["player_dist_walk", "player_dist_ride"],
                  "player_dist_walk + player_dist_ride", "metres", "float64",
                  "Missing if either required source distance is missing.",
                  depends_on=["player_dist_walk", "player_dist_ride"], tasks=CORE_TASKS,
                  targets=["survival", "placement"], description="Walk plus ride distance.")
        self._add("walk_ratio", "movement", ["player_dist_walk", "total_distance"],
                  "player_dist_walk / total_distance", "proportion [0,1]", "float64",
                  "Structural missing when total_distance = 0.", depends_on=["player_dist_walk", "total_distance"],
                  denominator="total_distance", tasks=CORE_TASKS, targets=["survival", "placement"],
                  description="Share of measured distance travelled on foot.")
        self._add("player_assists", "support", ["player_assists"], "identity", "count", "int64",
                  "Data-error missing only; zero means no recorded assist.", tasks=CORE_TASKS,
                  targets=["survival", "placement"], description="Credited assists.")
        self._add("player_dbno", "support", ["player_dbno"], "identity", "count", "int64",
                  "Data-error missing only; zero means no recorded DBNO.", tasks=CORE_TASKS,
                  targets=["survival", "placement"], description="Down-but-not-out events caused.")
        self._add("assist_ratio", "support", ["player_assists", "player_kills"],
                  "player_assists / (player_assists + player_kills)", "proportion [0,1]", "float64",
                  "Structural missing when player_assists + player_kills = 0.",
                  depends_on=["player_assists", "player_kills"],
                  denominator="player_assists + player_kills", tasks=CORE_TASKS,
                  targets=["survival", "placement"], description="Assist share of kills plus assists.")
        self._add("player_survive_time", "outcome", ["player_survive_time"], "identity", "seconds", "float64",
                  "Invalid or unavailable survival is excluded only from survival-target tasks.",
                  tasks=["target_s1", "target_s2", "p1"], targets=["survival"],
                  requires_current_outcome=True, description="Current-match survival duration.")
        self._add("normalized_placement", "outcome",
                  ["team_placement", "observed_team_count", "is_roster_complete"],
                  "1 - (team_placement - 1) / (observed_team_count - 1)", "score [0,1]", "float64",
                  "Missing when roster is incomplete, N_teams <= 1, or placement is outside [1,N_teams].",
                  depends_on=["team_placement", "observed_team_count"], denominator="observed_team_count - 1",
                  tasks=["target_p1", "target_p2", "target_p3"], targets=["placement"],
                  requires_current_outcome=True, requires_placement=True,
                  description="Roster-normalized team placement; 1 is best.")
        self._add("event_kill_count", "combat_timing_absolute", ["kill_match_stats"], "count(eligible credited-killer events)",
                  "count", "int64", "Structural zero when no eligible credited-killer event is matched.", tasks=CORE_TASKS,
                  targets=["survival", "placement"], description="Credited-killer event count; enemy eligibility is pending evidence.")
        self._add("first_kill_time", "combat_timing_absolute", ["event_time"], "min(event_time)",
                  "source time unit (pending verification)", "float64", "Structural missing when no eligible credited-killer event exists.",
                  tasks=CORE_TASKS, targets=["survival", "placement"], description="First valid kill time.")
        self._add("avg_kill_time", "combat_timing_absolute", ["event_time"], "sum(event_time) / event_kill_count",
                  "source time unit (pending verification)", "float64", "Structural missing when no eligible credited-killer event exists.",
                  denominator="event_kill_count", tasks=CORE_TASKS, targets=["survival", "placement"],
                  description="Mean valid kill time.")
        self._add("has_kill", "combat_timing_absolute", ["event_kill_count"], "event_kill_count > 0",
                  "boolean", "bool", "Never missing after event reconciliation.", depends_on=["event_kill_count"],
                  tasks=CORE_TASKS, targets=["survival", "placement"], description="Has an eligible credited-killer event; enemy eligibility is pending evidence.")
        for name, formula, description in (
            ("early_kills", "count(0 <= t < duration/3)", "Kills in the early phase."),
            ("mid_kills", "count(duration/3 <= t < 2*duration/3)", "Kills in the middle phase."),
            ("late_kills", "count(2*duration/3 <= t <= duration)", "Kills in the late phase."),
        ):
            self._add(name, "combat_timing_phase", ["event_time", "estimated_match_duration"], formula,
                      "count", "int64", "Missing when duration proxy is invalid or event is not phase-eligible.",
                      depends_on=["estimated_match_duration"], tasks=PLACEMENT_TASKS,
                      targets=["placement"], forbidden=["survival"], target_derived=True,
                      requires_survival=True, description=description)
        for name, numerator in (
            ("early_kill_ratio", "early_kills"),
            ("mid_kill_ratio", "mid_kills"),
            ("late_kill_ratio", "late_kills"),
        ):
            self._add(name, "combat_timing_phase", ["early_kills", "mid_kills", "late_kills"],
                      f"{numerator} / (early_kills + mid_kills + late_kills)",
                      "proportion [0,1]", "float64",
                      "Structural missing when phase-eligible kill count is zero.",
                      depends_on=["early_kills", "mid_kills", "late_kills"],
                      denominator="early_kills + mid_kills + late_kills",
                      tasks=PLACEMENT_TASKS, targets=["placement"], forbidden=["survival"],
                      target_derived=True, requires_survival=True,
                      description=f"{numerator} share of phase-eligible kills.")
        self._add("kills_per_minute", "diagnostic", ["player_kills", "player_survive_time"],
                  "player_kills / (player_survive_time / 60)", "kills per minute", "float64",
                  "Missing when survival <= 0.", depends_on=["player_kills", "player_survive_time"],
                  denominator="player_survive_time / 60", tasks=["diagnostic"], forbidden=["survival"],
                  target_derived=True, requires_survival=True, description="Diagnostic survival-derived rate.")
        self._add("damage_per_minute", "diagnostic", ["player_dmg", "player_survive_time"],
                  "player_dmg / (player_survive_time / 60)", "damage points per minute", "float64",
                  "Missing when survival <= 0.", depends_on=["player_dmg", "player_survive_time"],
                  denominator="player_survive_time / 60", tasks=["diagnostic"], forbidden=["survival"],
                  target_derived=True, requires_survival=True, description="Diagnostic survival-derived rate.")
        self._add("perspective_mode", "context", ["match_mode"], "verified mapping from match_mode",
                  "category", "string", "unknown when source label is absent or unrecognized.",
                  depends_on=["match_mode"], tasks=["context", "eda", "rq2", "rq3"],
                  availability="pre_match", description="TPP, FPP, or unknown.")
        self._add("team_size_mode", "context", ["party_size"],
                  "1=solo; 2=duo; verified 4=squad; otherwise unknown", "category", "string",
                  "unknown for missing or unverified party size.", depends_on=["party_size"],
                  tasks=["context", "eda", "rq2", "rq3"], availability="pre_match",
                  description="Verified team-size category.")

    def export_dictionary_dataframe(self) -> pd.DataFrame:
        return pd.DataFrame([{
            "feature_name": feature.name, "group": feature.group, "status": feature.status,
            "source_columns": ", ".join(feature.source_columns), "level": feature.level,
            "formula": feature.formula, "unit": feature.unit, "dtype": feature.dtype,
            "denominator": feature.aggregation_denominator or "-",
            "missing_semantics": feature.missing_semantics,
            "availability": feature.availability, "target_derived": feature.target_derived,
            "allowed_tasks": ", ".join(feature.allowed_tasks),
            "allowed_targets": ", ".join(feature.allowed_targets),
            "forbidden_targets": ", ".join(feature.forbidden_targets),
            "leakage_reason": feature.leakage_reason,
            "requires_current_outcome": feature.requires_current_outcome,
            "requires_survival": feature.requires_survival,
            "requires_placement": feature.requires_placement,
            "version": feature.version, "description": feature.description,
        } for feature in self._registry.values()])

    def export_dictionary_csv(self, output_path: Path) -> Path:
        from src.data.io import atomic_write_csv
        atomic_write_csv(Path(output_path), self.export_dictionary_dataframe())
        return Path(output_path)

    def get_allowed_features(self, task: str) -> List[str]:
        return [feature.name for feature in self._registry.values()
                if feature.status == "confirmed" and task in feature.allowed_tasks]

    def compute_dependency_closure(self, feature_names: List[str]) -> Set[str]:
        closure: Set[str] = set()
        queue = list(feature_names)
        while queue:
            name = queue.pop(0)
            if name in closure:
                continue
            closure.add(name)
            feature = self._registry.get(name)
            if feature:
                queue.extend(dependency for dependency in feature.depends_on if dependency not in closure)
        return closure

    def remove_group_and_descendants(self, current_features: List[str], group_to_remove: str) -> List[str]:
        removed = {feature.name for feature in self._registry.values() if feature.group == group_to_remove}
        changed = True
        while changed:
            changed = False
            for feature in self._registry.values():
                if feature.name not in removed and any(dep in removed for dep in feature.depends_on):
                    removed.add(feature.name)
                    changed = True
        return [name for name in current_features if name not in removed]
