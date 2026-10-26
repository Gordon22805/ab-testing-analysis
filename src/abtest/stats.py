"""Proportions statistics: z-test, confidence intervals, SRM, power."""
from __future__ import annotations

import math

import pandas as pd
from scipy import stats

from abtest.config import ALPHA, SRM_ALPHA

NAN = float("nan")


def two_proportion_ztest(x_c: int, n_c: int, x_t: int, n_t: int, alpha: float = ALPHA) -> dict:
    if n_c <= 0 or n_t <= 0:
        return _empty_result(alpha)

    p_c = x_c / n_c
    p_t = x_t / n_t
    diff = p_t - p_c
    rel_lift = diff / p_c * 100 if p_c > 0 else NAN

    pooled = (x_c + x_t) / (n_c + n_t)
    se_pooled = math.sqrt(pooled * (1 - pooled) * (1 / n_c + 1 / n_t))
    z = diff / se_pooled if se_pooled > 0 else NAN
    p_value = 2 * stats.norm.sf(abs(z)) if se_pooled > 0 else NAN

    se_unpooled = math.sqrt(p_c * (1 - p_c) / n_c + p_t * (1 - p_t) / n_t)
    z_crit = stats.norm.ppf(1 - alpha / 2)
    ci_low = diff - z_crit * se_unpooled
    ci_high = diff + z_crit * se_unpooled

    significant = bool(p_value < alpha) if p_value == p_value else False
    if not significant:
        direction = "none"
    else:
        direction = "increase" if diff > 0 else "decrease"

    return {
        "n_control": int(n_c),
        "n_treatment": int(n_t),
        "conversions_control": int(x_c),
        "conversions_treatment": int(x_t),
        "cr_control": p_c,
        "cr_treatment": p_t,
        "abs_diff": diff,
        "rel_lift_pct": rel_lift,
        "z_stat": z,
        "p_value": p_value,
        "se_pooled": se_pooled,
        "se_unpooled": se_unpooled,
        "ci_low": ci_low,
        "ci_high": ci_high,
        "alpha": alpha,
        "significant": significant,
        "direction": direction,
    }


def _empty_result(alpha: float) -> dict:
    return {
        "n_control": 0,
        "n_treatment": 0,
        "conversions_control": 0,
        "conversions_treatment": 0,
        "cr_control": NAN,
        "cr_treatment": NAN,
        "abs_diff": NAN,
        "rel_lift_pct": NAN,
        "z_stat": NAN,
        "p_value": NAN,
        "se_pooled": NAN,
        "se_unpooled": NAN,
        "ci_low": NAN,
        "ci_high": NAN,
        "alpha": alpha,
        "significant": False,
        "direction": "none",
    }


def sample_ratio_mismatch(n_c: int, n_t: int, expected: float = 0.5) -> dict:
    total = n_c + n_t
    if total == 0:
        return {
            "n_control": 0,
            "n_treatment": 0,
            "observed_ratio": NAN,
            "expected_ratio": expected,
            "chi2": NAN,
            "p_value": NAN,
            "srm_detected": False,
        }
    observed = n_c / total
    expected_counts = [expected * total, (1 - expected) * total]
    chi2, p_value = stats.chisquare([n_c, n_t], f_exp=expected_counts)
    return {
        "n_control": int(n_c),
        "n_treatment": int(n_t),
        "observed_ratio": observed,
        "expected_ratio": expected,
        "chi2": float(chi2),
        "p_value": float(p_value),
        "srm_detected": bool(p_value < SRM_ALPHA),
    }


def chi_square_independence(df: pd.DataFrame, col: str) -> dict:
    table = pd.crosstab(df[col], df["experiment_group"])
    if table.size == 0 or (table.sum(axis=0) == 0).any():
        return {"column": col, "chi2": NAN, "dof": 0, "p_value": NAN, "balanced": False}
    chi2, p_value, dof, _ = stats.chi2_contingency(table, correction=False)
    return {
        "column": col,
        "chi2": float(chi2),
        "dof": int(dof),
        "p_value": float(p_value),
        "balanced": bool(p_value >= 0.01),
    }


def power_for_proportions(p1: float, p2: float, alpha: float = ALPHA, power: float = 0.8, ratio: float = 1.0) -> int:
    if not (0 < p1 < 1) or not (0 < p2 < 1) or p1 == p2:
        return 0
    z_alpha = stats.norm.ppf(1 - alpha / 2)
    z_beta = stats.norm.ppf(power)
    p_bar = (p1 + ratio * p2) / (1 + ratio)
    numerator = (z_alpha * math.sqrt((1 + 1 / ratio) * p_bar * (1 - p_bar)) + z_beta * math.sqrt(
        p1 * (1 - p1) + p2 * (1 - p2) / ratio
    )) ** 2
    return math.ceil(numerator / (p1 - p2) ** 2)


def min_detectable_effect(n_per_arm: int, p: float, alpha: float = ALPHA, power: float = 0.8) -> float:
    if n_per_arm <= 0 or not (0 < p < 1):
        return NAN
    z_alpha = stats.norm.ppf(1 - alpha / 2)
    z_beta = stats.norm.ppf(power)
    se = math.sqrt(2 * p * (1 - p) / n_per_arm)
    abs_mde = (z_alpha + z_beta) * se
    return abs_mde / p * 100
