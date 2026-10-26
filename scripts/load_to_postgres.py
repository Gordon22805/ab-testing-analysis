"""Load the cleaned dataset into PostgreSQL. Requires a running server and DATABASE_URL."""
from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pandas as pd

from abtest.config import DATA_PATH, ROOT
from abtest.data_quality import REQUIRED_COLUMNS, clean

EXPERIMENT_ID = "cta_buy_now_2026_09"
READ_BATCH = 5_000


def _connect():
    try:
        import psycopg2
    except ImportError as exc:  # pragma: no cover - depends on local env
        raise SystemExit("Установите psycopg2-binary: pip install -r requirements.txt") from exc

    dsn = os.getenv("DATABASE_URL")
    if not dsn:
        raise SystemExit(
            "Задайте переменную окружения DATABASE_URL, например:\n"
            "  set DATABASE_URL=postgresql://postgres:postgres@localhost:5432/ab_testing"
        )
    return psycopg2.connect(dsn)


def main() -> None:
    data_path = Path(sys.argv[1]) if len(sys.argv) > 1 else DATA_PATH
    if not data_path.exists():
        raise SystemExit(f"Нет файла {data_path}. Сначала запустите run_analysis.py")
    raw = pd.read_csv(data_path, parse_dates=["session_date"])
    missing = [c for c in REQUIRED_COLUMNS if c not in raw.columns]
    if missing:
        raise SystemExit(f"В файле нет колонок: {missing}")

    df, _, _ = clean(raw)
    con = _connect()
    con.autocommit = False
    cur = con.cursor()
    cur.execute((ROOT / "database" / "schema.sql").read_text(encoding="utf-8"))

    cur.execute("TRUNCATE events, users, experiments")
    cur.execute(
        "INSERT INTO experiments (experiment_id, name, start_date, end_date, primary_metric, status)"
        " VALUES (%s, %s, %s, %s, %s, %s)",
        (
            EXPERIMENT_ID,
            "CTA «Купить» vs «Купить сейчас»",
            df["session_date"].min().date(),
            df["session_date"].max().date(),
            "conversion_rate",
            "completed",
        ),
    )

    users = df[["user_id", "country", "visitor_type"]].copy()
    users["first_seen_date"] = df["session_date"].dt.date
    with cur.copy(
        "COPY users (user_id, first_seen_date, country, visitor_type) FROM STDIN"
    ) as copy:
        for row in users.itertuples(index=False, name=None):
            copy.write_row(row)

    event_cols = [
        "user_id",
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
    events = df[event_cols].copy()
    events["session_date"] = events["session_date"].dt.date
    with cur.copy(
        "COPY events (user_id, experiment_id, experiment_group, session_date, device, traffic_source,"
        " viewed_product, added_to_cart, purchased, revenue, session_duration)"
        " FROM STDIN"
    ) as copy:
        for row in events.itertuples(index=False, name=None):
            copy.write_row((row[0], EXPERIMENT_ID, *row[1:]))

    con.commit()
    cur.execute("SELECT COUNT(*) FROM events")
    print(f"Загружено событий: {cur.fetchone()[0]}")
    cur.close()
    con.close()


if __name__ == "__main__":
    main()
