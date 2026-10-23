"""Six sklearn estimators with train-fitted preprocessing."""
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.dummy import DummyClassifier
from sklearn.ensemble import HistGradientBoostingClassifier, RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.naive_bayes import GaussianNB
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from sklearn.tree import DecisionTreeClassifier

from .config import SEED
from .config import FEATURE_SETS, FORBIDDEN_FEATURES, PLACEMENT_FEATURES


def tempered_class_weights(targets, alpha=0.8, max_ratio=12.0):
    """Sub-linear inverse frequency weights prevent coarse leaves from erasing majority recall."""
    counts = pd.Series(targets).value_counts()
    if counts.empty or alpha <= 0 or max_ratio < 1:
        raise ValueError('Invalid targets, alpha or max_ratio for class weights')
    raw = (len(targets) / (len(counts) * counts)) ** alpha
    return (raw / raw.min()).clip(upper=max_ratio).astype(float).to_dict()


def feature_columns(feature_set='full', with_placement=False):
    columns = list(FEATURE_SETS[feature_set])
    if with_placement and feature_set != 'distance':
        columns += list(PLACEMENT_FEATURES)
    if set(columns) & set(FORBIDDEN_FEATURES):
        raise ValueError('Forbidden columns in feature set')
    return columns


def build_model(family, balanced=False, feature_set='full', with_placement=False, jobs=2, **params):
    columns = feature_columns(feature_set, with_placement)
    categorical = [c for c in columns if c in ('map', 'time_phase', 'last_weapon_group', 'dominant_prior_weapon')]
    numeric = [c for c in columns if c not in categorical]
    transform = ColumnTransformer([
        ('numeric', Pipeline([('imputer', SimpleImputer(strategy='median', keep_empty_features=True)),
                              ('scale', StandardScaler())]), numeric),
        ('categorical', OneHotEncoder(handle_unknown='ignore', sparse_output=False), categorical),
    ], remainder='drop', sparse_threshold=0)
    weight = 'balanced' if balanced else None
    if family == 'majority':
        estimator = DummyClassifier(strategy='most_frequent')
    elif family == 'logistic':
        estimator = LogisticRegression(class_weight=weight, max_iter=1500, random_state=SEED)
    elif family == 'naive_bayes':
        estimator = GaussianNB()
    elif family == 'decision_tree':
        estimator = DecisionTreeClassifier(class_weight=weight, max_depth=12, min_samples_leaf=5, random_state=SEED)
    elif family == 'random_forest':
        estimator = RandomForestClassifier(n_estimators=200, max_depth=20, min_samples_leaf=2,
            class_weight='balanced_subsample' if balanced else None, n_jobs=jobs, random_state=SEED)
    elif family == 'hist_gradient_boosting':
        estimator = HistGradientBoostingClassifier(max_iter=150, max_leaf_nodes=31, min_samples_leaf=20,
            learning_rate=0.1, early_stopping=False, random_state=SEED)
    else:
        raise ValueError(f'Unknown model family: {family}')
    estimator.set_params(**params)
    return Pipeline([('preprocess', transform), ('model', estimator)])
