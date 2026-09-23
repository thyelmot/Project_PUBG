import sys
import unittest
from pathlib import Path

# Add Project_PUBG to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.utils.config import load_config, resolve_paths, validate_config
from src.utils.runtime import check_environment
from src.features.registry import FeatureRegistry


class TestW00Setup(unittest.TestCase):
    def setUp(self):
        self.config_dir = Path(__file__).resolve().parent.parent / "configs"
        self.cfg = load_config(str(self.config_dir))

    def test_load_and_validate_config(self):
        self.assertIn("data", self.cfg)
        self.assertIn("schema", self.cfg)
        self.assertIn("features", self.cfg)
        self.assertIn("runtime", self.cfg)
        validate_config(self.cfg)

    def test_resolve_paths(self):
        paths = resolve_paths(self.cfg)
        self.assertIn("raw", paths)
        self.assertIn("interim", paths)
        self.assertIn("processed", paths)
        self.assertIn("checkpoints", paths)

    def test_environment_check(self):
        env = check_environment()
        self.assertIn(env["status"], ["healthy", "warning"])
        self.assertTrue(env["can_write"])

    def test_feature_registry_contracts(self):
        reg = FeatureRegistry()
        s1 = reg.get_allowed_features("s1")
        p1 = reg.get_allowed_features("p1")
        p2 = reg.get_allowed_features("p2")

        # Invariant D01: Phase timing and survival rate features MUST NOT be in S1
        self.assertNotIn("early_kills", s1)
        self.assertNotIn("kills_per_minute", s1)
        self.assertNotIn("player_survive_time", s1)

        # Invariant D02: P1 contains direct survival; P2 excludes direct survival
        self.assertIn("player_survive_time", p1)
        self.assertNotIn("player_survive_time", p2)

        # Ablation test: removing 'combat' group also removes 'damage_per_kill'
        t1 = reg.get_allowed_features("t1")
        ablated = reg.remove_group_and_descendants(t1, "combat")
        self.assertNotIn("player_kills", ablated)
        self.assertNotIn("player_dmg", ablated)
        self.assertNotIn("damage_per_kill", ablated)


if __name__ == "__main__":
    unittest.main()
