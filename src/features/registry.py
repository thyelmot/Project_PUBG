from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set


@dataclass
class FeatureDefinition:
    name: str
    group: str  # combat, movement, support, combat_timing_absolute, combat_timing_phase, placement, diagnostic
    status: str = "candidate"  # candidate, confirmed, excluded
    depends_on: List[str] = field(default_factory=list)
    availability: str = "post_match"  # pre_match, strict_past, post_match
    missing_indicator: bool = False
    aggregation_denominator: Optional[str] = None
    target_derived: bool = False
    description: str = ""
    allowed_tasks: List[str] = field(default_factory=list)


class FeatureRegistry:
    """Canonical registry defining all research features, dependencies, and leakage contracts."""

    def __init__(self) -> None:
        self._registry: Dict[str, FeatureDefinition] = {}
        self._init_defaults()

    def register(self, feature: FeatureDefinition) -> None:
        """Register or update a feature definition."""
        self._registry[feature.name] = feature

    def get(self, name: str) -> Optional[FeatureDefinition]:
        return self._registry.get(name)

    def list_all(self) -> List[FeatureDefinition]:
        return list(self._registry.values())

    def _init_defaults(self) -> None:
        # Combat core
        self.register(FeatureDefinition(
            name="player_kills",
            group="combat",
            status="confirmed",
            depends_on=[],
            availability="post_match",
            allowed_tasks=["rq1_survival", "rq1_placement", "rq2", "s1", "p1", "p2", "t0", "t1", "ablation"],
            description="Total confirmed player kills in match",
        ))
        self.register(FeatureDefinition(
            name="player_dmg",
            group="combat",
            status="confirmed",
            depends_on=[],
            availability="post_match",
            allowed_tasks=["rq1_survival", "rq1_placement", "rq2", "s1", "p1", "p2", "t0", "t1", "ablation"],
            description="Total damage inflicted on opponents",
        ))
        self.register(FeatureDefinition(
            name="damage_per_kill",
            group="combat",
            status="confirmed",
            depends_on=["player_dmg", "player_kills"],
            availability="post_match",
            aggregation_denominator="player_kills",
            allowed_tasks=["rq1_survival", "rq1_placement", "rq2", "s1", "p1", "p2", "t0", "t1", "ablation"],
            description="Damage per kill (NaN if kills == 0)",
        ))

        # Movement core
        self.register(FeatureDefinition(
            name="player_dist_walk",
            group="movement",
            status="confirmed",
            depends_on=[],
            availability="post_match",
            allowed_tasks=["rq1_survival", "rq1_placement", "rq2", "s1", "p1", "p2", "t0", "t1", "ablation"],
            description="Distance walked in meters",
        ))
        self.register(FeatureDefinition(
            name="player_dist_ride",
            group="movement",
            status="confirmed",
            depends_on=[],
            availability="post_match",
            allowed_tasks=["rq1_survival", "rq1_placement", "rq2", "s1", "p1", "p2", "t0", "t1", "ablation"],
            description="Distance ridden in vehicles in meters",
        ))
        self.register(FeatureDefinition(
            name="total_distance",
            group="movement",
            status="confirmed",
            depends_on=["player_dist_walk", "player_dist_ride"],
            availability="post_match",
            allowed_tasks=["rq1_survival", "rq1_placement", "rq2", "s1", "p1", "p2", "t0", "t1", "ablation"],
            description="Total distance traversed",
        ))
        self.register(FeatureDefinition(
            name="walk_ratio",
            group="movement",
            status="confirmed",
            depends_on=["player_dist_walk", "total_distance"],
            availability="post_match",
            aggregation_denominator="total_distance",
            allowed_tasks=["rq1_survival", "rq1_placement", "rq2", "s1", "p1", "p2", "t0", "t1", "ablation"],
            description="Proportion of distance on foot (NaN if total_distance == 0)",
        ))

        # Support core
        self.register(FeatureDefinition(
            name="player_assists",
            group="support",
            status="confirmed",
            depends_on=[],
            availability="post_match",
            allowed_tasks=["rq1_survival", "rq1_placement", "rq2", "s1", "p1", "p2", "t0", "t1", "ablation"],
            description="Total assists credited",
        ))
        self.register(FeatureDefinition(
            name="player_dbno",
            group="support",
            status="confirmed",
            depends_on=[],
            availability="post_match",
            allowed_tasks=["rq1_survival", "rq1_placement", "rq2", "s1", "p1", "p2", "t0", "t1", "ablation"],
            description="Down-but-not-out instances caused",
        ))
        self.register(FeatureDefinition(
            name="assist_ratio",
            group="support",
            status="confirmed",
            depends_on=["player_assists", "player_kills"],
            availability="post_match",
            aggregation_denominator="player_assists + player_kills",
            allowed_tasks=["rq1_survival", "rq1_placement", "rq2", "s1", "p1", "p2", "t0", "t1", "ablation"],
            description="Assists / (kills + assists) (NaN if sum == 0)",
        ))

        # Outcomes / Targets
        self.register(FeatureDefinition(
            name="player_survive_time",
            group="outcome",
            status="confirmed",
            depends_on=[],
            availability="post_match",
            allowed_tasks=["target_s1", "target_s2", "p1"],  # Allowed in P1 as direct predictor; target in S1/S2
            description="Duration survived in seconds",
        ))
        self.register(FeatureDefinition(
            name="normalized_placement",
            group="outcome",
            status="confirmed",
            depends_on=["team_placement", "N_teams"],
            availability="post_match",
            allowed_tasks=["target_p1", "target_p2", "target_p3"],
            description="Normalized team placement in [0, 1]",
        ))

        # Combat Timing - Absolute (Safe for S1 under D01)
        self.register(FeatureDefinition(
            name="event_kill_count",
            group="combat_timing_absolute",
            status="confirmed",
            depends_on=[],
            availability="post_match",
            allowed_tasks=["rq1_survival", "rq1_placement", "rq2", "s1", "p1", "p2", "t1", "ablation"],
            description="Count of matched death kill events",
        ))
        self.register(FeatureDefinition(
            name="first_kill_time",
            group="combat_timing_absolute",
            status="confirmed",
            depends_on=[],
            availability="post_match",
            allowed_tasks=["rq1_survival", "rq1_placement", "rq2", "s1", "p1", "p2", "t1", "ablation"],
            description="Timestamp of first kill in match",
        ))
        self.register(FeatureDefinition(
            name="avg_kill_time",
            group="combat_timing_absolute",
            status="confirmed",
            depends_on=[],
            availability="post_match",
            allowed_tasks=["rq1_survival", "rq1_placement", "rq2", "s1", "p1", "p2", "t1", "ablation"],
            description="Average timestamp of player kills",
        ))
        self.register(FeatureDefinition(
            name="has_kill",
            group="combat_timing_absolute",
            status="confirmed",
            depends_on=[],
            availability="post_match",
            allowed_tasks=["rq1_survival", "rq1_placement", "rq2", "s1", "p1", "p2", "t1", "ablation"],
            description="Binary indicator for whether player scored >= 1 kill",
        ))

        # Combat Timing - Phase (Derived from match duration proxy -> excluded from S1 by D01)
        self.register(FeatureDefinition(
            name="early_kills",
            group="combat_timing_phase",
            status="confirmed",
            depends_on=["estimated_match_duration"],
            availability="post_match",
            target_derived=True,  # depends on max(player_survive_time)
            allowed_tasks=["rq1_placement", "rq2", "p1", "p2", "t1", "ablation"],
            description="Kills in phase [0, 1/3) of match duration",
        ))
        self.register(FeatureDefinition(
            name="mid_kills",
            group="combat_timing_phase",
            status="confirmed",
            depends_on=["estimated_match_duration"],
            availability="post_match",
            target_derived=True,
            allowed_tasks=["rq1_placement", "rq2", "p1", "p2", "t1", "ablation"],
            description="Kills in phase [1/3, 2/3) of match duration",
        ))
        self.register(FeatureDefinition(
            name="late_kills",
            group="combat_timing_phase",
            status="confirmed",
            depends_on=["estimated_match_duration"],
            availability="post_match",
            target_derived=True,
            allowed_tasks=["rq1_placement", "rq2", "p1", "p2", "t1", "ablation"],
            description="Kills in phase [2/3, 1] of match duration",
        ))
        self.register(FeatureDefinition(
            name="early_kill_ratio",
            group="combat_timing_phase",
            status="confirmed",
            depends_on=["early_kills", "event_kill_count"],
            availability="post_match",
            target_derived=True,
            allowed_tasks=["rq1_placement", "rq2", "p1", "p2", "t1", "ablation"],
            description="Early kills / total event kills",
        ))
        self.register(FeatureDefinition(
            name="mid_kill_ratio",
            group="combat_timing_phase",
            status="confirmed",
            depends_on=["mid_kills", "event_kill_count"],
            availability="post_match",
            target_derived=True,
            allowed_tasks=["rq1_placement", "rq2", "p1", "p2", "t1", "ablation"],
            description="Mid kills / total event kills",
        ))
        self.register(FeatureDefinition(
            name="late_kill_ratio",
            group="combat_timing_phase",
            status="confirmed",
            depends_on=["late_kills", "event_kill_count"],
            availability="post_match",
            target_derived=True,
            allowed_tasks=["rq1_placement", "rq2", "p1", "p2", "t1", "ablation"],
            description="Late kills / total event kills",
        ))

        # Target-derived diagnostic features (Prohibited as primary predictors for survival)
        self.register(FeatureDefinition(
            name="kills_per_minute",
            group="diagnostic",
            status="confirmed",
            depends_on=["player_kills", "player_survive_time"],
            availability="post_match",
            target_derived=True,
            allowed_tasks=["diagnostic"],
            description="Kills per minute of survival (Diagnostic only)",
        ))
        self.register(FeatureDefinition(
            name="damage_per_minute",
            group="diagnostic",
            status="confirmed",
            depends_on=["player_dmg", "player_survive_time"],
            availability="post_match",
            target_derived=True,
            allowed_tasks=["diagnostic"],
            description="Damage per minute of survival (Diagnostic only)",
        ))

    def get_allowed_features(self, task: str) -> List[str]:
        """Return all features explicitly authorized for a task."""
        return [f.name for f in self._registry.values() if task in f.allowed_tasks]

    def compute_dependency_closure(self, feature_names: List[str]) -> Set[str]:
        """Compute the recursive closure of all dependencies for given features."""
        closure: Set[str] = set()
        queue = list(feature_names)
        while queue:
            feat = queue.pop(0)
            if feat not in closure:
                closure.add(feat)
                if feat in self._registry:
                    for dep in self._registry[feat].depends_on:
                        if dep not in closure:
                            queue.append(dep)
        return closure

    def remove_group_and_descendants(self, current_features: List[str], group_to_remove: str) -> List[str]:
        """Ablation helper: remove an entire group plus all features depending on any removed feature."""
        # Find features in target group
        removed_base = {f.name for f in self._registry.values() if f.group == group_to_remove}
        # Find everything that depends on removed_base
        all_removed = set(removed_base)
        changed = True
        while changed:
            changed = False
            for f in self._registry.values():
                if f.name not in all_removed:
                    if any(dep in all_removed for dep in f.depends_on):
                        all_removed.add(f.name)
                        changed = True

        return [f for f in current_features if f not in all_removed]
