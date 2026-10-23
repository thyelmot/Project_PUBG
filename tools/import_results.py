"""Import an intact Kaggle ZIP snapshot without running its code or models."""
from pathlib import Path, PurePosixPath
import argparse
import hashlib
import json
import shutil
import stat
import tempfile
import time
import zipfile


def import_results(archive, target):
    archive, target = Path(archive).resolve(), Path(target).resolve()
    if target.exists():
        raise FileExistsError(f"Destination must be new: {target}")
    started = time.monotonic()
    with zipfile.ZipFile(archive) as bundle:
        files = [entry for entry in bundle.infolist() if not entry.is_dir()]
        names = set()
        for entry in bundle.infolist():
            name = entry.filename
            parts = PurePosixPath(name).parts
            if (not parts or name.startswith('/') or '\\' in name
                    or any(p in {'.', '..'} or ':' in p or p.rstrip(' .') != p for p in parts)
                    or stat.S_ISLNK(entry.external_attr >> 16)):
                raise ValueError(f"Unsafe ZIP path: {name}")
            key = name.rstrip('/').casefold()
            if key in names:
                raise ValueError(f"Duplicate ZIP path: {name}")
            names.add(key)
        handoffs = [entry.filename for entry in files if entry.filename.endswith('/handoff_full.json')]
        if len(handoffs) != 1:
            raise ValueError("Expected exactly one handoff_full.json")
        prefix = handoffs[0].removesuffix('handoff_full.json')
        manifest = json.loads(bundle.read(handoffs[0]))
        records = manifest['stages']
        if set(records) != {f'S{i:02d}' for i in range(1, 11)} or any(
                r.get('status') != 'completed' for r in records.values()):
            raise ValueError("Expected completed S01-S10")
        expected = {}
        available = {entry.filename: entry for entry in files}
        for entry in manifest['entries']:
            name = prefix + entry['path']
            if name in expected or name not in available or available[name].file_size != entry['bytes']:
                raise ValueError(f"Invalid/missing handoff entry: {name}")
            expected[name] = entry
        total = sum(entry.file_size for entry in files)
        target.parent.mkdir(parents=True, exist_ok=True)
        if shutil.disk_usage(target.parent).free < total + 1024**3:
            raise OSError("Insufficient disk space plus 1 GiB reserve")
        print(f'Extracting {len(files)} files, {total / 2**30:.2f} GiB', flush=True)
        with tempfile.TemporaryDirectory(prefix='.pubg-results-import-', dir=target.parent) as folder:
            staging = Path(folder) / 'results'
            staging.mkdir()
            done = 0
            for index, entry in enumerate(files, 1):
                dest = staging.joinpath(*PurePosixPath(entry.filename).parts)
                if not dest.resolve().is_relative_to(staging.resolve()):
                    raise ValueError('Destination escape')
                dest.parent.mkdir(parents=True, exist_ok=True)
                with bundle.open(entry) as source, dest.open('xb') as output:
                    shutil.copyfileobj(source, output, length=8 * 1024**2)
                if dest.stat().st_size != entry.file_size:
                    raise IOError(f'Extracted size mismatch: {entry.filename}')
                done += entry.file_size
                if entry.file_size > 64 * 1024**2 or index % 50 == 0:
                    print(f'Extracted {index}/{len(files)}; {done / 2**30:.2f} GiB', flush=True)
            print('Verifying saved SHA256 hashes from disk', flush=True)
            for index, (name, entry) in enumerate(expected.items(), 1):
                with (staging / name).open('rb') as source:
                    actual = hashlib.file_digest(source, 'sha256').hexdigest()
                if actual != entry['sha256']:
                    raise ValueError(f'Checksum mismatch: {name}')
                if index % 50 == 0:
                    print(f'Checksums {index}/{len(expected)}', flush=True)
            root = staging / prefix
            stage_file = root / 'outputs/full/checkpoints/stages.json'
            if json.loads(stage_file.read_text(encoding='utf-8')) != records:
                raise ValueError('Handoff and stage checkpoint differ')
            inventory = {entry['path']: entry for entry in manifest['entries']}
            for record in records.values():
                for entry in record.get('artifacts', []):
                    if inventory.get(entry['path'], {}).get('sha256') != entry['sha256']:
                        raise ValueError(f"Stage inventory mismatch: {entry['path']}")
            import pyarrow.parquet as pq
            parquets = list(root.rglob('*.parquet'))
            for path in parquets:
                pq.ParquetFile(path).schema_arrow
            releases = list((root / 'outputs/full/manifests/releases').glob('*/manifest.json'))
            for path in releases:
                for entry in json.loads(path.read_text(encoding='utf-8'))['entries']:
                    relative = (path.parent / entry['path']).relative_to(root).as_posix()
                    if inventory.get(relative, {}).get('sha256') != entry['sha256']:
                        raise ValueError(f'Release inventory mismatch: {relative}')
            receipt = {
                'archive': str(archive), 'snapshot': prefix.rstrip('/'),
                'files': len(files), 'bytes': total, 'verified_handoff_entries': len(expected),
                'zip_crc': 'checked while extracting every file',
                'sha256': 'all handoff entries verified from extracted files',
                'parquet_headers_checked': len(parquets), 'release_manifests_checked': len(releases),
                'stages': {s: r['status'] for s, r in records.items()},
                'limitations': 'No model deserialization, raw source verification, full Parquet decode or stage rerun.',
                'seconds': round(time.monotonic() - started, 2),
            }
            (staging / 'IMPORT_VERIFICATION.json').write_text(
                json.dumps(receipt, ensure_ascii=False, indent=2), encoding='utf-8')
            if target.exists():
                raise FileExistsError('Destination appeared during import')
            staging.rename(target)
    print(json.dumps(receipt, ensure_ascii=False, indent=2), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('archive', type=Path)
    parser.add_argument('target', type=Path)
    args = parser.parse_args()
    import_results(args.archive, args.target)
