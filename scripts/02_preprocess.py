"""Run one pipeline stage; see README.md for the complete sequence."""
import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
parser = argparse.ArgumentParser(description=__doc__)
from pubg_weapon.preprocessing import run_preprocessing
parser.add_argument('--eda', type=Path, required=True)
parser.add_argument('--output', type=Path, required=True)
parser.add_argument('--mapping', type=Path, default=ROOT / 'configs' / 'label_mapping.json')
parser.add_argument('--max-train-rows', type=int, default=1_000_000)
parser.add_argument('--seed', type=int, default=42)
args = parser.parse_args()
print(run_preprocessing(args.eda, args.output, args.mapping, args.max_train_rows, args.seed))
