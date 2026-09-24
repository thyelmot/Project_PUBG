import json
import errno
import shutil
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Union
import duckdb
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
from src.utils.hashing import hash_file


def publish_file(local_path: Path, output: Path) -> None:
    """Verify publication, including mounts where rename fails or reports late.

    Only a NEW destination may fall back to an exclusive direct copy. Existing
    checkpoints must never be truncated to work around an unsupported rename.
    Single writer required; a direct copy is not atomic on a remote mount.
    """
    local_path = Path(local_path)
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    size, checksum = local_path.stat().st_size, hash_file(local_path)
    uploading = output.with_name(output.name + f".uploading_{uuid.uuid4().hex}")

    def verified(path):
        try:
            return path.stat().st_size == size and hash_file(path) == checksum
        except FileNotFoundError:
            return False

    transient = {errno.ENOENT, errno.EIO, errno.EBUSY, errno.ETIMEDOUT, errno.ESTALE,
                 errno.EXDEV, errno.ENOTSUP}
    try:
        for attempt in range(3):
            try:
                if verified(output):
                    return  # Includes a rename which succeeded despite raising ENOENT.
                if not verified(uploading):
                    shutil.copyfile(local_path, uploading)
                    if not verified(uploading):
                        raise OSError(errno.EIO, f"Destination copy failed checksum verification: {output}")
                try:
                    uploading.replace(output)
                except OSError as error:
                    if verified(output):
                        return
                    if error.errno not in transient:
                        raise
                    if attempt < 2:
                        raise
                    # FUSE may reject rename even after the temporary copy was read
                    # back successfully. Exclusive create cannot overwrite old data.
                    created = False
                    try:
                        with output.open("xb") as destination:
                            created = True
                            with local_path.open("rb") as source:
                                shutil.copyfileobj(source, destination, length=1024 * 1024)
                        if not verified(output):
                            raise OSError(errno.EIO, f"Direct copy failed checksum verification: {output}")
                    except BaseException:
                        if created:
                            try:
                                output.unlink(missing_ok=True)
                            except OSError:
                                pass
                        raise
                if verified(output):
                    return
                raise OSError(errno.EIO, f"Published file failed checksum verification: {output}")
            except OSError as error:
                if error.errno not in transient or attempt == 2:
                    raise
                print(f"Storage operation failed; retry {attempt + 1}/2: {output.name}", flush=True)
                time.sleep(attempt + 1)
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
    """Use the same verified publication rules as Parquet checkpoints."""
    with tempfile.TemporaryDirectory(prefix="pubg_json_") as directory:
        temp_path = Path(directory) / "result.json"
        with temp_path.open("w", encoding="utf-8") as f:
            json.dump(data, f, indent=indent, default=str)
        publish_file(temp_path, Path(file_path))


def check_storage_writable(directory: Path) -> None:
    """Fail before a long conversion if creation or checkpoint replacement fails."""
    probe = Path(directory) / f".pubg_write_check_{uuid.uuid4().hex}.json"
    try:
        atomic_write_json(probe, {"probe": 1})
        atomic_write_json(probe, {"probe": 2})
    except OSError as error:
        raise OSError(
            f"Cannot create/replace checkpoints in {directory}. Check Drive connection, "
            "Editor access and free storage, then rerun this cell. No CSV conversion started."
        ) from error
    finally:
        try:
            probe.unlink(missing_ok=True)
        except OSError:
            pass


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
    """Write locally, then publish using verified checkpoint rules."""
    with tempfile.TemporaryDirectory(prefix="pubg_parquet_") as directory:
        temp_path = Path(directory) / "result.parquet"
        if isinstance(df_or_table, pd.DataFrame):
            table = pa.Table.from_pandas(df_or_table)
        else:
            table = df_or_table

        pq.write_table(table, temp_path, compression=compression)
        publish_file(temp_path, Path(file_path))


def atomic_write_csv(file_path: Union[str, Path], df: pd.DataFrame, *, index=False) -> None:
    """Close and verify reports before replacing the previous result."""
    with tempfile.TemporaryDirectory(prefix="pubg_csv_") as directory:
        local = Path(directory) / "result.csv"
        df.to_csv(local, index=index)
        publish_file(local, Path(file_path))


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
