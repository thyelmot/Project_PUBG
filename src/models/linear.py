from typing import Any, Dict, List, Optional
import numpy as np
from sklearn.base import BaseEstimator, RegressorMixin
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LinearRegression, SGDRegressor
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler


class LinearModelWrapper(BaseEstimator, RegressorMixin):
    """Encapsulates a pipeline: SimpleImputer(mean) -> StandardScaler -> LinearRegression / SGDRegressor."""

    def __init__(
        self,
        model_type: str = "exact",  # "exact" or "sgd"
        alpha: float = 0.0001,
        max_iter: int = 1000,
        random_state: int = 42,
    ) -> None:
        self.model_type = model_type
        self.alpha = alpha
        self.max_iter = max_iter
        self.random_state = random_state
        self.pipeline: Optional[Pipeline] = None
        self._build_pipeline()

    def _build_pipeline(self) -> None:
        if self.model_type == "exact":
            reg = LinearRegression()
        else:
            reg = SGDRegressor(
                loss="squared_error",
                penalty="l2",
                alpha=self.alpha,
                max_iter=self.max_iter,
                random_state=self.random_state,
            )

        self.pipeline = Pipeline([
            ("imputer", SimpleImputer(strategy="mean")),
            ("scaler", StandardScaler()),
            ("regressor", reg),
        ])

    def fit(self, X: np.ndarray, y: np.ndarray) -> "LinearModelWrapper":
        if self.pipeline is None:
            self._build_pipeline()
        self.pipeline.fit(X, y)
        return self

    def predict(self, X: np.ndarray) -> np.ndarray:
        if self.pipeline is None:
            raise ValueError("Model pipeline is not fitted.")
        return self.pipeline.predict(X)

    @property
    def coefficients(self) -> np.ndarray:
        reg = self.pipeline.named_steps["regressor"]
        return getattr(reg, "coef_", np.array([]))

    @property
    def intercept(self) -> float:
        reg = self.pipeline.named_steps["regressor"]
        return float(getattr(reg, "intercept_", 0.0))
