"""Inspect validation errors without opening the real test partition."""
import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from pubg_weapon.diagnostics import run_diagnostics

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--processed', type=Path, required=True)
parser.add_argument('--run', type=Path, required=True)
parser.add_argument('--output', type=Path, required=True)
parser.add_argument('--jobs', type=int, default=2)
args = parser.parse_args()
print(run_diagnostics(args.processed, args.run, args.output, args.jobs))
