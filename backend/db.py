"""
Database layer for CampusWatch SQLite storage.
Handles initialization, upserting meter readings, querying historical data,
and record counting.
"""

import sqlite3
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from .config import DB_PATH


def get_connection() -> sqlite3.Connection:
    """Returns a SQLite connection with row factory enabled."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    """Initializes the database schema if it doesn't already exist."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS readings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                building TEXT NOT NULL,
                resource TEXT NOT NULL,
                ts TEXT NOT NULL,
                value REAL NOT NULL,
                UNIQUE(building, resource, ts)
            );
            """
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_readings_ts ON readings(ts);"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_readings_lookup ON readings(building, resource, ts);"
        )
        conn.commit()


def insert_readings(rows: List[Dict[str, Any]]) -> None:
    """
    Inserts a list of readings into the database using UPSERT semantics.
    Each row must be a dict with keys: {building, resource, ts, value}.
    """
    if not rows:
        return
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.executemany(
            """
            INSERT INTO readings (building, resource, ts, value)
            VALUES (:building, :resource, :ts, :value)
            ON CONFLICT(building, resource, ts) DO UPDATE SET value = excluded.value;
            """,
            rows,
        )
        conn.commit()


def clear_readings() -> None:
    """Wipes all rows from the readings table."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM readings;")
        conn.commit()



def get_readings(
    building: Optional[str] = None,
    resource: Optional[str] = None,
    hours: Optional[int] = 168,
) -> List[Dict[str, Any]]:
    """
    Retrieves readings filtered by building, resource, and time window (in hours).
    Returns a list of dicts: [{building, resource, ts, value}].
    If hours is specified, filters records relative to the latest timestamp in the database.
    """
    with get_connection() as conn:
        cursor = conn.cursor()
        where_clauses = []
        params = []

        if building:
            where_clauses.append("building = ?")
            params.append(building)
        if resource:
            where_clauses.append("resource = ?")
            params.append(resource)

        if hours is not None and hours > 0:
            cursor.execute("SELECT MAX(ts) FROM readings")
            max_row = cursor.fetchone()
            if max_row and max_row[0]:
                max_dt = datetime.fromisoformat(max_row[0])
                cutoff_dt = max_dt - timedelta(hours=hours)
                where_clauses.append("ts >= ?")
                params.append(cutoff_dt.isoformat())

        where_sql = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""
        query = f"""
            SELECT building, resource, ts, value
            FROM readings
            {where_sql}
            ORDER BY ts ASC
        """
        cursor.execute(query, params)
        rows = cursor.fetchall()
        return [
            {
                "building": row["building"],
                "resource": row["resource"],
                "ts": row["ts"],
                "value": float(row["value"]),
            }
            for row in rows
        ]


def count_readings() -> int:
    """Returns the total number of readings stored in the database."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM readings")
        row = cursor.fetchone()
        return row[0] if row else 0
