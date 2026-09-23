import hashlib
import json
from pathlib import Path
from typing import Any, Dict, Union
import pandas as pd


def hash_file(file_path: Union[str, Path], algorithm: str = "sha256", chunk_size: int = 65536) -> str:
    """Compute deterministic cryptographic hash of a file."""
    path = Path(file_path)
    if not path.is_file():
        raise FileNotFoundError(f"File not found for hashing: {path}")

    hasher = getattr(hashlib, algorithm)()
    with open(path, "rb") as f:
        while chunk := f.read(chunk_size):
            hasher.update(chunk)
    return hasher.hexdigest()


def hash_dict(data: Dict[str, Any], algorithm: str = "sha256") -> str:
    """Compute deterministic hash of a dictionary by sorting keys."""
    encoded = json.dumps(data, sort_keys=True, default=str).encode("utf-8")
    hasher = getattr(hashlib, algorithm)()
    hasher.update(encoded)
    return hasher.hexdigest()


def hash_dataframe(df: pd.DataFrame, algorithm: str = "sha256") -> str:
    """Compute hash of pandas DataFrame based on columns, dtypes, and values."""
    hasher = getattr(hashlib, algorithm)()
    # Include column names and dtypes in hash
    col_meta = json.dumps([(str(col), str(dtype)) for col, dtype in zip(df.columns, df.dtypes)]).encode("utf-8")
    hasher.update(col_meta)

    # Use pandas deterministic hash if available, or row serialization
    try:
        series_hash = pd.util.hash_pandas_object(df, index=True).values.tobytes()
        hasher.update(series_hash)
    except Exception:
        # Fallback for complex object dtypes
        hasher.update(df.to_csv(index=True).encode("utf-8"))
    return hasher.hexdigest()


def compute_signature(**kwargs: Any) -> str:
    """Compute deterministic run/checkpoint signature from kwargs components."""
    clean_kwargs = {k: v for k, v in kwargs.items() if v is not None}
    return hash_dict(clean_kwargs)
