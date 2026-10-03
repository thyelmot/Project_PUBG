"""Separate CPU SGD recipe: bounded matrices, frozen train statistics, external validation."""
import copy
import numpy as np
from sklearn.base import BaseEstimator, RegressorMixin
from sklearn.linear_model import SGDRegressor
from sklearn.preprocessing import StandardScaler
from src.models.linear import log1p_columns


class StreamingSGDWrapper(RegressorMixin, BaseEstimator):
    def __init__(self, loss="squared_error", penalty="l2", alpha=0.0001,
                 max_iter=1000, tol=0.001, random_state=42, standardize=True,
                 add_indicator=False, log_indices=(), batch_size=50000):
        self.loss, self.penalty, self.alpha = loss, penalty, alpha
        self.max_iter, self.tol, self.random_state = max_iter, tol, random_state
        self.standardize, self.add_indicator = standardize, add_indicator
        self.log_indices, self.batch_size = log_indices, batch_size
        self.device = "cpu"

    def _blocks(self, frame, names):
        for start in range(0, len(frame), self.batch_size):
            yield log1p_columns(frame.iloc[start:start+self.batch_size][names].to_numpy(dtype=float), self.log_indices)

    def _impute(self, values):
        missing = np.isnan(values)
        if np.isinf(values).any():
            raise ValueError("Infinite SGD feature")
        result = np.where(missing, self.means_, values)
        return np.column_stack([result, missing[:, self.indicator_indices_]]) if self.add_indicator else result

    def fit_frame(self, train, validation, names, target):
        if self.batch_size < 1 or self.max_iter < 1 or train.empty or validation.empty:
            raise ValueError("SGD requires positive batch/epochs and external train/validation")
        self.feature_names_ = list(names)
        sums, counts = np.zeros(len(names)), np.zeros(len(names), dtype=np.int64)
        for block in self._blocks(train, names):
            if np.isinf(block).any():
                raise ValueError("Infinite SGD feature")
            sums += np.nansum(block, axis=0)
            counts += np.isfinite(block).sum(axis=0)
        self.means_ = np.divide(sums, counts, out=np.zeros_like(sums), where=counts>0)
        self.indicator_indices_ = np.flatnonzero(counts < len(train))
        self.scaler_ = StandardScaler() if self.standardize else None
        if self.scaler_ is not None:
            for block in self._blocks(train, names):
                self.scaler_.partial_fit(self._impute(block))
        self.regressor_ = SGDRegressor(loss=self.loss, penalty=self.penalty, alpha=self.alpha,
            random_state=self.random_state, shuffle=False, early_stopping=False)
        starts = np.arange(0, len(train), self.batch_size)
        rng = np.random.default_rng(self.random_state)
        best, stale, best_model = np.inf, 0, None
        self.epoch_history_ = []
        for epoch in range(self.max_iter):
            seen = 0
            for start in rng.permutation(starts):
                batch = train.iloc[start:start+self.batch_size]
                self.regressor_.partial_fit(self.transform(batch[names].to_numpy(dtype=float)), batch[target].to_numpy(dtype=float))
                seen += len(batch)
            total = 0.
            for start in range(0, len(validation), self.batch_size):
                batch = validation.iloc[start:start+self.batch_size]
                total += np.abs(self.predict(batch[names].to_numpy(dtype=float))-batch[target].to_numpy(dtype=float)).sum()
            mae = total/len(validation)
            if not np.isfinite(mae):
                raise ValueError("SGD diverged; no estimator substitution")
            self.epoch_history_.append({"epoch":epoch+1,"train_rows_seen":seen,"validation_mae":float(mae)})
            if mae < best - (self.tol or 0):
                best, stale, best_model = mae, 0, copy.deepcopy(self.regressor_)
                self.best_epoch_ = epoch+1
            else:
                stale += 1
            if self.tol is not None and stale >= 5:
                break
        self.regressor_ = best_model
        return self

    def transform(self, values):
        result = self._impute(log1p_columns(values, self.log_indices))
        return self.scaler_.transform(result) if self.scaler_ is not None else result

    def predict(self, values):
        return self.regressor_.predict(self.transform(values))

    def fit(self, values, target):
        raise ValueError("Use fit_frame with explicit external validation; no internal random split")

    @property
    def coefficients(self):
        return self.regressor_.coef_

    def coefficient_names(self):
        return self.feature_names_ + (["missingindicator_"+self.feature_names_[i] for i in self.indicator_indices_] if self.add_indicator else [])
