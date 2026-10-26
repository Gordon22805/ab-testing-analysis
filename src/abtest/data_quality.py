"""Data quality checks and cleaning for the experiment dataset."""
from __future__ import annotations

from collections.abc import Callable

import pandas as pd

from abtest.config import EXPERIMENT_DAYS, EXPERIMENT_START, GROUPS

DEVICES = {"mobile", "desktop", "tablet"}
SOURCES = {"organic", "paid_search", "social", "email", "referral"}
VISITOR_TYPES = {"new", "returning"}
COUNTRIES = {"RU", "KZ", "BY", "UA"}
REQUIRED = [
    "user_id",
    "experiment_group",
    "device",
    "traffic_source",
    "visitor_type",
    "session_date",
    "viewed_product",
    "added_to_cart",
    "purchased",
    "revenue",
]

Check = Callable[[pd.DataFrame], tuple[pd.Index, str]]


def _window() -> tuple[pd.Timestamp, pd.Timestamp]:
    start = pd.Timestamp(EXPERIMENT_START)
    return start, start + pd.Timedelta(days=EXPERIMENT_DAYS)


def _duplicate_users(df: pd.DataFrame) -> tuple[pd.Index, str]:
    mask = df["user_id"].duplicated(keep="first")
    return df.index[mask], f"duplicated user_id: {df.loc[mask, 'user_id'].nunique()}"


def _both_groups(df: pd.DataFrame) -> tuple[pd.Index, str]:
    counts = df.groupby("user_id")["experiment_group"].nunique()
    ids = counts[counts > 1].index
    return df.index[df["user_id"].isin(ids)], f"users in both groups: {len(ids)}"


def _nulls(df: pd.DataFrame) -> tuple[pd.Index, str]:
    mask = df[REQUIRED].isna().any(axis=1)
    return df.index[mask], f"rows with missing required fields: {int(mask.sum())}"


def _unknown_group(df: pd.DataFrame) -> tuple[pd.Index, str]:
    mask = ~df["experiment_group"].isin(GROUPS)
    return df.index[mask], f"rows with invalid experiment_group: {int(mask.sum())}"


def _unknown_categories(df: pd.DataFrame) -> tuple[pd.Index, str]:
    mask = (
        ~df["device"].isin(DEVICES)
        | ~df["traffic_source"].isin(SOURCES)
        | ~df["visitor_type"].isin(VISITOR_TYPES)
        | ~df["country"].isin(COUNTRIES)
    )
    return df.index[mask], f"rows with unknown device/source/visitor_type/country: {int(mask.sum())}"


def _negative_revenue(df: pd.DataFrame) -> tuple[pd.Index, str]:
    mask = df["revenue"].fillna(0) < 0
    return df.index[mask], f"rows with negative revenue: {int(mask.sum())}"


def _funnel_logic(df: pd.DataFrame) -> tuple[pd.Index, str]:
    mask = (df["purchased"] & ~df["added_to_cart"]) | (df["added_to_cart"] & ~df["viewed_product"])
    return df.index[mask.fillna(False)], f"rows violating funnel order: {int(mask.sum())}"


def _revenue_logic(df: pd.DataFrame) -> tuple[pd.Index, str]:
    mask = (df["purchased"] & (df["revenue"].fillna(0) == 0)) | (~df["purchased"] & (df["revenue"].fillna(0) != 0))
    return df.index[mask.fillna(False)], f"rows where revenue and purchased disagree: {int(mask.sum())}"


def _dates(df: pd.DataFrame) -> tuple[pd.Index, str]:
    start, end = _window()
    dates = pd.to_datetime(df["session_date"], errors="coerce")
    mask = dates.isna() | (dates < start) | (dates >= end)
    return df.index[mask], f"rows outside the experiment window or with invalid date: {int(mask.sum())}"


CHECKS: list[tuple[str, Check]] = [
    ("user_in_both_groups", _both_groups),
    ("duplicate_user_id", _duplicate_users),
    ("missing_required_fields", _nulls),
    ("invalid_experiment_group", _unknown_group),
    ("unknown_categories", _unknown_categories),
    ("negative_revenue", _negative_revenue),
    ("funnel_order", _funnel_logic),
    ("revenue_vs_purchased", _revenue_logic),
    ("session_date_window", _dates),
]

REQUIRED_COLUMNS = REQUIRED + ["country", "session_duration"]


def run_checks(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for name, check in CHECKS:
        bad_index, detail = check(df)
        n = len(bad_index)
        rows.append(
            {
                "check": name,
                "issues_found": n,
                "action": "drop rows" if n else "none",
                "detail": detail,
            }
        )
    return pd.DataFrame(rows)


def clean(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Return (clean_df, quality_report, dropped_rows_log)."""
    df = df.copy()
    df["session_date"] = pd.to_datetime(df["session_date"], errors="coerce")

    report = run_checks(df)
    dropped = pd.DataFrame({"row": [], "reason": []})
    clean = df
    for name, check in CHECKS:
        bad_index, _ = check(clean)
        if len(bad_index):
            dropped = pd.concat(
                [dropped, pd.DataFrame({"row": bad_index, "reason": name})], ignore_index=True
            )
            clean = clean.drop(index=bad_index)

    clean = clean.reset_index(drop=True)
    return clean, report, dropped
