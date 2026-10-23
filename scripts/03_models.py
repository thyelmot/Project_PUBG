"""Run one pipeline stage; see README.md for the complete sequence."""
import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
parser = argparse.ArgumentParser(description=__doc__)
from pubg_weapon.training import run_training
parser.add_argument('--processed', type=Path, required=True)
parser.add_argument('--output', type=Path, required=True)
parser.add_argument('--quick', action='store_true', help='Small RF/HGB settings for smoke testing')
parser.add_argument('--jobs', type=int, default=2)
parser.add_argument('--with-placement', action='store_true', help='Retrospective experiment using final ranks')
parser.add_argument('--main-feature-set', choices=['full', 'loadout_history'], default='loadout_history')
args = parser.parse_args()
print(run_training(args.processed, args.output, args.quick, args.jobs, args.with_placement, args.main_feature_set))
