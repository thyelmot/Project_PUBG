"""Package one validation-only appendix section, attaching the frozen main kernel."""
import argparse
import base64
import hashlib
import io
import json
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def build(output, owner, slug, section, baseline_run, docker_image=None):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    baseline_run = Path(baseline_run)
    manifest_hash = json.loads((baseline_run / 'metadata.json').read_text())['dataset_manifest_sha256']
    metadata_hash = hashlib.sha256((baseline_run / 'metadata.json').read_bytes()).hexdigest()
    split_hash = '3cd3e1a76c8679b510ee791bbd280a3684a51ffc03676c39ffbcc7466296c8ce'
    files = sorted([*ROOT.glob('src/pubg_weapon/*.py'), *ROOT.glob('tests/*.py'),
                    *ROOT.glob('scripts/0*.py'), *ROOT.glob('configs/*.csv'),
                    ROOT / 'scripts/build_appendix_kaggle.py',
                    ROOT / 'configs/label_mapping.json', ROOT / 'pyproject.toml',
                    ROOT / 'kaggle/runner.py', ROOT / 'kaggle/appendix_runner.py'])
    buffer = io.BytesIO(); hashes = {}
    with zipfile.ZipFile(buffer, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        for path in files:
            relative = path.relative_to(ROOT).as_posix(); content = path.read_bytes()
            hashes[relative] = hashlib.sha256(content).hexdigest()
            archive.writestr(relative, content)
        archive.writestr('source_hashes.json', json.dumps(hashes, indent=2))
    encoded = base64.b64encode(buffer.getvalue()).decode('ascii')
    bootstrap = f'''import base64, io, zipfile, os, sys, faulthandler
from pathlib import Path
for variable in ('OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS', 'NUMEXPR_NUM_THREADS'):
    os.environ[variable] = '2'
os.environ['PYTHONUNBUFFERED'] = '1'
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(line_buffering=True)
faulthandler.enable()
print('Appendix bootstrap: CPU threads=2; extracting source', flush=True)
project = Path('/kaggle/working/project')
project.mkdir(exist_ok=False)
with zipfile.ZipFile(io.BytesIO(base64.b64decode({encoded!r}))) as archive:
    archive.extractall(project)
'''
    runner = (ROOT / 'kaggle/appendix_runner.py').read_text()
    (output / 'main.py').write_text(bootstrap + '\n' + runner +
        f'\nexecute(project, {section!r}, {manifest_hash!r}, {metadata_hash!r}, {split_hash!r})\n')
    metadata = {'id': f'{owner}/{slug}', 'title': slug.replace('-', ' '), 'code_file': 'main.py',
        'language': 'python', 'kernel_type': 'script', 'is_private': True,
        'enable_gpu': False, 'enable_internet': False, 'dataset_sources': [], 'competition_sources': [],
        'kernel_sources': ['sangtranminh211/pubg-loadout-history-full-final-20261022']}
    if docker_image:
        metadata['docker_image'] = docker_image
    (output / 'kernel-metadata.json').write_text(json.dumps(metadata, indent=2)+'\n')
    (output / 'source_hashes.json').write_text(json.dumps(hashes, indent=2)+'\n')
    print(f'Built {metadata["id"]}: {section}; frozen full data, validation only')
    return hashes


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--owner', required=True)
    parser.add_argument('--slug', required=True)
    parser.add_argument('--section', choices=['rf_grid','hgb_grid','alpha_placement','alpha_recall'], required=True)
    parser.add_argument('--baseline-run', type=Path, required=True)
    parser.add_argument('--docker-image', help='Pin the image digest of the successful frozen main run')
    args = parser.parse_args()
    build(args.output, args.owner, args.slug, args.section, args.baseline_run, args.docker_image)
