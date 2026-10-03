from typing import Any, Dict, List, Optional
import numpy as np
from sklearn.base import BaseEstimator, RegressorMixin
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LinearRegression, SGDRegressor
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler, FunctionTransformer
from src.models.compute import make_linear


def log1p_columns(values, indices=()):
    transformed=np.asarray(values,dtype=float).copy()
    if indices:
        block=transformed[:,list(indices)]
        if (block[np.isfinite(block)]<0).any():
            raise ValueError("Configured log1p features must be nonnegative")
        transformed[:,list(indices)]=np.log1p(block)
    return transformed


class LinearModelWrapper(BaseEstimator, RegressorMixin):
    """Encapsulates a pipeline: SimpleImputer(mean) -> StandardScaler -> LinearRegression / SGDRegressor."""

    def __init__(
        self,
        model_type: str = "exact",  # "exact" or "sgd"
        alpha: float = 0.0001,
        max_iter: int = 1000,
        random_state: int = 42,
        device: str = "cpu",
        fit_intercept: bool = True,
        standardize: bool = True,
        add_indicator: bool = False,
        log_indices: tuple = (),
    ) -> None:
        self.model_type = model_type
        self.alpha = alpha
        self.max_iter = max_iter
        self.random_state = random_state
        self.device = device
        self.fit_intercept = fit_intercept
        self.standardize = standardize
        self.add_indicator = add_indicator
        self.log_indices = log_indices
        self.pipeline: Optional[Pipeline] = None
        self._build_pipeline()

    def _build_pipeline(self) -> None:
        if self.model_type == "exact":
            reg = make_linear(self.device, fit_intercept=self.fit_intercept)
        elif self.model_type == "sgd":
            if self.device != 'cpu':
                raise ValueError('SGD GPU is not implemented; exact linear regression supports cuda')
            reg = SGDRegressor(
                loss="squared_error",
                penalty="l2",
                alpha=self.alpha,
                max_iter=self.max_iter,
                random_state=self.random_state,
                fit_intercept=self.fit_intercept,
            )
        else:
            raise ValueError("Unknown linear model_type; use exact or an explicitly registered sgd recipe")

        self.pipeline = Pipeline([
            ("log1p", FunctionTransformer(log1p_columns,kw_args={"indices":self.log_indices})),
            ("imputer", SimpleImputer(strategy="mean", keep_empty_features=True, add_indicator=self.add_indicator)),
            ("scaler", StandardScaler() if self.standardize else "passthrough"),
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
