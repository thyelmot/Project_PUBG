"""Appendix C: grouped CV, alpha tradeoff and placement on frozen validation only."""
import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from pubg_weapon.appendix import run_appendix

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--processed', type=Path, required=True)
    parser.add_argument('--baseline-run', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--section', choices=['rf_grid','hgb_grid','alpha_placement','alpha_recall'], required=True)
    parser.add_argument('--jobs', type=int, default=2)
    args = parser.parse_args()
    print(run_appendix(args.processed, args.baseline_run, args.output, args.section, args.jobs))
