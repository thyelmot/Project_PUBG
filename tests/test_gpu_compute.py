"""Routing/failure tests run anywhere; real CUDA parity is explicitly opt-in."""
import os
import unittest
from unittest.mock import patch, Mock
import numpy as np
from sklearn.metrics import adjusted_rand_score
from src.models.compute import compute_info, make_kmeans, make_linear
from src.models.linear import LinearModelWrapper


class TestGPUCompute(unittest.TestCase):
    def test_missing_gpu_stops_before_training_and_cpu_stays_available(self):
        with patch('src.models.compute.importlib.util.find_spec', return_value=None):
            for operation in (lambda: compute_info('cuda'), lambda: make_kmeans('cuda', n_clusters=2),
                              lambda: LinearModelWrapper(device='cuda')):
                with self.assertRaisesRegex(RuntimeError, 'GPU requires'):
                    operation()
        with patch('src.models.compute.importlib.util.find_spec', return_value=None), \
             patch('src.models.compute.subprocess.run', side_effect=FileNotFoundError), \
             patch('src.models.compute.subprocess.check_call') as install:
            with self.assertRaisesRegex(RuntimeError, 'switch account'):
                compute_info('cuda', install=True)
            install.assert_not_called()
        self.assertEqual(compute_info('cpu')['device'], 'cpu')
        with self.assertRaises(ValueError):
            compute_info('unknown')

    def test_cuda_constructors_use_cuml_without_cpu_fallback(self):
        cluster, linear = Mock(), Mock()
        with patch('src.models.compute.compute_info'), patch.dict('sys.modules', {'cuml.cluster': cluster, 'cuml.linear_model': linear}):
            make_kmeans('cuda', n_clusters=3, random_state=42, n_init=10)
            cluster.KMeans.assert_called_once_with(init='k-means++', max_iter=300, tol=1e-4,
                output_type='numpy', n_clusters=3, random_state=42, n_init=10)
            make_linear('cuda')
            linear.LinearRegression.assert_called_once_with(algorithm='svd', fit_intercept=True, output_type='numpy')

    @unittest.skipUnless(os.environ.get('PUBG_TEST_GPU') == '1', 'Requires real CUDA/cuML 26.08; set PUBG_TEST_GPU=1 on Colab')
    def test_real_gpu_models_and_cpu_numerical_agreement(self):
        self.assertEqual(compute_info('cuda')['device'], 'cuda')
        rng = np.random.RandomState(42)
        X = rng.normal(size=(120, 4))
        y = X @ np.array([2., -3., .5, 1.]) + 4.
        X[0, 0] = np.nan
        cpu, gpu = LinearModelWrapper(device='cpu'), LinearModelWrapper(device='cuda')
        cpu.fit(X, y)
        gpu.fit(X, y)
        np.testing.assert_allclose(cpu.predict(X), gpu.predict(X), atol=1e-6, rtol=1e-6)
        Z = np.vstack([rng.normal(-10, .1, (40, 3)), rng.normal(10, .1, (40, 3))])
        a = make_kmeans('cpu', n_clusters=2, random_state=42, n_init=10).fit_predict(Z)
        b = make_kmeans('cuda', n_clusters=2, random_state=42, n_init=10).fit_predict(Z)
        self.assertEqual(adjusted_rand_score(a, b), 1.)


if __name__ == '__main__':
    unittest.main()
