import json
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Union
import duckdb
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
from src.utils.hashing import hash_file


def publish_file(local_path: Path, output: Path) -> None:
    """Publish a closed local file only after verifying the destination copy."""
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    uploading = output.with_name(output.name + f".uploading_{os.getpid()}")
    try:
        shutil.copyfile(local_path, uploading)
        if local_path.stat().st_size != uploading.stat().st_size or hash_file(local_path) != hash_file(uploading):
            raise IOError(f"Destination copy failed checksum verification: {output}")
        uploading.replace(output)
    finally:
        try:
            uploading.unlink(missing_ok=True)
        except OSError:
            pass  # A disconnected mount must not mask the original publish error.


def copy_query_to_parquet(con, query: str, output: Path, expected_rows=None) -> int:
    """Execute DuckDB output locally; validate row count before replacing a checkpoint."""
    temp_root = Path(con.execute("SELECT current_setting('temp_directory')").fetchone()[0])
    temp_root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="parquet_", dir=temp_root) as directory:
        local = Path(directory) / "result.parquet"
        safe_local = local.resolve().as_posix().replace("'", "''")
        con.execute(f"COPY ({query.strip().rstrip(';')}) TO '{safe_local}' (FORMAT PARQUET, COMPRESSION 'ZSTD')")
        with pq.ParquetFile(local) as parquet:
            rows = parquet.metadata.num_rows
        if expected_rows is not None and rows != expected_rows:
            raise ValueError(f"Row count invariant violated: expected {expected_rows}, got {rows}")
        publish_file(local, output)
    return rows


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
    compression: str = "zstd",
) -> None:
    """Write a DataFrame or PyArrow Table to a Parquet file atomically."""
    with tempfile.TemporaryDirectory(prefix="pubg_parquet_") as directory:
        temp_path = Path(directory) / "result.parquet"
        if isinstance(df_or_table, pd.DataFrame):
            table = pa.Table.from_pandas(df_or_table)
        else:
            table = df_or_table

        pq.write_table(table, temp_path, compression=compression)
        publish_file(temp_path, Path(file_path))


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
        safe_temp = temp_path.resolve().as_posix().replace("'", "''")
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
