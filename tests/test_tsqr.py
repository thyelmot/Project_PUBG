"""Blocked OLS parity, rank/NULL handling and integration; CPU tests are not CUDA evidence."""
import tempfile
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import joblib
import numpy as np
import pandas as pd
from sklearn.dummy import DummyRegressor
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LinearRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler,FunctionTransformer

from src import modeling
from src.io import Context
from test_data_features import fixture,run_features,write_config


class TSQR(unittest.TestCase):
    def test_cuda_backend_without_divide_where_handles_full_and_zero_rank(self):
        # NumPy-backed API simulation only; do not claim real CUDA execution.
        def reject_where(*args,**kwargs):
            if 'where' in kwargs:raise TypeError("Wrong arguments {'where': array}")
            return np.divide(*args,**kwargs)
        backend=SimpleNamespace(asarray=np.asarray,float64=np.float64,concatenate=np.concatenate,
            zeros_like=np.zeros_like,asnumpy=np.asarray,divide=reject_where)
        rng=np.random.default_rng(42);full=rng.normal(size=(48,3))
        for x,y in ((full,full@np.array([2.,-1.,.5])+3),
                    (np.ones((48,3)),np.full(48,7.)),
                    (np.column_stack((full[:,0],full[:,0]*2)),full[:,0]+3)):
            with self.subTest(columns=x.shape[1]),np.errstate(all='raise'), \
                 patch('src.modeling.qr_backend',return_value=backend), \
                 patch('src.modeling.checked_factor',side_effect=lambda xp,op,a,**kw:getattr(np.linalg,op)(a,**kw)):
                actual=modeling.TSQROLS('cuda').fit_batches([(x[:23],y[:23]),(x[23:],y[23:])],x.mean(0),float(y.mean()),len(x))
                expected=LinearRegression().fit(x,y)
                self.assertEqual(actual.rank_,expected.rank_)
                np.testing.assert_allclose(actual.predict(x),expected.predict(x),rtol=1e-9,atol=1e-10)

    def bundle(self,root,x,y):
        np.save(root/'X.npy',x.astype(np.float64));np.save(root/'y.npy',y.astype(np.float64))
        return {'X':str(root/'X.npy'),'y':str(root/'y.npy'),'rows':len(x),'columns':list(x.columns)}

    def reference(self,x,y,logs,kind):
        model=LinearRegression() if kind=='linear' else DummyRegressor(strategy=kind)
        return Pipeline([('log',FunctionTransformer(modeling.log_features,kw_args={'columns':logs})),
            ('imputer',SimpleImputer(strategy='mean',add_indicator=True,keep_empty_features=True)),
            ('scaler',StandardScaler()),('model',model)]).fit(x,y)

    def test_global_preprocessing_and_ols_match_dense_across_50000_boundary(self):
        rng=np.random.default_rng(42);x=pd.DataFrame(rng.normal(size=(100007,5)),columns=list('abcde'))
        x['a']=np.nan;x['b']=np.abs(x.b);x.loc[::13,'c']=np.nan;x['d']=7.
        y=2*x.b.to_numpy()-np.nan_to_num(x.c.to_numpy())+rng.normal(size=len(x))*.01+3
        with tempfile.TemporaryDirectory(prefix='pubg-tsqr-parity-') as folder:
            root=Path(folder);bundle=self.bundle(root,x,y)
            shapes=[];factor=modeling.checked_factor
            def track_factor(xp,operation,array,**options):
                shapes.append((operation,array.shape))
                return factor(xp,operation,array,**options)
            with patch('src.modeling.checked_factor',side_effect=track_factor):
                actual=modeling.block_pipeline(bundle,['b'],'cpu','linear')
            self.assertTrue(shapes)
            self.assertLessEqual(max(shape[0] for operation,shape in shapes),50000)
            self.assertLessEqual(max(shape[0] for operation,shape in shapes if operation=='svd'),11)
            expected=self.reference(x,y,['b'],'linear')
            for name in ('statistics_',):
                np.testing.assert_allclose(getattr(actual.named_steps['imputer'],name),getattr(expected.named_steps['imputer'],name),rtol=1e-9,atol=1e-10)
            np.testing.assert_array_equal(actual.named_steps['imputer'].get_feature_names_out(),expected.named_steps['imputer'].get_feature_names_out())
            for name in ('mean_','var_','scale_'):
                np.testing.assert_allclose(getattr(actual.named_steps['scaler'],name),getattr(expected.named_steps['scaler'],name),rtol=1e-9,atol=1e-10)
            np.testing.assert_allclose(actual.predict(x),expected.predict(x),rtol=1e-9,atol=1e-10)
            np.testing.assert_allclose(actual.named_steps['model'].coef_,expected.named_steps['model'].coef_,rtol=1e-8,atol=1e-9)
            path=root/'model.joblib';joblib.dump(actual,path)
            np.testing.assert_array_equal(actual.predict(x.iloc[:53]),joblib.load(path).predict(x.iloc[:53]))
            self.assertEqual(actual.named_steps['model'].training_rows_,len(x))

    def test_original_row_count_controls_rank_and_minimum_norm_solution(self):
        rng=np.random.default_rng(8);n=100007
        x=rng.normal(size=(n,2));x[:,1]*=1e-12;y=x[:,0]+x[:,1]
        offset=x.mean(axis=0);ym=float(y.mean())
        batches=((x[s:s+50000],y[s:s+50000]) for s in range(0,n,50000))
        actual=modeling.TSQROLS().fit_batches(batches,offset,ym,n)
        expected=LinearRegression().fit(x,y)
        self.assertEqual(actual.rank_,expected.rank_)
        self.assertEqual(actual.rank_,1)
        np.testing.assert_allclose(actual.predict(x),expected.predict(x),rtol=1e-9,atol=1e-10)
        for x,y in ((np.ones((7,3)),np.full(7,4.)),(np.array([[1.,2.,3.]]),np.array([8.])),
                    (np.column_stack((np.arange(9.),np.arange(9.)*2)),np.arange(9.)*3+4)):
            actual=modeling.TSQROLS().fit_batches([(x,y)],x.mean(0),float(y.mean()),len(x))
            expected=LinearRegression().fit(x,y)
            np.testing.assert_allclose(actual.coef_,expected.coef_,rtol=1e-9,atol=1e-10)
            np.testing.assert_allclose(actual.predict(x),expected.predict(x),rtol=1e-9,atol=1e-10)
            np.testing.assert_allclose(modeling.TSQROLS().fit(x,y).predict(x),expected.predict(x),rtol=1e-9,atol=1e-10)

    def test_baselines_exact_external_quantiles_and_test_only_missing(self):
        rng=np.random.default_rng(4);x=pd.DataFrame({'x':rng.normal(size=100007),'z':np.nan})
        y=(np.arange(len(x))%17).astype(float)+.125
        with tempfile.TemporaryDirectory(prefix='pubg-tsqr-baselines-') as folder:
            root=Path(folder);fixture(root);ctx=Context(root,'development');bundle=self.bundle(root,x,y)
            meta=root/'metadata.parquet';pd.DataFrame({'y':y}).to_parquet(meta,index=False)
            bundle.update(metadata=str(meta),target='y')
            probabilities=[0,.33,.5,.67,1]
            with ctx.disk_db() as con:quantiles=modeling.exact_target_quantiles(con,bundle,probabilities)
            np.testing.assert_allclose(quantiles,np.quantile(y,probabilities),rtol=1e-12,atol=1e-12)
            for kind in ('mean','median'):
                actual=modeling.block_pipeline(bundle,[],'cpu',kind,quantiles[2]);expected=self.reference(x,y,[],kind)
                np.testing.assert_allclose(actual.predict(x.iloc[:91]),expected.predict(x.iloc[:91]),rtol=1e-12,atol=1e-12)
            model=modeling.block_pipeline(bundle,[],'cpu','linear')
            probe=x.iloc[:3].copy();probe.loc[:,'x']=np.nan;probe.loc[:,'z']=12.
            expected=self.reference(x,y,[],'linear')
            np.testing.assert_allclose(model.predict(probe),expected.predict(probe),rtol=1e-9,atol=1e-10)

    def test_invalid_blocks_no_cuda_fallback_and_bounded_estimates(self):
        with patch.dict('sys.modules',{'cupy':None}):
            with self.assertRaisesRegex(RuntimeError,'no CPU fallback'):modeling.qr_backend('cuda')
        with self.assertRaises(ValueError):modeling.regression_solver('sgd')
        for n in (1000000,47000000):
            self.assertLess(modeling.fit_memory_bytes(n,19,'tsqr'),2**30)
            self.assertLess(modeling.regression_vram_bytes(n,19,'tsqr'),2*2**30)
        self.assertGreater(modeling.fit_memory_bytes(47000000,19),30*2**30)
        with self.assertRaises(ValueError):modeling.TSQROLS().fit_batches([(np.ones((2,2)),np.ones(2))],np.zeros(2),0,3)
        with self.assertRaises(ValueError):modeling.TSQROLS().fit_batches([(np.array([[np.inf]]),np.ones(1))],np.zeros(1),0,1)
        with tempfile.TemporaryDirectory(prefix='pubg-tsqr-fail-') as folder:
            root=Path(folder);x=pd.DataFrame({'x':[1.,2.,3.]});bundle=self.bundle(root,x,np.array([1.,np.nan,3.]))
            with self.assertRaises(ValueError):modeling.block_pipeline(bundle,[],'cpu','linear')
            # Closed mmaps must release both files even when traceback retains views.
            Path(bundle['X']).unlink();Path(bundle['y']).unlink()

    def test_whole_s08_keeps_seven_fits_cohorts_predictions_and_g4(self):
        from src.analysis import eda,relationship,clustering
        with tempfile.TemporaryDirectory(prefix='pubg-tsqr-stage-') as folder:
            root=Path(folder);cfg=fixture(root)
            cfg['rq2']['decision_mode']='auto';cfg['rq3']['decision_mode']='auto'
            write_config(root,cfg);ctx=run_features(root)
            for stage,fn in (('S05',eda),('S06',relationship),('S07',clustering)):ctx.run(stage,fn)
            ctx.run('S08',modeling.prediction)
            expected={p.name:pd.read_parquet(p) for p in ctx.path('predictions').glob('*.parquet')}
            upstream={s:r['signature'] for s,r in ctx.manifest().items() if s!='S08'}
            cfg['rq3']['solver']='tsqr';write_config(root,cfg);ctx=Context(root,'development')
            ctx.run('S08',modeling.prediction)
            self.assertEqual(upstream,{s:r['signature'] for s,r in ctx.manifest().items() if s!='S08'})
            for name,reference in expected.items():
                actual=pd.read_parquet(ctx.path('predictions')/name)
                for c in ('row_id','match_id','team_id','split','actual'):pd.testing.assert_series_equal(actual[c],reference[c])
                np.testing.assert_allclose(actual.predicted,reference.predicted,rtol=1e-8,atol=1e-9)
            table=pd.read_csv(ctx.path('tables/model_metrics.csv'))
            self.assertEqual(table.experiment.nunique(),7)
            from src.io import read_json
            self.assertTrue(read_json(ctx.path('manifests/selection.json'))['approved'])
            self.assertEqual(read_json(ctx.path('manifests/s08_execution.json'))['solver'],'tsqr')

    def test_manual_g4_does_not_read_test_or_refit_verified_train_models(self):
        from src.analysis import eda,relationship,clustering
        from src.io import PendingDecision,read_json,digest
        with tempfile.TemporaryDirectory(prefix='pubg-tsqr-g4-') as folder:
            root=Path(folder);cfg=fixture(root);cfg['rq2']['decision_mode']='auto';cfg['rq3']['solver']='tsqr'
            write_config(root,cfg);ctx=run_features(root)
            for stage,fn in (('S05',eda),('S06',relationship),('S07',clustering)):ctx.run(stage,fn)
            with self.assertRaises(PendingDecision):ctx.run('S08',modeling.prediction)
            self.assertFalse(list(ctx.path('predictions').glob('test_*')))
            receipt=read_json(ctx.path('manifests/validation_receipt.json'))
            self.assertFalse(receipt['test_accessed'])
            models={p.name:digest(p) for p in ctx.path('models').glob('*.joblib')}
            cfg['rq3'].update(selection_approved=True,selection_reason='fixture manual G4 only',validation_hash=receipt['validation_hash'])
            write_config(root,cfg);ctx=Context(root,'development')
            with patch('src.modeling.fit_candidate',side_effect=AssertionError('Unexpected refit')):
                ctx.run('S08',modeling.prediction)
            self.assertEqual(models,{p.name:digest(p) for p in ctx.path('models').glob('*.joblib')})
            self.assertTrue(list(ctx.path('predictions').glob('test_*')))


if __name__=='__main__':unittest.main()
