"""Experiment Registry and lifecycle tracking for PUBG research models."""
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Dict, List, Optional, Any, Union
import json
import os


VALID_LIFECYCLE_STATES = {
    "planned",
    "running",
    "completed",
    "failed",
    "blocked",
    "resource_limited",
    "stale",
}


@dataclass
class ExperimentDefinition:
    """Canonical definition of a machine learning experiment."""
    experiment_id: str
    rq: str
    task: str
    target_col: str
    feature_names: List[str]
    model_type: str
    model_params: Dict[str, Any] = field(default_factory=dict)
    seed: int = 42
    status: str = "planned"
    reason_code: Optional[str] = None
    metrics: Optional[Dict[str, float]] = None
    artifact_paths: Dict[str, str] = field(default_factory=dict)
    signatures: Dict[str, str] = field(default_factory=dict)
    split_scope: str = "official"

    def __post_init__(self):
        if self.status not in VALID_LIFECYCLE_STATES:
            raise ValueError(f"Invalid status '{self.status}'. Must be one of {VALID_LIFECYCLE_STATES}")


class ExperimentRegistry:
    """Registry maintaining experiment lifecycles, states, and reproduction metadata."""

    def __init__(self, registry_path: Optional[Union[str, Path]] = None):
        self._experiments: Dict[str, ExperimentDefinition] = {}
        self.registry_path = Path(registry_path) if registry_path else None
        if self.registry_path and self.registry_path.is_file():
            self.load(self.registry_path)

    def register(self, experiment: ExperimentDefinition) -> None:
        """Register or update an experiment definition."""
        self._experiments[experiment.experiment_id] = experiment

    def get(self, experiment_id: str) -> Optional[ExperimentDefinition]:
        """Retrieve an experiment definition by ID."""
        return self._experiments.get(experiment_id)

    def update_status(
        self,
        experiment_id: str,
        status: str,
        reason_code: Optional[str] = None,
    ) -> None:
        """Update experiment lifecycle state."""
        if experiment_id not in self._experiments:
            raise KeyError(f"Experiment '{experiment_id}' not found in registry")
        if status not in VALID_LIFECYCLE_STATES:
            raise ValueError(f"Invalid status '{status}'. Must be one of {VALID_LIFECYCLE_STATES}")
        exp = self._experiments[experiment_id]
        exp.status = status
        exp.reason_code = reason_code

    def update_metrics(
        self,
        experiment_id: str,
        metrics: Dict[str, float],
        artifacts: Optional[Dict[str, str]] = None,
    ) -> None:
        """Record completed experiment metrics and artifact paths."""
        if experiment_id not in self._experiments:
            raise KeyError(f"Experiment '{experiment_id}' not found in registry")
        exp = self._experiments[experiment_id]
        exp.metrics = metrics
        exp.status = "completed"
        exp.reason_code = None
        if artifacts:
            exp.artifact_paths.update(artifacts)

    def list_all(self) -> List[ExperimentDefinition]:
        """List all registered experiments."""
        return list(self._experiments.values())

    def filter_by(
        self,
        rq: Optional[str] = None,
        task: Optional[str] = None,
        status: Optional[str] = None,
    ) -> List[ExperimentDefinition]:
        """Filter experiments by research question, task, or lifecycle status."""
        results = list(self._experiments.values())
        if rq:
            results = [e for e in results if e.rq == rq]
        if task:
            results = [e for e in results if e.task == task]
        if status:
            results = [e for e in results if e.status == status]
        return results

    def to_dict(self) -> Dict[str, Any]:
        """Serialize registry to dictionary."""
        return {
            "experiments": {exp_id: asdict(exp) for exp_id, exp in self._experiments.items()}
        }

    def save(self, path: Optional[Union[str, Path]] = None) -> None:
        """Save registry to JSON file."""
        target_path = Path(path) if path else self.registry_path
        if not target_path:
            raise ValueError("No path specified to save experiment registry")
        target_path.parent.mkdir(parents=True, exist_ok=True)
        with open(target_path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2, ensure_ascii=False)

    def load(self, path: Union[str, Path]) -> None:
        """Load registry from JSON file."""
        load_path = Path(path)
        if not load_path.is_file():
            raise FileNotFoundError(f"Registry file not found: {load_path}")
        with open(load_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        self._experiments = {}
        for exp_id, exp_dict in data.get("experiments", {}).items():
            self._experiments[exp_id] = ExperimentDefinition(**exp_dict)


def create_canonical_experiment_matrix() -> ExperimentRegistry:
    """Build the canonical PUBG research experiment matrix."""
    reg = ExperimentRegistry()

    # Core placement tasks
    reg.register(ExperimentDefinition(
        experiment_id="p1_ols_direct_survival",
        rq="rq3",
        task="p1",
        target_col="normalized_placement",
        feature_names=["combat", "movement", "support", "timing", "player_survive_time"],
        model_type="OLS",
    ))
    reg.register(ExperimentDefinition(
        experiment_id="p2_ols_no_direct_survival",
        rq="rq3",
        task="p2",
        target_col="normalized_placement",
        feature_names=["combat", "movement", "support", "timing"],
        model_type="OLS",
    ))
    reg.register(ExperimentDefinition(
        experiment_id="p3_historical_placement",
        rq="rq3",
        task="p3",
        target_col="normalized_placement",
        feature_names=["hist_kills_mean", "hist_dmg_mean", "hist_walk_mean", "hist_placement_mean"],
        model_type="OLS",
    ))
    reg.register(ExperimentDefinition(
        experiment_id="p3_historical_expanding",
        rq="rq3",
        task="p3",
        target_col="normalized_placement",
        feature_names=["hist_kills_mean", "hist_dmg_mean", "hist_walk_mean", "hist_placement_mean"],
        model_type="OLS",
    ))


    # Core survival tasks
    reg.register(ExperimentDefinition(
        experiment_id="s1_retrospective_survival",
        rq="rq3",
        task="s1",
        target_col="player_survive_time",
        feature_names=["combat", "movement", "support", "timing_safe"],
        model_type="OLS",
    ))
    reg.register(ExperimentDefinition(
        experiment_id="s2_historical_survival",
        rq="rq3",
        task="s2",
        target_col="player_survive_time",
        feature_names=["hist_kills_mean", "hist_dmg_mean", "hist_walk_mean", "hist_survive_mean"],
        model_type="OLS",
    ))

    # Timing comparison tasks
    reg.register(ExperimentDefinition(
        experiment_id="t0_placement_without_timing",
        rq="rq3",
        task="t0",
        target_col="normalized_placement",
        feature_names=["combat", "movement", "support"],
        model_type="OLS",
    ))
    reg.register(ExperimentDefinition(
        experiment_id="t1_placement_with_timing",
        rq="rq3",
        task="t1",
        target_col="normalized_placement",
        feature_names=["combat", "movement", "support", "timing"],
        model_type="OLS",
    ))

    # Baselines
    for task_name, target in [("p1", "normalized_placement"), ("p2", "normalized_placement"), ("s1", "player_survive_time")]:
        reg.register(ExperimentDefinition(
            experiment_id=f"{task_name}_baseline_mean",
            rq="rq3",
            task=task_name,
            target_col=target,
            feature_names=[],
            model_type="TrainMean",
        ))
        reg.register(ExperimentDefinition(
            experiment_id=f"{task_name}_baseline_median",
            rq="rq3",
            task=task_name,
            target_col=target,
            feature_names=[],
            model_type="TrainMedian",
        ))

    return reg
