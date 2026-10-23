"""Run one pipeline stage; see README.md for the complete sequence."""
import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
parser = argparse.ArgumentParser(description=__doc__)
from pubg_weapon.evaluation import run_evaluation
parser.add_argument('--processed', type=Path, required=True)
parser.add_argument('--run', type=Path, required=True)
parser.add_argument('--output', type=Path, required=True)
parser.add_argument('--jobs', type=int, default=2)
args = parser.parse_args()
print(run_evaluation(args.processed, args.run, args.output, args.jobs))
