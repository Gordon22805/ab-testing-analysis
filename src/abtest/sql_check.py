"""Portable SQL checks: execute the project SQL against an in-memory SQLite mirror."""
from __future__ import annotations

import re
import sqlite3
from pathlib import Path

import pandas as pd

EXPERIMENT_ID = "cta_buy_now_2026_09"

SQLITE_SCHEMA = """
CREATE TABLE experiments (
    experiment_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    start_date TEXT NOT NULL,
    end_date TEXT NOT NULL,
    primary_metric TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'running'
);
CREATE TABLE users (
    user_id TEXT PRIMARY KEY,
    first_seen_date TEXT,
    country TEXT,
    visitor_type TEXT
);
CREATE TABLE events (
    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL REFERENCES users (user_id),
    experiment_id TEXT NOT NULL REFERENCES experiments (experiment_id),
    experiment_group TEXT NOT NULL CHECK (experiment_group IN ('control', 'treatment')),
    session_date TEXT NOT NULL,
    device TEXT NOT NULL,
    traffic_source TEXT NOT NULL,
    viewed_product INTEGER NOT NULL,
    added_to_cart INTEGER NOT NULL,
    purchased INTEGER NOT NULL,
    revenue REAL NOT NULL DEFAULT 0 CHECK (revenue >= 0),
    session_duration INTEGER NOT NULL,
    UNIQUE (user_id, experiment_id)
);
CREATE INDEX idx_events_experiment_group ON events (experiment_id, experiment_group);
"""


def split_statements(sql: str) -> list[str]:
    stripped = re.sub(r"--[^\n]*", "", sql)
    return [s.strip() for s in stripped.split(";") if s.strip()]


def build_mirror(df: pd.DataFrame) -> sqlite3.Connection:
    con = sqlite3.connect(":memory:")
    con.executescript(SQLITE_SCHEMA)
    con.execute(
        "INSERT INTO experiments VALUES (?, ?, ?, ?, ?, ?)",
        (
            EXPERIMENT_ID,
            "CTA Купить -> Купить сейчас",
            df["session_date"].min().strftime("%Y-%m-%d"),
            df["session_date"].max().strftime("%Y-%m-%d"),
            "conversion_rate",
            "completed",
        ),
    )
    users = df[["user_id", "country", "visitor_type"]].copy()
    users["first_seen_date"] = df["session_date"].dt.strftime("%Y-%m-%d").values
    users.to_sql("users", con, if_exists="append", index=False)

    events = df[
        [
            "user_id",
            "experiment_group",
            "device",
            "traffic_source",
            "viewed_product",
            "added_to_cart",
            "purchased",
            "revenue",
            "session_duration",
        ]
    ].copy()
    events["experiment_id"] = EXPERIMENT_ID
    events["session_date"] = df["session_date"].dt.strftime("%Y-%m-%d").values
    events = events[
        [
            "user_id",
            "experiment_id",
            "experiment_group",
            "session_date",
            "device",
            "traffic_source",
            "viewed_product",
            "added_to_cart",
            "purchased",
            "revenue",
            "session_duration",
        ]
    ]
    events.to_sql("events", con, if_exists="append", index=False)
    return con


def run_file(con: sqlite3.Connection, path: Path) -> list[pd.DataFrame]:
    results = []
    for statement in split_statements(path.read_text(encoding="utf-8")):
        results.append(pd.read_sql_query(statement, con))
    return results


def run_all(con: sqlite3.Connection, sql_dir: Path) -> dict[str, list[pd.DataFrame]]:
    return {path.name: run_file(con, path) for path in sorted(sql_dir.glob("*.sql"))}
