# src/cee_comps/db.py
"""
Thin DuckDB persistence layer.

Three operations: connect, write_table, read_table. Each call opens a
fresh file-backed connection and closes it on exit. This is fine for a
CLI tool — no concurrent writers, and connection cost is negligible at
our row counts (<100 per table).

Table names are interpolated into SQL via f-string. Acceptable here
because the only callers are internal modules passing known string
literals; do NOT extend this pattern to accept user-supplied names.
"""
from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

import duckdb
import pandas as pd

from .config import DB_PATH


@contextmanager
def connect() -> Iterator[duckdb.DuckDBPyConnection]:
    """Context-managed DuckDB connection to the project DB file."""
    con = duckdb.connect(str(DB_PATH))
    try:
        yield con
    finally:
        con.close()


def write_table(name: str, df: pd.DataFrame) -> None:
    """
    Replace `name` with the contents of `df`. Idempotent.

    Uses explicit register/unregister rather than relying on DuckDB's
    replacement scan, which is more obvious when reading the code.
    """
    if df is None or df.empty:
        raise ValueError(f"Refusing to write empty DataFrame to '{name}'.")
    with connect() as con:
        con.register("_tmp_df", df)
        con.execute(f"CREATE OR REPLACE TABLE {name} AS SELECT * FROM _tmp_df")
        con.unregister("_tmp_df")


def read_table(name: str) -> pd.DataFrame:
    """Load `name` into a pandas DataFrame."""
    with connect() as con:
        return con.execute(f"SELECT * FROM {name}").fetchdf()


def tables() -> list[str]:
    """List all tables currently in the DB. Useful for sanity-checking."""
    with connect() as con:
        rows = con.execute("SHOW TABLES").fetchall()
    return [r[0] for r in rows]