import json
import os
import shutil
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Union
import duckdb
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq


def atomic_write_json(file_path: Union[str, Path], data: Any, indent: int = 2) -> None:
    """Write data to a JSON file atomically using a temporary file."""
    path = Path(file_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(f"{path.suffix}.tmp_{os.getpid()}")

    try:
        with open(temp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=indent, default=str)
        temp_path.replace(path)
    finally:
        if temp_path.exists():
            temp_path.unlink()


def read_json(file_path: Union[str, Path]) -> Any:
    """Read data from a JSON file."""
    path = Path(file_path)
    if not path.is_file():
        raise FileNotFoundError(f"JSON file does not exist: {path}")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def atomic_write_parquet(
    file_path: Union[str, Path],
    df_or_table: Union[pd.DataFrame, pa.Table],
    compression: str = "snappy",
) -> None:
    """Write a DataFrame or PyArrow Table to a Parquet file atomically."""
    path = Path(file_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(f"{path.suffix}.tmp_{os.getpid()}")

    try:
        if isinstance(df_or_table, pd.DataFrame):
            table = pa.Table.from_pandas(df_or_table)
        else:
            table = df_or_table

        pq.write_table(table, temp_path, compression=compression)
        temp_path.replace(path)
    finally:
        if temp_path.exists():
            temp_path.unlink()


def read_parquet_table(file_path: Union[str, Path], columns: Optional[List[str]] = None) -> pa.Table:
    """Read a Parquet file as a PyArrow Table with column projection."""
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"Parquet path does not exist: {path}")
    return pq.read_table(path, columns=columns)


def read_parquet_df(file_path: Union[str, Path], columns: Optional[List[str]] = None) -> pd.DataFrame:
    """Read a Parquet file as a pandas DataFrame with column projection."""
    return read_parquet_table(file_path, columns=columns).to_pandas()


def get_duckdb_connection(
    temp_dir: Optional[Union[str, Path]] = None,
    memory_limit: str = "4GB",
    threads: int = 4,
) -> duckdb.DuckDBPyConnection:
    """Initialize a configured DuckDB in-memory or disk-backed session."""
    con = duckdb.connect(database=":memory:")
    con.execute(f"SET threads TO {threads};")
    con.execute(f"SET max_memory TO '{memory_limit}';")
    con.execute("SET preserve_insertion_order = false;")
    if temp_dir:
        temp_path = Path(temp_dir)
        temp_path.mkdir(parents=True, exist_ok=True)
        # DuckDB requires forward slashes or escaped path
        safe_temp = str(temp_path.resolve()).replace("\\", "/")
        con.execute(f"SET temp_directory = '{safe_temp}';")
    return con


def scan_parquet_batches(
    file_path: Union[str, Path],
    batch_size: int = 50000,
    columns: Optional[List[str]] = None,
) -> Iterator[pd.DataFrame]:
    """Stream Parquet file in constant-size batches to prevent RAM saturation."""
    parquet_file = pq.ParquetFile(file_path)
    for batch in parquet_file.iter_batches(batch_size=batch_size, columns=columns):
        yield batch.to_pandas()
