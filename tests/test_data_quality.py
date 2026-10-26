import numpy as np
import pandas as pd
import pytest

from abtest import data_quality as dq
from abtest.generate import generate_users


@pytest.fixture(scope="module")
def clean_df() -> pd.DataFrame:
    return generate_users(800, seed=11)


def _run(df):
    return dq.clean(df)


def _issues(report: pd.DataFrame) -> dict[str, int]:
    return dict(zip(report["check"], report["issues_found"]))


def test_clean_data_has_no_issues(clean_df):
    _, report, _ = _run(clean_df)
    assert report["issues_found"].sum() == 0
    assert len(report) == len(dq.CHECKS)


def test_duplicate_user_removed(clean_df):
    dirty = pd.concat([clean_df, clean_df.iloc[:3]], ignore_index=True)
    out, report, dropped = _run(dirty)
    assert out["user_id"].is_unique
    assert len(out) == len(clean_df)
    assert _issues(report)["duplicate_user_id"] == 3


def test_user_in_two_groups_removed(clean_df):
    dirty = pd.concat([clean_df, clean_df.iloc[[0]]], ignore_index=True)
    dirty.loc[len(dirty) - 1, "experiment_group"] = (
        "treatment" if dirty.loc[0, "experiment_group"] == "control" else "control"
    )
    out, report, _ = _run(dirty)
    assert dirty.loc[0, "user_id"] not in set(out["user_id"])
    assert _issues(report)["user_in_both_groups"] >= 1


def test_negative_revenue_removed(clean_df):
    dirty = clean_df.copy()
    dirty.loc[5, "revenue"] = -100.0
    out, report, _ = _run(dirty)
    assert (out["revenue"] >= 0).all()
    assert _issues(report)["negative_revenue"] == 1


def test_null_group_removed(clean_df):
    dirty = clean_df.copy()
    dirty.loc[7, "experiment_group"] = None
    out, report, _ = _run(dirty)
    assert out["experiment_group"].notna().all()
    assert _issues(report)["missing_required_fields"] >= 1


def test_unknown_group_removed(clean_df):
    dirty = clean_df.copy()
    dirty.loc[9, "experiment_group"] = "variant_c"
    out, report, _ = _run(dirty)
    assert set(out["experiment_group"]) == {"control", "treatment"}
    assert _issues(report)["invalid_experiment_group"] == 1


def test_purchase_without_cart_removed(clean_df):
    dirty = clean_df.copy()
    dirty.loc[11, ["viewed_product", "added_to_cart", "purchased"]] = [True, False, True]
    out, report, _ = _run(dirty)
    assert (out["purchased"] & ~out["added_to_cart"]).sum() == 0
    assert _issues(report)["funnel_order"] == 1


def test_revenue_without_purchase_removed(clean_df):
    dirty = clean_df.copy()
    dirty.loc[13, ["purchased", "revenue"]] = [False, 999.0]
    out, report, _ = _run(dirty)
    assert (out.loc[~out["purchased"], "revenue"] == 0).all()
    assert _issues(report)["revenue_vs_purchased"] == 1


def test_out_of_window_date_removed(clean_df):
    dirty = clean_df.copy()
    dirty.loc[15, "session_date"] = pd.Timestamp("2026-08-01")
    out, report, _ = _run(dirty)
    assert out["session_date"].min() >= pd.Timestamp("2026-09-01")
    assert _issues(report)["session_date_window"] == 1


def test_unknown_device_removed(clean_df):
    dirty = clean_df.copy()
    dirty.loc[17, "device"] = "smart_tv"
    out, report, _ = _run(dirty)
    assert "smart_tv" not in set(out["device"])
    assert _issues(report)["unknown_categories"] == 1


def test_dropped_log_reason_matches(clean_df):
    dirty = pd.concat([clean_df, clean_df.iloc[:2]], ignore_index=True)
    dirty.loc[20, "revenue"] = -1.0
    _, _, dropped = _run(dirty)
    assert len(dropped) == 3
    assert set(dropped["reason"]) == {"duplicate_user_id", "negative_revenue"}


def test_all_nan_revenue_does_not_crash(clean_df):
    dirty = clean_df.copy()
    dirty["revenue"] = np.nan
    out, report, _ = _run(dirty)
    assert out.empty or out["revenue"].isna().all()
