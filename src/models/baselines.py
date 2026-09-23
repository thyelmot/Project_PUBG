from typing import Optional
import numpy as np
from sklearn.base import BaseEstimator, RegressorMixin


class TrainMeanRegressor(BaseEstimator, RegressorMixin):
    """Zero-predictor constant baseline: predicts the mean of the training target."""

    def __init__(self) -> None:
        self.constant_value_: Optional[float] = None

    def fit(self, X: np.ndarray, y: np.ndarray) -> "TrainMeanRegressor":
        valid_y = y[~np.isnan(y)]
        if len(valid_y) == 0:
            raise ValueError("Cannot fit TrainMeanRegressor on all-NaN target.")
        self.constant_value_ = float(np.mean(valid_y))
        return self

    def predict(self, X: np.ndarray) -> np.ndarray:
        if self.constant_value_ is None:
            raise ValueError("Estimator not fitted.")
        n_samples = X.shape[0]
        return np.full(n_samples, self.constant_value_, dtype=np.float64)


class TrainMedianRegressor(BaseEstimator, RegressorMixin):
    """Robust constant baseline: predicts the median of the training target."""

    def __init__(self) -> None:
        self.constant_value_: Optional[float] = None

    def fit(self, X: np.ndarray, y: np.ndarray) -> "TrainMedianRegressor":
        valid_y = y[~np.isnan(y)]
        if len(valid_y) == 0:
            raise ValueError("Cannot fit TrainMedianRegressor on all-NaN target.")
        self.constant_value_ = float(np.median(valid_y))
        return self

    def predict(self, X: np.ndarray) -> np.ndarray:
        if self.constant_value_ is None:
            raise ValueError("Estimator not fitted.")
        n_samples = X.shape[0]
        return np.full(n_samples, self.constant_value_, dtype=np.float64)
