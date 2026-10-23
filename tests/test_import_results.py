"""Small archive checks; these fixtures are not PUBG research results."""
from pathlib import Path
import hashlib
import importlib.util
import json
import tempfile
import unittest
import zipfile

spec = importlib.util.spec_from_file_location('results_import', Path(__file__).resolve().parents[1] / 'tools/import_results.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class ImportResultsTests(unittest.TestCase):
    def make_zip(self, path, corrupt=False):
        records = {f'S{i:02d}': {'status': 'completed', 'artifacts': []} for i in range(1, 11)}
        payload = b'fixture, not research data'
        manifest = {'stages': records, 'entries': [{
            'path': 'payload.txt', 'bytes': len(payload),
            'sha256': '0' * 64 if corrupt else hashlib.sha256(payload).hexdigest(),
        }]}
        with zipfile.ZipFile(path, 'w') as bundle:
            bundle.writestr('run/handoff_full.json', json.dumps(manifest))
            bundle.writestr('run/payload.txt', payload)
            bundle.writestr('run/outputs/full/checkpoints/stages.json', json.dumps(records))

    def test_import_preserves_bytes_and_rejects_existing_destination(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            self.make_zip(root / 'input.zip')
            module.import_results(root / 'input.zip', root / 'results')
            self.assertEqual((root / 'results/run/payload.txt').read_bytes(), b'fixture, not research data')
            with self.assertRaises(FileExistsError):
                module.import_results(root / 'input.zip', root / 'results')

    def test_corrupt_hash_does_not_publish(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            self.make_zip(root / 'input.zip', corrupt=True)
            with self.assertRaisesRegex(ValueError, 'Checksum mismatch'):
                module.import_results(root / 'input.zip', root / 'results')
            self.assertFalse((root / 'results').exists())
            self.assertEqual(list(root.glob('.pubg-results-import-*')), [])

    def test_path_traversal_rejected_before_extraction(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            with zipfile.ZipFile(root / 'input.zip', 'w') as bundle:
                bundle.writestr('../outside.txt', 'unsafe')
            with self.assertRaisesRegex(ValueError, 'Unsafe ZIP path'):
                module.import_results(root / 'input.zip', root / 'results')
            self.assertFalse((root / 'outside.txt').exists())


if __name__ == '__main__':
    unittest.main()
