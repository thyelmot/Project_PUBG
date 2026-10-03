"""Execute every NB12 cell, including read-only bootstrap, without raw or a prior kernel."""
import base64
import copy
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch
import nbformat
import pandas as pd
from src.data.io import read_json, atomic_write_json
from src.evaluation.finalize import load_locked_release, artifact_metadata
from src.evaluation.summary import key_findings, public_frame, metadata_frame
from src.utils.hashing import hash_file, hash_dict

ROOT = Path(__file__).resolve().parents[1]


def fingerprints(directory):
    return {p.relative_to(directory).as_posix(): hash_file(p) for p in directory.rglob('*') if p.is_file()}


def execute_summary(manifest, *, allow_fixture=True):
    notebook = nbformat.read(ROOT/'notebooks/12_final_results_summary.ipynb', as_version=4)
    scope = {'PUBG_STORAGE_MODE': 'runtime', 'PUBG_SUMMARY_CODE_ROOT': str(ROOT),
             'PUBG_SUMMARY_MANIFEST': str(manifest), 'PUBG_SUMMARY_ALLOW_FIXTURE': allow_fixture}
    outputs = []
    def capture(value):
        if isinstance(value, pd.DataFrame):
            outputs.append(nbformat.v4.new_output('display_data', data={'text/html': value.to_html(index=False), 'text/plain': value.to_string(index=False)}))
        elif value.__class__.__name__ == 'Markdown':
            outputs.append(nbformat.v4.new_output('display_data', data={'text/markdown': value.data}))
        elif value.__class__.__name__ == 'Image':
            outputs.append(nbformat.v4.new_output('display_data', data={'image/png': base64.b64encode(value.data).decode()}))
    with patch('IPython.display.display', side_effect=capture), \
         patch('src.utils.config.load_config', side_effect=AssertionError('summary must not load current config')), \
         patch('src.data.checkpoints.CheckpointManager.__init__', side_effect=AssertionError('summary must not create checkpoint manager')), \
         patch('src.models.linear.LinearModelWrapper.fit', side_effect=AssertionError('summary must not train')), \
         patch('urllib.request.urlopen', side_effect=AssertionError('summary must not download')), \
         patch('joblib.load', side_effect=AssertionError('summary must not load model pickle')), \
         patch('subprocess.check_call', side_effect=AssertionError('summary must not install packages')), \
         patch('pathlib.Path.mkdir', side_effect=AssertionError('summary must not create directories')):
        for cell in notebook.cells:
            if cell.cell_type != 'code' or 'storage-options' in cell.metadata.get('tags', []):
                continue
            outputs = []
            stream = io.StringIO()
            with redirect_stdout(stream):
                exec(compile(cell.source, 'actual-NB12', 'exec'), scope)
            cell.outputs = [nbformat.v4.new_output('stream', name='stdout', text=stream.getvalue())] + outputs
            cell.execution_count = 1
    return notebook, scope


class TestPhase14Summary(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Reuse the existing *actual* NB09/10/11 fixture, not a manually fabricated G5.
        import test_phase13_finalization as producer
        cls.directory = tempfile.TemporaryDirectory()
        cls.evidence = Path(cls.directory.name)
        with patch.dict(os.environ, {'PUBG_PHASE13_EVIDENCE_DIR': str(cls.evidence)}):
            producer.TestPhase13Finalization().test_actual_notebook_release_guards_resume_immutability_and_portability()
        cls.manifest = cls.evidence/'release/final_results_manifest.json'

    @classmethod
    def tearDownClass(cls):
        cls.directory.cleanup()

    def test_actual_12_sections_read_only_and_independent_workspace(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            snapshot = workspace/'selected_release'
            shutil.copytree(self.manifest.parent, snapshot)
            unrelated = workspace/'artifacts/checkpoints/checkpoint_manifest.json'
            unrelated.parent.mkdir(parents=True)
            atomic_write_json(unrelated, {'stages': {'notebook/03_build_player_match.ipynb': {'status': 'running'}}})
            before = fingerprints(workspace)
            notebook, scope = execute_summary(snapshot/self.manifest.name)
            self.assertEqual(fingerprints(workspace), before)
            self.assertEqual([view['section'] for view in scope['summary_views']], list(range(1, 13)))
            self.assertTrue(all(view['tables'] for view in scope['summary_views']))
            self.assertFalse((workspace/'data').exists())
            rendered = '\n'.join(o.get('data', {}).get('text/html', '') + o.get('data', {}).get('text/markdown', '')
                for c in notebook.cells for o in c.get('outputs', []))
            for term in ['fixture_locked', 'Grade C', 'not_in_release', 'Spearman=', 'delta MAE=', 'Run', 'SHA']:
                self.assertIn(term, rendered)
            self.assertEqual(sum('image/png' in o.get('data', {}) for c in notebook.cells for o in c.get('outputs', [])), 1)
            evidence = os.environ.get('PUBG_PHASE14_EVIDENCE_DIR')
            if evidence:
                destination = Path(evidence)
                destination.mkdir(parents=True, exist_ok=True)
                nbformat.write(notebook, destination/'12_fixture.ipynb')
                from nbconvert import HTMLExporter
                html, _ = HTMLExporter().from_notebook_node(notebook)
                (destination/'12_fixture.html').write_text(html, encoding='utf-8')
                shutil.copytree(snapshot, destination/'release', dirs_exist_ok=True)

    def test_missing_corrupt_legacy_completeness_and_fixture_guards(self):
        with self.assertRaisesRegex(ValueError, 'not an official'):
            execute_summary(self.manifest, allow_fixture=False)
        with tempfile.TemporaryDirectory() as directory:
            copied = Path(directory)/'release'
            shutil.copytree(self.manifest.parent, copied)
            path = copied/self.manifest.name
            original = read_json(path)
            table = copied/original['tables']['rq1/summary_table']['path']
            table.write_text('corrupt\n', encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'integrity/completeness'):
                execute_summary(path)
            shutil.copy2(self.manifest.parent/original['tables']['rq1/summary_table']['path'], table)
            changed = copy.deepcopy(original)
            changed['required_matrix'] = [r for r in changed['required_matrix'] if r['component'] != 'RQ1']
            changed['manifest_hash'] = hash_dict({k: v for k, v in changed.items() if k != 'manifest_hash'})
            atomic_write_json(path, changed)
            with self.assertRaisesRegex(ValueError, 'coverage missing'):
                execute_summary(path)
            changed = copy.deepcopy(original)
            changed['required_matrix'] = [r for r in changed['required_matrix'] if r['component'] != 'p1_ols_direct_survival']
            changed['manifest_hash'] = hash_dict({k: v for k, v in changed.items() if k != 'manifest_hash'})
            atomic_write_json(path, changed)
            with self.assertRaisesRegex(ValueError, 'model coverage missing'):
                execute_summary(path)
            atomic_write_json(path, {'format_version': '3.1'})
            with self.assertRaisesRegex(ValueError, 'format 4.0'):
                execute_summary(path)
            with self.assertRaises(FileNotFoundError):
                execute_summary(copied/'missing.json')

    def test_findings_values_privacy_and_non_report_ready_figure(self):
        release = load_locked_release(self.manifest, allow_fixture=True)
        findings = key_findings(release)
        self.assertEqual(len(findings), 52)
        first = findings.iloc[0]
        source = pd.read_csv(release['root']/release['manifest']['tables'][first['Nguồn bảng']]['path']).iloc[0]
        self.assertIn(f"{source.spearman_rho:.4g}", first['Phát biểu từ số đo'])
        self.assertEqual(first['N dòng'], source.n_observations)
        private = public_frame(pd.DataFrame({'player_name': ['PRIVATE_PLAYER_SENTINEL'], 'value': [3]}))
        self.assertNotIn('PRIVATE_PLAYER_SENTINEL', private.to_string())
        self.assertNotIn('PRIVATE_PLAYER_SENTINEL', metadata_frame({'player_name': 'PRIVATE_PLAYER_SENTINEL', 'players': 4}).to_string())
        release['fixture'] = False  # Test display policy, NOT a production G5 approval/publication.
        from src.evaluation.summary import render_summary_section
        captured = []
        with patch('IPython.display.display', side_effect=captured.append):
            view = render_summary_section(release, 10)
        self.assertEqual(view['figures'], [])
        self.assertFalse(any(v.__class__.__name__ == 'Image' for v in captured))
        for status in ('blocked', 'resource_limited', 'failed'):
            release['manifest']['required_matrix'].append({'component': 'fixture_optional_'+status,
                'required': False, 'status': status, 'reason': 'fixture injected '+status, 'run_id': None})
        with patch('IPython.display.display', side_effect=captured.append):
            render_summary_section(release, 12)
        text = '\n'.join(v.to_string() for v in captured if isinstance(v, pd.DataFrame))
        for status in ('blocked', 'resource_limited', 'failed'):
            self.assertIn('fixture injected '+status, text)

    def test_fresh_process_without_raw_config_or_checkpoint(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            snapshot = workspace/'portable_release'
            shutil.copytree(self.manifest.parent, snapshot)
            before = fingerprints(workspace)
            code = "import sys; sys.path[:0]=sys.argv[1:3]; from test_phase14_summary import execute_summary; n,s=execute_summary(sys.argv[3]); print('SECTION_COUNT',len(s['summary_views']))"
            result = subprocess.run([sys.executable, '-X', 'utf8', '-c', code, str(ROOT), str(ROOT/'tests'), str(snapshot/self.manifest.name)],
                cwd=workspace, capture_output=True, text=True, encoding='utf-8',
                env={**os.environ, 'PYTHONDONTWRITEBYTECODE': '1'}, timeout=60)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn('SECTION_COUNT 12', result.stdout)
            self.assertEqual(fingerprints(workspace), before)
            self.assertFalse((workspace/'configs').exists())


if __name__ == '__main__':
    unittest.main()
