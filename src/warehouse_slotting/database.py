"""Editable SQLite input store, separate from immutable analytics runs."""

from __future__ import annotations

import sqlite3
import math
from pathlib import Path

import pandas as pd


TABLE_KEYS = {"orders": ("order_id", "sku_id"), "skus": ("sku_id",),
              "locations": ("location_id",)}
SOURCE_FILES = {name: f"festival_{name}.csv" for name in TABLE_KEYS}


def _quoted(identifier: str) -> str:
    if not identifier.isidentifier():
        raise ValueError(f"Invalid column name: {identifier}")
    return f'"{identifier}"'


def connect(path: str | Path) -> sqlite3.Connection:
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def initialize(path: str | Path, source_directory: str | Path | None = None,
               tables: dict[str, pd.DataFrame] | None = None) -> None:
    """Create a persistent local database from a saved run or bundled inputs once."""
    if tables is None and source_directory is None:
        raise ValueError("Provide source tables or a source directory")
    db_path = Path(path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with connect(db_path) as connection:
        if all(connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
        ).fetchone() for table in TABLE_KEYS):
            return
        with connection:
            for table, keys in TABLE_KEYS.items():
                frame = (tables[table] if tables is not None else
                         pd.read_csv(Path(source_directory) / SOURCE_FILES[table]))
                columns = []
                for column in frame.columns:
                    kind = "REAL" if pd.api.types.is_float_dtype(frame[column]) else (
                        "INTEGER" if pd.api.types.is_integer_dtype(frame[column]) else "TEXT"
                    )
                    columns.append(f"{_quoted(column)} {kind}")
                primary = ", ".join(_quoted(key) for key in keys)
                connection.execute(f'CREATE TABLE IF NOT EXISTS "{table}" '
                                   f'({", ".join(columns)}, PRIMARY KEY ({primary}))')
                fields = ", ".join(_quoted(column) for column in frame.columns)
                placeholders = ", ".join("?" for _ in frame.columns)
                prepared = frame.copy()
                for field in prepared.columns:
                    if pd.api.types.is_datetime64_any_dtype(prepared[field]):
                        prepared[field] = prepared[field].dt.strftime("%Y-%m-%d %H:%M:%S")
                prepared = prepared.astype(object).where(pd.notna(prepared), None)
                records = [tuple(
                    value.isoformat(sep=" ") if isinstance(value, pd.Timestamp) else
                    value.item() if hasattr(value, "item") else value
                    for value in row
                ) for row in prepared.itertuples(index=False, name=None)]
                connection.executemany(
                    f'INSERT OR IGNORE INTO "{table}" ({fields}) VALUES ({placeholders})',
                    records,
                )


def columns(connection: sqlite3.Connection, table: str) -> list[tuple[str, str]]:
    if table not in TABLE_KEYS:
        raise ValueError("Unknown table")
    return [(row["name"], row["type"]) for row in connection.execute(f'PRAGMA table_info("{table}")')]


def count(connection: sqlite3.Connection, table: str) -> int:
    if table not in TABLE_KEYS:
        raise ValueError("Unknown table")
    return int(connection.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0])


def preview(connection: sqlite3.Connection, table: str, limit: int = 100,
            offset: int = 0) -> pd.DataFrame:
    if table not in TABLE_KEYS:
        raise ValueError("Unknown table")
    order = ", ".join(_quoted(key) for key in TABLE_KEYS[table])
    return pd.read_sql_query(
        f'SELECT * FROM "{table}" ORDER BY {order} LIMIT ? OFFSET ?',
        connection, params=(limit, offset),
    )


def keys(connection: sqlite3.Connection, table: str) -> list[tuple[str, ...]]:
    if table not in TABLE_KEYS:
        raise ValueError("Unknown table")
    fields = ", ".join(_quoted(key) for key in TABLE_KEYS[table])
    return [tuple(str(value) for value in row) for row in connection.execute(
        f'SELECT {fields} FROM "{table}" ORDER BY {fields}'
    )]


def get_row(connection: sqlite3.Connection, table: str, key: tuple[str, ...]) -> dict:
    if table not in TABLE_KEYS or len(key) != len(TABLE_KEYS[table]):
        raise ValueError("Invalid row key")
    where = " AND ".join(f'{_quoted(field)}=?' for field in TABLE_KEYS[table])
    row = connection.execute(f'SELECT * FROM "{table}" WHERE {where}', key).fetchone()
    if row is None:
        raise KeyError(key)
    return dict(row)


def _cast(value: object, kind: str) -> object:
    if kind == "INTEGER":
        number = float(str(value))
        if not math.isfinite(number) or not number.is_integer():
            raise ValueError("Enter a whole number")
        return int(number)
    if kind == "REAL":
        number = float(str(value))
        if not math.isfinite(number):
            raise ValueError("Enter a finite number")
        return number
    return str(value).strip()


def save_row(connection: sqlite3.Connection, table: str, values: dict,
             old_key: tuple[str, ...] | None = None) -> None:
    schema = columns(connection, table)
    if set(values) != {name for name, _ in schema}:
        raise ValueError("All table fields are required")
    parsed = {name: _cast(values[name], kind) for name, kind in schema}
    if any(parsed[key] == "" for key in TABLE_KEYS[table]):
        raise ValueError("Key fields cannot be blank")
    if table == "orders":
        if int(parsed["quantity"]) <= 0 or pd.isna(pd.to_datetime(parsed["timestamp"], errors="coerce")):
            raise ValueError("Orders need a positive quantity and valid timestamp")
        if not connection.execute('SELECT 1 FROM "skus" WHERE sku_id=?',
                                  (parsed["sku_id"],)).fetchone():
            raise ValueError("Add the SKU before referencing it in an order")
    if table == "skus" and (int(parsed["on_hand_qty"]) <= 0 or
                             any(float(parsed[name]) <= 0 for name in
                                 ("width_cm", "height_cm", "depth_cm", "unit_weight_kg"))):
        raise ValueError("SKU dimensions, weight, and on-hand quantity must be positive")
    if table == "skus" and old_key is not None and parsed["sku_id"] != old_key[0] and connection.execute(
        'SELECT 1 FROM "orders" WHERE sku_id=? LIMIT 1', old_key
    ).fetchone():
        raise ValueError("This SKU is used by orders; update those lines before changing its ID")
    if table == "locations" and any(float(parsed[name]) <= 0 for name in
                                      ("bin_width_cm", "bin_height_cm", "bin_depth_cm",
                                       "bin_max_weight_kg", "shelf_max_weight_kg", "rack_max_weight_kg")):
        raise ValueError("Bin dimensions and weight limits must be positive")
    fields = ", ".join(_quoted(name) for name, _ in schema)
    placeholders = ", ".join("?" for _ in schema)
    with connection:
        if old_key is not None:
            where = " AND ".join(f'{_quoted(field)}=?' for field in TABLE_KEYS[table])
            cursor = connection.execute(f'DELETE FROM "{table}" WHERE {where}', old_key)
            if cursor.rowcount != 1:
                raise KeyError(old_key)
        connection.execute(f'INSERT INTO "{table}" ({fields}) VALUES ({placeholders})',
                           tuple(parsed[name] for name, _ in schema))


def delete_row(connection: sqlite3.Connection, table: str, key: tuple[str, ...]) -> None:
    if table not in TABLE_KEYS or len(key) != len(TABLE_KEYS[table]):
        raise ValueError("Invalid row key")
    if table == "skus" and connection.execute(
        'SELECT 1 FROM "orders" WHERE sku_id=? LIMIT 1', key
    ).fetchone():
        raise ValueError("This SKU is used by orders; delete those lines first")
    where = " AND ".join(f'{_quoted(field)}=?' for field in TABLE_KEYS[table])
    with connection:
        cursor = connection.execute(f'DELETE FROM "{table}" WHERE {where}', key)
        if cursor.rowcount != 1:
            raise KeyError(key)


def export_tables(connection: sqlite3.Connection, directory: str | Path) -> dict[str, Path]:
    target = Path(directory)
    target.mkdir(parents=True, exist_ok=True)
    result = {}
    for table in TABLE_KEYS:
        path = target / f"{table}.csv"
        pd.read_sql_query(f'SELECT * FROM "{table}"', connection).to_csv(path, index=False)
        result[table] = path
    return result
