"""Explicit CPU/cuML backends. A requested GPU never silently falls back."""
import importlib.util
import subprocess
import sys
import sklearn
from sklearn.cluster import KMeans


def compute_info(device='cpu', install=False):
    if device == 'cpu':
        return {'device': 'cpu', 'backend': 'sklearn', 'version': sklearn.__version__}
    if device != 'cuda':
        raise ValueError("device must be 'cpu' or 'cuda'")
    if importlib.util.find_spec('cuml') is None:
        if not install:
            raise RuntimeError('GPU requires cuML. On Colab CUDA 12 install cuml-cu12==26.8.* and restart the session.')
        try:
            subprocess.run(['nvidia-smi', '-L'], check=True, capture_output=True, timeout=20)
        except (OSError, subprocess.SubprocessError) as error:
            raise RuntimeError('GPU unavailable. Select T4 in Colab. If quota is exhausted, stop and switch account using the shared Drive shortcut.') from error
        subprocess.check_call([sys.executable, '-m', 'pip', 'install', 'cuml-cu12==26.8.*'])
        importlib.invalidate_caches()
    try:
        import cupy as cp
        import cuml
        if tuple(int(p) for p in cuml.__version__.split('.')[:2]) != (26, 8):
            raise RuntimeError('This GPU implementation is pinned to cuML 26.08; reinstall cuml-cu12==26.8.*')
        if cp.cuda.runtime.getDeviceCount() < 1:
            raise RuntimeError('No CUDA device')
        cp.asarray([1.0], dtype=cp.float64).sum().item()
        props = cp.cuda.runtime.getDeviceProperties(cp.cuda.Device().id)
        name = props['name']
        return {'device': 'cuda', 'backend': 'cuml', 'version': cuml.__version__,
                'gpu': name.decode() if isinstance(name, bytes) else str(name),
                'cuda_runtime': cp.cuda.runtime.runtimeGetVersion(), 'dtype': 'float64'}
    except Exception as error:
        raise RuntimeError('CUDA/cuML unavailable or incompatible. Stop; check T4 and restart after installation. If quota is exhausted, switch account and remount the same shared project. No CPU fallback.') from error


def make_kmeans(device='cpu', **kwargs):
    if device == 'cpu':
        return KMeans(**kwargs)
    compute_info(device)
    from cuml.cluster import KMeans as GPUKMeans
    return GPUKMeans(init='k-means++', max_iter=300, tol=1e-4, output_type='numpy', **kwargs)


def make_linear(device='cpu', fit_intercept=True):
    if device == 'cpu':
        from sklearn.linear_model import LinearRegression
        return LinearRegression(fit_intercept=fit_intercept)
    compute_info(device)
    from cuml.linear_model import LinearRegression
    return LinearRegression(algorithm='svd', fit_intercept=fit_intercept, output_type='numpy')
