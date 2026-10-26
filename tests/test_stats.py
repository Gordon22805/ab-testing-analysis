import math

import pytest
from scipy import stats

from abtest.generate import generate_users
from abtest.stats import (
    chi_square_independence,
    min_detectable_effect,
    power_for_proportions,
    sample_ratio_mismatch,
    two_proportion_ztest,
)


def test_known_ztest_values():
    res = two_proportion_ztest(x_c=100, n_c=1000, x_t=120, n_t=1000)
    assert res["cr_control"] == pytest.approx(0.10)
    assert res["cr_treatment"] == pytest.approx(0.12)
    assert res["abs_diff"] == pytest.approx(0.02, abs=1e-12)
    assert res["rel_lift_pct"] == pytest.approx(20.0, abs=1e-9)
    assert res["p_value"] == pytest.approx(0.1529, abs=0.0005)
    # pooled two-proportion z equals the chi-square test of the same 2x2 table
    chi2_p = stats.chi2_contingency([[100, 900], [120, 880]], correction=False)[1]
    assert res["p_value"] == pytest.approx(chi2_p, abs=1e-9)
    assert res["significant"] is False
    assert res["direction"] == "none"


def test_clear_positive_is_significant():
    res = two_proportion_ztest(500, 5000, 600, 5000)
    assert res["significant"] is True
    assert res["direction"] == "increase"
    assert res["ci_low"] > 0


def test_clear_negative_is_significant():
    res = two_proportion_ztest(600, 5000, 500, 5000)
    assert res["direction"] == "decrease"
    assert res["ci_high"] < 0


def test_zero_denominator_returns_nan():
    res = two_proportion_ztest(0, 0, 10, 100)
    assert math.isnan(res["p_value"])
    assert math.isnan(res["ci_low"])
    assert res["significant"] is False


def test_zero_control_rate_returns_nan_lift():
    res = two_proportion_ztest(0, 500, 10, 500)
    assert math.isnan(res["rel_lift_pct"])
    assert res["abs_diff"] == pytest.approx(0.02)


def test_ci_matches_scipy_reference():
    x_c, n_c, x_t, n_t = 340, 4000, 383, 4000
    res = two_proportion_ztest(x_c, n_c, x_t, n_t)
    p_c, p_t = x_c / n_c, x_t / n_t
    se = math.sqrt(p_c * (1 - p_c) / n_c + p_t * (1 - p_t) / n_t)
    z = stats.norm.ppf(0.975)
    assert res["ci_low"] == pytest.approx((p_t - p_c) - z * se)
    assert res["ci_high"] == pytest.approx((p_t - p_c) + z * se)


def test_ci_and_pvalue_agree_on_decision():
    res = two_proportion_ztest(340, 4000, 400, 4000)
    assert (res["ci_low"] > 0) == res["significant"]


def test_identical_groups_not_significant():
    res = two_proportion_ztest(300, 3000, 300, 3000)
    assert res["p_value"] == pytest.approx(1.0)
    assert res["significant"] is False
    assert res["direction"] == "none"


def test_srm_detects_skew():
    assert sample_ratio_mismatch(5000, 5200)["srm_detected"] is False
    assert sample_ratio_mismatch(5000, 6000)["srm_detected"] is True


def test_srm_empty():
    res = sample_ratio_mismatch(0, 0)
    assert res["srm_detected"] is False
    assert math.isnan(res["observed_ratio"])


def test_chi_square_balanced_on_random():
    df = generate_users(2000, seed=3)
    res = chi_square_independence(df, "device")
    assert res["balanced"] is True
    assert res["p_value"] > 0.01


def test_chi_square_detects_imbalance():
    df = generate_users(4000, seed=3)
    mobile = df["device"] == "mobile"
    df.loc[mobile, "experiment_group"] = "treatment"
    res = chi_square_independence(df, "device")
    assert res["balanced"] is False


def test_power_roundtrip():
    n = power_for_proportions(0.085, 0.090)
    assert min_detectable_effect(n, 0.085) <= 5.9
    assert min_detectable_effect(n - 1, 0.085) > 5.0


def test_power_degenerate():
    assert power_for_proportions(0.1, 0.1) == 0
    assert math.isnan(min_detectable_effect(0, 0.1))


def test_ci_width_shrinks_with_sample_size():
    small = two_proportion_ztest(50, 1000, 60, 1000)
    big = two_proportion_ztest(500, 10000, 600, 10000)
    assert (big["ci_high"] - big["ci_low"]) < (small["ci_high"] - small["ci_low"])
