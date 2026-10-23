"""Compare RF regularization, sub-bootstrapping, tempered weights, and feature pruning on validation."""
import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from pubg_weapon.rf_experiment import run_rf_experiment

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--processed', type=Path, required=True)
parser.add_argument('--baseline-run', type=Path, required=True)
parser.add_argument('--output', type=Path, required=True)
parser.add_argument('--jobs', type=int, default=2)
args = parser.parse_args()
print(run_rf_experiment(args.processed, args.baseline_run, args.output, args.jobs))
