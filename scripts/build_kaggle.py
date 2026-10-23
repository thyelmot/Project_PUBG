"""Bundle current source/tests into a private Kaggle CPU script, without credentials."""
import argparse
import base64
import hashlib
import io
import json
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def build(output, owner, slug, mode='smoke', matches=None, max_train_rows=None, evaluate=False):
    if not owner or not slug:
        raise ValueError('owner and slug are required')
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    members = sorted([*ROOT.glob('src/pubg_weapon/*.py'), *ROOT.glob('tests/*.py'),
                      *ROOT.glob('scripts/0*.py'), ROOT / 'configs/label_mapping.json',
                      *ROOT.glob('configs/*.csv'),
                      ROOT / 'pyproject.toml', ROOT / 'kaggle/runner.py'])
    content = io.BytesIO()
    hashes = {}
    with zipfile.ZipFile(content, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        for path in members:
            relative = path.relative_to(ROOT).as_posix()
            data = path.read_bytes()
            hashes[relative] = hashlib.sha256(data).hexdigest()
            archive.writestr(relative, data)
        archive.writestr('source_hashes.json', json.dumps(hashes, indent=2))
    encoded = base64.b64encode(content.getvalue()).decode('ascii')
    matches = matches if matches is not None else (50_000 if mode == 'full' else 3000)
    max_train_rows = max_train_rows if max_train_rows is not None else {
        'smoke': 30_000, 'pilot': 100_000, 'diagnostic': 100_000, 'full': 1_000_000}[mode]
    bootstrap = f'''import base64, io, zipfile
from pathlib import Path
project = Path('/kaggle/working/project')
project.mkdir(exist_ok=False)
with zipfile.ZipFile(io.BytesIO(base64.b64decode({encoded!r}))) as archive:
    archive.extractall(project)
'''
    runner = (ROOT / 'kaggle/runner.py').read_text()
    (output / 'main.py').write_text(bootstrap + '\n' + runner +
        f'\nrun(project, {mode!r}, {matches!r}, {max_train_rows!r}, {evaluate!r})\n')
    metadata = {'id': f'{owner}/{slug}', 'title': slug.replace('-', ' '), 'code_file': 'main.py',
        'language': 'python', 'kernel_type': 'script', 'is_private': True,
        'enable_gpu': False, 'enable_internet': False,
        'dataset_sources': ['skihikingkevin/pubg-match-deaths'],
        'competition_sources': [], 'kernel_sources': []}
    (output / 'kernel-metadata.json').write_text(json.dumps(metadata, indent=2) + '\n')
    (output / 'source_hashes.json').write_text(json.dumps(hashes, indent=2) + '\n')
    print(f'Built {metadata["id"]} in {output}; mode={mode}, matches={matches}, max_train_rows={max_train_rows}')
    return hashes


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--owner', required=True)
    parser.add_argument('--slug', required=True)
    parser.add_argument('--mode', choices=['smoke', 'pilot', 'diagnostic', 'full'], default='smoke')
    parser.add_argument('--matches', type=int)
    parser.add_argument('--max-train-rows', type=int)
    parser.add_argument('--evaluate', action='store_true', help='Unlock final test evaluation after training')
    args = parser.parse_args()
    build(args.output, args.owner, args.slug, args.mode, args.matches, args.max_train_rows, args.evaluate)
