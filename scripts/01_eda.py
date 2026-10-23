"""Run one pipeline stage; see README.md for the complete sequence."""
import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
parser = argparse.ArgumentParser(description=__doc__)
from pubg_weapon.eda import run_eda
parser.add_argument('--source', type=Path, required=True)
parser.add_argument('--output', type=Path, required=True)
parser.add_argument('--matches', type=int, default=50_000)
parser.add_argument('--chunk-size', type=int, default=100_000)
parser.add_argument('--seed', type=int, default=42)
args = parser.parse_args()
print(run_eda(args.source, args.output, args.matches, args.chunk_size, args.seed))
