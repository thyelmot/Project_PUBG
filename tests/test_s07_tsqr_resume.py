"""Frozen b663 S01-S07 import; actual CPU fixtures, not evidence of CUDA/full-source execution."""
import copy
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

import nbformat
from nbclient import NotebookClient

from src.io import Context,digest,read_json,write_json
from src.kaggle_runtime import (S07_PRODUCER_511,prepare_handoff,restore_handoff,
    restore_s07_tsqr_handoff,source_fingerprint,verify_handoff)
from test_data_features import ROOT,fixture,write_config


class S07TSQRResume(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory(prefix='pubg-frozen-s07-')
        cls.base=Path(cls.temp.name);cls.source=cls.base/'original';cls.source.mkdir()
        cfg=fixture(cls.source);cfg['storage']['layout']='normalized_v1'
        cfg['rq2']['decision_mode']='auto';cfg['rq3']['decision_mode']='auto'
        write_config(cls.source,cfg)
        with zipfile.ZipFile(ROOT/'tests/fixtures/audited_s07_producer_511.zip') as archive:
            for name in archive.namelist():
                if name.startswith('src/'):(cls.source/name).write_bytes(archive.read(name))
        if source_fingerprint(cls.source)!=S07_PRODUCER_511:raise AssertionError('Frozen S07 producer differs')
        script='''from pathlib import Path
import sys
sys.path.insert(0,sys.argv[1])
from src.io import Context,write_json
from src.preprocessing import ingest,clean_split
from src.features import base_features,combat_timing
from src.analysis import eda,relationship,clustering
from src.kaggle_runtime import prepare_handoff
ctx=Context(Path(sys.argv[1]),'development',progress=lambda _:None)
for s,f in zip(('S01','S02','S03','S04','S05','S06','S07'),(ingest,clean_split,base_features,combat_timing,eda,relationship,clustering)):ctx.run(s,f)
# A labelled nested-history marker tests preservation without pretending it is a real cloud import.
records=ctx.manifest();records['S01']['producer_import']={'fixture_history':'preserve','recomputed':False}
write_json(records,ctx.manifest_path)
prepare_handoff(ctx)
'''
        result=subprocess.run([sys.executable,'-B','-c',script,str(cls.source)],cwd=cls.source,
            env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1','PYTHONUTF8':'1','PYTHONIOENCODING':'utf-8',
                'OMP_NUM_THREADS':'1','OPENBLAS_NUM_THREADS':'1','MKL_NUM_THREADS':'1'},
            capture_output=True,text=True,encoding='utf-8',timeout=240)
        if result.returncode:raise AssertionError(result.stderr)
        cls.manifest=read_json(cls.source/'handoff_development.json')
        cls.raw=cls.base/'raw-remount';shutil.copytree(cls.source/'raw_fixture',cls.raw)
        cls.original=cls.hashes(cls.source)

    @classmethod
    def tearDownClass(cls):cls.temp.cleanup()

    @staticmethod
    def hashes(root):return {p.relative_to(root).as_posix():digest(p) for p in root.rglob('*') if p.is_file()}

    def restore(self,target,**kw):
        return restore_handoff(self.source,target,'development',self.raw,'quangthinng/pubg-v3/versions/6',
            code_input=ROOT,allow_s07_tsqr=True,**kw)

    def test_verified_import_preserves_every_artifact_model_history_and_never_calls_upstream(self):
        with tempfile.TemporaryDirectory(prefix='pubg-tsqr-import-') as folder:
            target=Path(folder)/'project';self.restore(target)
            ctx=Context(target,'development',progress=lambda _:None)
            self.assertEqual(ctx.cfg['rq3']['solver'],'tsqr')
            for stage,original in self.manifest['stages'].items():
                ctx.run(stage,lambda _:self.fail('An upstream stage was recomputed'))
                record=ctx.require(stage)
                self.assertEqual(record['execution_import']['signature'],original['signature'])
                self.assertFalse(record['execution_import']['recomputed'])
                for key,value in original.items():
                    if key not in {'artifacts','signature'}:self.assertEqual(record[key],value,key)
                for artifact in original['artifacts']:
                    self.assertEqual(digest(target/artifact['path']),artifact['sha256'])
            self.assertTrue(list(ctx.path('models').glob('kmeans_*.joblib')))
            receipt=read_json(ctx.out/'provenance/s07_tsqr_resume.json')
            self.assertEqual(receipt['recomputed_stages'],[])
            self.assertEqual(receipt['producer_handoff'],self.manifest)
            self.assertEqual(receipt['verification']['verified_stages'],[f'S{i:02d}' for i in range(1,8)])
            prepare_handoff(ctx);verify_handoff(target,'development','team/new/versions/1')
            second=Path(folder)/'second'
            restore_handoff(target,second,'development',self.raw,'team/new/versions/1')
            Context(second,'development').require('S07')
            self.assertEqual(self.hashes(self.source),self.original)

    def test_opt_in_software_scope_code_disk_and_existing_target_fail_closed(self):
        with tempfile.TemporaryDirectory(prefix='pubg-tsqr-reject-') as folder:
            target=Path(folder)/'project'
            with self.assertRaisesRegex(ValueError,'CODE_INPUT'):
                restore_handoff(self.source,target,'development',self.raw,'team/book/versions/6',allow_s07_tsqr=True)
            with self.assertRaises(ValueError):self.restore(target,allow_cpu_gpu=True)
            altered={**self.manifest['software'],'numpy':'different'}
            with patch('src.kaggle_runtime.software_versions',return_value=altered):
                with self.assertRaisesRegex(RuntimeError,'identical'):self.restore(target)
            self.assertFalse(target.exists())
            _,evidence=verify_handoff(self.source,'development','team/book/versions/6')
            for change in ('partial','downstream','model','lock'):
                bad=copy.deepcopy(self.manifest)
                if change=='partial':bad['stages']['S07']['status']='failed'
                elif change=='downstream':bad['stages']['S08']={'status':'completed'}
                else:bad['entries'].append({'path':'outputs/development/'+('models/unknown.joblib' if change=='model' else 'checkpoints/S07.lock')})
                with self.subTest(change=change),self.assertRaises(ValueError):
                    restore_s07_tsqr_handoff(self.source,target,'development',self.raw,'team/book/versions/6',ROOT,bad,evidence)
            with patch('src.kaggle_runtime.shutil.disk_usage',return_value=shutil._ntuple_diskusage(10,10,0)):
                with self.assertRaises(MemoryError):self.restore(target)
            self.assertFalse(target.exists())
            target.mkdir();(target/'keep.txt').write_text('old result',encoding='utf-8')
            with self.assertRaisesRegex(ValueError,'never overwrite'):self.restore(target)
            self.assertEqual((target/'keep.txt').read_text(),'old result')

    def test_tampered_model_raw_code_and_failed_copy_do_not_publish_or_touch_original(self):
        with tempfile.TemporaryDirectory(prefix='pubg-tsqr-corrupt-') as folder:
            target=Path(folder)/'project';bad=Path(folder)/'bad';shutil.copytree(self.source,bad)
            model=next((bad/'outputs/development/models').glob('kmeans_*.joblib'))
            model.write_bytes(model.read_bytes()+b'changed')
            with self.assertRaises((RuntimeError,ValueError)):
                restore_handoff(bad,target,'development',self.raw,'team/book/versions/6',code_input=ROOT,allow_s07_tsqr=True)
            self.assertFalse(target.exists())
            raw=Path(folder)/'raw';shutil.copytree(self.raw,raw)
            csv=next(raw.glob('*.csv'));csv.write_bytes(csv.read_bytes()+b'\n')
            with self.assertRaisesRegex(RuntimeError,'verification failed'):
                restore_handoff(self.source,target,'development',raw,'team/book/versions/6',code_input=ROOT,allow_s07_tsqr=True)
            self.assertFalse(target.exists())
            with patch('src.kaggle_runtime.publish',side_effect=OSError('copy failed')):
                with self.assertRaises(OSError):self.restore(target)
            self.assertFalse(target.exists());self.assertFalse(list(target.parent.glob('pubg-s07-tsqr-resume-*')))
            from src.kaggle_runtime import publish
            moving=Path(folder)/'moving-raw';shutil.copytree(self.raw,moving)
            mutated=False
            def mutate_during_copy(source,destination,**kwargs):
                nonlocal mutated
                if not mutated:
                    mutated=True;csv=next(moving.glob('*.csv'));csv.write_bytes(csv.read_bytes()+b'\n')
                return publish(source,destination,**kwargs)
            with patch('src.kaggle_runtime.publish',side_effect=mutate_during_copy):
                with self.assertRaisesRegex(RuntimeError,'Raw source changed during S07 import'):
                    restore_handoff(self.source,target,'development',moving,'team/book/versions/6',code_input=ROOT,allow_s07_tsqr=True)
            self.assertFalse(target.exists())
            code=Path(folder)/'code';shutil.copytree(ROOT/'src',code/'src')
            (code/'src/modeling.py').write_bytes((code/'src/modeling.py').read_bytes()+b'\n')
            with self.assertRaisesRegex(ValueError,'match the running'):
                restore_handoff(self.source,target,'development',self.raw,'team/book/versions/6',code_input=code,allow_s07_tsqr=True)
            self.assertEqual(self.hashes(self.source),self.original)

    def test_actual_s08_only_notebook_does_not_recompute_prefix_and_can_be_saved(self):
        with tempfile.TemporaryDirectory(prefix='pubg-s08-tsqr-notebook-') as folder:
            target=Path(folder)/'project';nb=nbformat.read(ROOT/'notebooks/PUBG_COURSEWORK.ipynb',as_version=4)
            cells={c.id:c for c in nb.cells}
            cells['parameters'].source+=(f'\nCODE_INPUT={str(ROOT)!r}\nRESUME_INPUT={str(self.source)!r}\n'
                f'PUBG_PROJECT_ROOT={str(target)!r}\nSOURCE_DIRECTORY={str(self.raw)!r}\nEXECUTION_MODE="development"\n'
                'SOURCE_VERSION=None\nSOURCE_LICENSE=""\nRUN_GPU_SMOKE=False\nSOURCE_TIME_UNIT_STATUS=""\n'
                'SOURCE_TIME_UNIT_ASSUMPTION_APPROVED=None\nSOURCE_TIME_UNIT_ASSUMPTION_SCOPE=""\n')
            guard=nbformat.v4.new_code_cell('def forbidden_producer(ctx):\n    raise AssertionError("Upstream recomputation")\n'
                'STAGES.update({s:forbidden_producer for s in STAGES if s!="S08"})',id='test-no-recomputation')
            nb.cells.insert(nb.cells.index(cells['section-runner'])+1,guard)
            NotebookClient(nb,timeout=300,kernel_name='python3',resources={'metadata':{'path':folder}}).execute()
            ctx=Context(target,'development');ctx.require('S08')
            self.assertEqual(set(ctx.manifest()),{f'S{i:02d}' for i in range(1,9)})
            for stage,record in self.manifest['stages'].items():
                for artifact in record['artifacts']:self.assertEqual(digest(target/artifact['path']),artifact['sha256'])
            before={p.name:digest(p) for p in ctx.path('models').glob('*.joblib')}
            from src.modeling import prediction
            ctx.run('S08',prediction)
            self.assertEqual(before,{p.name:digest(p) for p in ctx.path('models').glob('*.joblib')})
            prepare_handoff(ctx);verify_handoff(target,'development','team/s08/versions/1')
            self.assertEqual(self.hashes(self.source),self.original)


if __name__=='__main__':unittest.main()
