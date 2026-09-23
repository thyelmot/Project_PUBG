from typing import Optional
import numpy as np
from sklearn.base import BaseEstimator, RegressorMixin
from sklearn.ensemble import HistGradientBoostingRegressor, RandomForestRegressor
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline


class HistGradientBoostingWrapper(BaseEstimator, RegressorMixin):
    """Modern, high-performance tree boosting with native NaN support."""

    def __init__(
        self,
        max_iter: int = 100,
        learning_rate: float = 0.1,
        max_leaf_nodes: int = 31,
        random_state: int = 42,
    ) -> None:
        self.max_iter = max_iter
        self.learning_rate = learning_rate
        self.max_leaf_nodes = max_leaf_nodes
        self.random_state = random_state
        self.model: Optional[HistGradientBoostingRegressor] = None

    def fit(self, X: np.ndarray, y: np.ndarray) -> "HistGradientBoostingWrapper":
        self.model = HistGradientBoostingRegressor(
            max_iter=self.max_iter,
            learning_rate=self.learning_rate,
            max_leaf_nodes=self.max_leaf_nodes,
            random_state=self.random_state,
        )
        self.model.fit(X, y)
        return self

    def predict(self, X: np.ndarray) -> np.ndarray:
        if self.model is None:
            raise ValueError("Model is not fitted.")
        return self.model.predict(X)


class RandomForestWrapper(BaseEstimator, RegressorMixin):
    """Random Forest regressor pipeline with mean imputation."""

    def __init__(
        self,
        n_estimators: int = 100,
        max_depth: Optional[int] = 15,
        random_state: int = 42,
    ) -> None:
        self.n_estimators = n_estimators
        self.max_depth = max_depth
        self.random_state = random_state
        self.pipeline: Optional[Pipeline] = None

    def fit(self, X: np.ndarray, y: np.ndarray) -> "RandomForestWrapper":
        self.pipeline = Pipeline([
            ("imputer", SimpleImputer(strategy="mean")),
            ("regressor", RandomForestRegressor(
                n_estimators=self.n_estimators,
                max_depth=self.max_depth,
                random_state=self.random_state,
                n_jobs=-1,
            )),
        ])
        self.pipeline.fit(X, y)
        return self

    def predict(self, X: np.ndarray) -> np.ndarray:
        if self.pipeline is None:
            raise ValueError("Model pipeline is not fitted.")
        return self.pipeline.predict(X)
