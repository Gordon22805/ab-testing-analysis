"""Metric tables, funnel and segment analysis."""
from __future__ import annotations

import pandas as pd

from abtest.config import ALPHA, GROUPS, IMPACT_TARGET_USERS, MIN_SEGMENT_USERS
from abtest.stats import two_proportion_ztest

SEGMENT_COLUMNS = ["device", "traffic_source", "visitor_type"]


def _safe_div(a: float, b: float) -> float:
    return a / b if b else float("nan")


def group_metrics(df: pd.DataFrame, group_col: str = "experiment_group") -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame(
            columns=[
                "experiment_group",
                "users",
                "viewers",
                "add_to_cart_users",
                "purchasers",
                "conversion_rate",
                "view_rate",
                "add_to_cart_rate",
                "purchase_rate",
                "revenue",
                "revenue_per_user",
                "revenue_per_purchaser",
                "avg_session_duration",
            ]
        )

    agg = df.groupby(group_col, observed=True).agg(
        users=("user_id", "size"),
        viewers=("viewed_product", "sum"),
        add_to_cart_users=("added_to_cart", "sum"),
        purchasers=("purchased", "sum"),
        revenue=("revenue", "sum"),
        avg_session_duration=("session_duration", "mean"),
    )
    agg["conversion_rate"] = agg["purchasers"] / agg["users"]
    agg["view_rate"] = agg["viewers"] / agg["users"]
    agg["add_to_cart_rate"] = agg["add_to_cart_users"] / agg["users"]
    agg["purchase_rate"] = agg["purchasers"] / agg["add_to_cart_users"]
    agg["revenue_per_user"] = agg["revenue"] / agg["users"]
    agg["revenue_per_purchaser"] = agg["revenue"] / agg["purchasers"]
    agg = agg.reset_index().sort_values(group_col, key=lambda s: s.map({g: i for i, g in enumerate(GROUPS)}))
    return agg


def funnel(df: pd.DataFrame) -> pd.DataFrame:
    steps = {
        "users": pd.Series(True, index=df.index),
        "viewed": df["viewed_product"],
        "added_to_cart": df["added_to_cart"],
        "purchased": df["purchased"],
    }
    rows = {}
    for step, mask in steps.items():
        rows[step] = {
            group: int((mask & (df["experiment_group"] == group)).sum()) for group in GROUPS
        }
    counts = pd.DataFrame(rows).T
    for group in GROUPS:
        counts[f"{group}_pct"] = counts[group] / counts.loc["users", group] if counts.loc["users", group] else float("nan")
    return counts


def segment_metrics(df: pd.DataFrame, segment_col: str) -> dict:
    rows = []
    dropped = []
    for segment, part in df.groupby(segment_col, observed=True):
        counts = part.groupby("experiment_group", observed=True)["purchased"].agg(["size", "sum"])
        n_c = int(counts["size"].get("control", 0))
        n_t = int(counts["size"].get("treatment", 0))
        if n_c < MIN_SEGMENT_USERS or n_t < MIN_SEGMENT_USERS:
            dropped.append(str(segment))
            continue
        x_c = int(counts["sum"].get("control", 0))
        x_t = int(counts["sum"].get("treatment", 0))
        test = two_proportion_ztest(x_c, n_c, x_t, n_t)
        rows.append(
            {
                "segment": str(segment),
                "users_control": n_c,
                "users_treatment": n_t,
                "cr_control": test["cr_control"],
                "cr_treatment": test["cr_treatment"],
                "abs_diff": test["abs_diff"],
                "rel_lift_pct": test["rel_lift_pct"],
                "p_value": test["p_value"],
                "ci_low": test["ci_low"],
                "ci_high": test["ci_high"],
                "significant": test["significant"],
            }
        )
    table = pd.DataFrame(rows)
    return {"table": table, "dropped": dropped, "column": segment_col}


def all_segments(df: pd.DataFrame) -> dict[str, dict]:
    return {col: segment_metrics(df, col) for col in SEGMENT_COLUMNS if col in df.columns}


def daily_conversion(df: pd.DataFrame) -> pd.DataFrame:
    daily = (
        df.groupby(["session_date", "experiment_group"], observed=True)["purchased"]
        .agg(["size", "sum"])
        .rename(columns={"size": "users", "sum": "purchasers"})
        .reset_index()
    )
    daily["conversion_rate"] = daily["purchasers"] / daily["users"]
    daily["rolling_cr"] = daily.groupby("experiment_group", observed=True)["conversion_rate"].transform(
        lambda s: s.rolling(3, min_periods=1).mean()
    )
    return daily.sort_values("session_date")


def revenue_impact(df: pd.DataFrame, n_target: int = IMPACT_TARGET_USERS, alpha: float = ALPHA) -> dict:
    gm = group_metrics(df).set_index("experiment_group")
    if not {"control", "treatment"}.issubset(gm.index):
        return {"n_target": n_target, "extra_revenue": float("nan")}

    cr = gm.loc[["control", "treatment"]]
    test = two_proportion_ztest(
        int(cr.loc["control", "purchasers"]),
        int(cr.loc["control", "users"]),
        int(cr.loc["treatment", "purchasers"]),
        int(cr.loc["treatment", "users"]),
        alpha,
    )
    rpp_c = cr.loc["control", "revenue_per_purchaser"]
    rpp_t = cr.loc["treatment", "revenue_per_purchaser"]
    baseline_aov = cr.loc["control", "revenue"] / cr.loc["control", "purchasers"]
    treatment_aov = cr.loc["treatment", "revenue"] / cr.loc["treatment", "purchasers"]

    diff = test["abs_diff"]
    extra_purchases_per_user = diff
    extra_revenue_per_user = diff * treatment_aov

    return {
        "n_target": n_target,
        "aov_control": baseline_aov,
        "aov_treatment": treatment_aov,
        "rpu_control": cr.loc["control", "revenue_per_user"],
        "rpu_treatment": cr.loc["treatment", "revenue_per_user"],
        "extra_purchases_per_user": extra_purchases_per_user,
        "extra_revenue_per_user": extra_revenue_per_user,
        "extra_purchases": extra_purchases_per_user * n_target,
        "extra_revenue": extra_revenue_per_user * n_target,
        "extra_purchases_ci_low": test["ci_low"] * n_target,
        "extra_purchases_ci_high": test["ci_high"] * n_target,
        "extra_revenue_ci_low": test["ci_low"] * treatment_aov * n_target,
        "extra_revenue_ci_high": test["ci_high"] * treatment_aov * n_target,
        "aov_ci_low": min(rpp_c, rpp_t),
        "aov_ci_high": max(rpp_c, rpp_t),

        "rel_lift_pct": test["rel_lift_pct"],
        "p_value": test["p_value"],
        "significant": test["significant"],
    }
