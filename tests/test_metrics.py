import math

import pandas as pd
import pytest

from abtest.generate import generate_users
from abtest.metrics import (
    daily_conversion,
    funnel,
    group_metrics,
    revenue_impact,
    segment_metrics,
)


def _frame(rows: list[dict]) -> pd.DataFrame:
    base = {
        "experiment_group": "control",
        "device": "mobile",
        "traffic_source": "organic",
        "visitor_type": "new",
        "viewed_product": True,
        "added_to_cart": False,
        "purchased": False,
        "revenue": 0.0,
        "session_duration": 100,
        "session_date": pd.Timestamp("2026-09-01"),
    }
    return pd.DataFrame([{**base, **row} for row in rows]).assign(
        user_id=[f"U{i:06d}" for i in range(len(rows))]
    )


@pytest.fixture(scope="module")
def data() -> pd.DataFrame:
    return generate_users()


def test_group_metrics_rates():
    df = _frame(
        [
            {"experiment_group": "control", "added_to_cart": True, "purchased": True, "revenue": 100.0},
            {"experiment_group": "control", "added_to_cart": True},
            {"experiment_group": "control"},
            {"experiment_group": "control"},
            {"experiment_group": "treatment", "added_to_cart": True, "purchased": True, "revenue": 200.0},
            {"experiment_group": "treatment", "added_to_cart": True, "purchased": True, "revenue": 200.0},
            {"experiment_group": "treatment"},
            {"experiment_group": "treatment"},
        ]
    )
    gm = group_metrics(df).set_index("experiment_group")
    assert gm.loc["control", "conversion_rate"] == pytest.approx(0.25)
    assert gm.loc["treatment", "conversion_rate"] == pytest.approx(0.5)
    assert gm.loc["control", "add_to_cart_rate"] == pytest.approx(0.5)
    assert gm.loc["control", "purchase_rate"] == pytest.approx(0.5)
    assert gm.loc["control", "revenue_per_user"] == pytest.approx(25.0)
    assert gm.loc["control", "revenue_per_purchaser"] == pytest.approx(100.0)


def test_revenue_per_purchaser_nan_when_no_purchasers():
    df = _frame([{"experiment_group": "control"}, {"experiment_group": "treatment"}])
    gm = group_metrics(df).set_index("experiment_group")
    assert math.isnan(gm.loc["control", "revenue_per_purchaser"])
    assert gm.loc["control", "conversion_rate"] == 0.0


def test_purchase_rate_nan_when_no_cart_users():
    df = _frame([{"experiment_group": "control"}, {"experiment_group": "treatment"}])
    gm = group_metrics(df).set_index("experiment_group")
    assert math.isnan(gm.loc["control", "purchase_rate"])


def test_group_metrics_empty_frame():
    gm = group_metrics(pd.DataFrame(columns=["user_id", "experiment_group", "purchased", "revenue"]))
    assert gm.empty


def test_funnel_counts_monotone(data):
    fn = funnel(data)
    for group in ("control", "treatment"):
        assert fn[group].is_monotonic_decreasing
    assert fn.loc["users", "control"] == (data["experiment_group"] == "control").sum()


def test_funnel_pct_of_users(data):
    fn = funnel(data)
    assert fn.loc["purchased", "control_pct"] == pytest.approx(
        fn.loc["purchased", "control"] / fn.loc["users", "control"]
    )


def test_segment_returns_dropped_list():
    df = _frame(
        [{"experiment_group": "control", "device": "tablet"} for _ in range(3)]
        + [{"experiment_group": "treatment", "device": "tablet"} for _ in range(3)]
        + [{"experiment_group": "control", "device": "mobile"} for _ in range(300)]
        + [{"experiment_group": "treatment", "device": "mobile"} for _ in range(300)]
    )
    res = segment_metrics(df, "device")
    assert res["dropped"] == ["tablet"]
    assert set(res["table"]["segment"]) == {"mobile"}


def test_segment_table_columns(data):
    res = segment_metrics(data, "device")
    expected = {
        "segment",
        "users_control",
        "users_treatment",
        "cr_control",
        "cr_treatment",
        "abs_diff",
        "rel_lift_pct",
        "p_value",
        "ci_low",
        "ci_high",
        "significant",
    }
    assert expected <= set(res["table"].columns)
    assert len(res["table"]) == data["device"].nunique()


def test_daily_conversion_covers_all_days(data):
    daily = daily_conversion(data)
    assert daily["conversion_rate"].between(0, 1).all()
    assert daily["session_date"].nunique() == 21
    assert set(daily["experiment_group"]) == {"control", "treatment"}


def test_revenue_impact_scales_linearly(data):
    one = revenue_impact(data, n_target=10_000)
    two = revenue_impact(data, n_target=20_000)
    assert two["extra_revenue"] == pytest.approx(2 * one["extra_revenue"])
    assert one["extra_revenue_ci_low"] < one["extra_revenue"] < one["extra_revenue_ci_high"]


def test_revenue_impact_empty():
    empty = pd.DataFrame(columns=["user_id", "experiment_group", "purchased", "revenue"])
    assert math.isnan(revenue_impact(empty)["extra_revenue"])
