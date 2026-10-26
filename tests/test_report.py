import pandas as pd
import pytest

from abtest.config import MIN_ROLLOUT_LIFT_PCT
from abtest.generate import generate_users
from abtest.metrics import all_segments, funnel, group_metrics, revenue_impact
from abtest.report import (
    DECISIONS,
    _dec,
    _num,
    _p,
    _pct,
    _pp,
    _signed_pct,
    decide,
    inject_readme_results,
)
from abtest.stats import two_proportion_ztest


def _stats(cr_c, cr_t, n=5000, alpha=0.05):
    x_c = int(round(cr_c * n))
    x_t = int(round(cr_t * n))
    return two_proportion_ztest(x_c, n, x_t, n, alpha)


def _segments_with(lift_pct=None, significant=False):
    table = pd.DataFrame(
        [
            {
                "segment": "mobile",
                "users_control": 3000,
                "users_treatment": 3000,
                "cr_control": 0.1,
                "cr_treatment": 0.1 * (1 + (lift_pct or 0) / 100),
                "abs_diff": 0.001,
                "rel_lift_pct": lift_pct or 0.0,
                "p_value": 0.01 if significant else 0.5,
                "ci_low": -0.01,
                "ci_high": 0.02,
                "significant": significant,
            }
        ]
    )
    return {"device": {"table": table, "dropped": [], "column": "device"}}


def test_decide_continue_when_not_significant():
    assert decide(_stats(0.10, 0.101), {}, {}) == "continue"


def test_decide_rollout_when_clear_growth():
    stats = _stats(0.08, 0.10, n=20000)
    assert stats["significant"] is True
    assert decide(stats, {}, _segments_with(5.0, False)) == "roll_out"


def test_decide_no_rollout_when_significant_decrease():
    stats = _stats(0.10, 0.08, n=20000)
    assert stats["direction"] == "decrease"
    assert decide(stats, {}, {}) == "do_not_roll_out"


def test_decide_no_rollout_when_lift_below_threshold():
    stats = _stats(0.10, 0.1015, n=500_000)
    assert stats["significant"] is True
    assert stats["rel_lift_pct"] < MIN_ROLLOUT_LIFT_PCT
    assert decide(stats, {}, {}) == "do_not_roll_out"


def test_decide_no_rollout_when_segment_significantly_worse():
    assert decide(_stats(0.08, 0.10, n=20000), {}, _segments_with(-4.0, True)) == "do_not_roll_out"


def test_decide_ignores_non_significant_segment_drop():
    assert decide(_stats(0.08, 0.10, n=20000), {}, _segments_with(-1.0, False)) == "roll_out"


def test_decide_on_real_data_is_final_id():
    df = generate_users(8000, seed=42)
    gm = group_metrics(df).set_index("experiment_group")
    stats = two_proportion_ztest(
        int(gm.loc["control", "purchasers"]),
        int(gm.loc["control", "users"]),
        int(gm.loc["treatment", "purchasers"]),
        int(gm.loc["treatment", "users"]),
    )
    assert decide(stats, revenue_impact(df), all_segments(df)) in DECISIONS


def test_decide_handles_zero_sample():
    stats = two_proportion_ztest(0, 0, 0, 0)
    assert decide(stats, {}, {}) == "continue"


@pytest.mark.parametrize(
    "formatter, value, expected",
    [
        (_pct, 0.1234, "12,34%"),
        (_pct, float("nan"), "—"),
        (_signed_pct, 9.3456, "+9,35%"),
        (_pp, 0.008991, "+0,90 п.п."),
        (_num, 30000, "30 000"),
        (_p, 0.0004, "< 0,001"),
        (_p, 0.0153, "0,015"),
        (_dec, 2.4248, "2,42"),
        (_dec, 0.05, "0,05"),
    ],
)
def test_formatters(formatter, value, expected):
    assert formatter(value) == expected


def test_num_with_decimals():
    assert _num(2513.6, 2) == "2 513,60"


def test_formatter_pp_keeps_units():
    text = _pp(0.0012)
    assert text.endswith(" п.п.")
    assert "п,п" not in text


def test_readme_injection_replaces_block():
    template = "Один\n<!-- RESULTS:START -->\nстарое\n<!-- RESULTS:END -->\nДва"
    updated = inject_readme_results(template, "<!-- RESULTS:START -->\nновое\n<!-- RESULTS:END -->")
    assert "новое" in updated
    assert "старое" not in updated
    assert updated.startswith("Один")
    assert updated.endswith("Два")


def test_readme_injection_without_markers_is_noop():
    template = "нет маркеров"
    assert inject_readme_results(template, "блок") == template


def test_segments_markdown_uses_russian_labels():
    from abtest.report import _segments_markdown

    table = pd.DataFrame(
        [
            {
                "segment": "paid_search",
                "users_control": 3000,
                "users_treatment": 3000,
                "cr_control": 0.1,
                "cr_treatment": 0.11,
                "abs_diff": 0.01,
                "rel_lift_pct": 10.0,
                "p_value": 0.01,
                "ci_low": 0.002,
                "ci_high": 0.018,
                "significant": True,
            }
        ]
    )
    markdown = _segments_markdown(
        {"traffic_source": {"table": table, "dropped": ["tablet"], "column": "traffic_source"}}
    )
    assert "поиск (платный)" in markdown
    assert "paid_search" not in markdown
    assert "планшеты" in markdown


def test_report_headings_are_russian():
    from abtest.config import DOCS_DIR

    text = (DOCS_DIR / "analysis_report.md").read_text(encoding="utf-8")
    for english in ("## Experiment", "## Metrics", "## Results", "## Final Decision"):
        assert english not in text


def test_small_segments_are_reported_as_dropped():
    from abtest.report import _segments_markdown

    table = pd.DataFrame(
        [
            {
                "segment": "desktop",
                "users_control": 3000,
                "users_treatment": 3000,
                "cr_control": 0.1,
                "cr_treatment": 0.11,
                "abs_diff": 0.01,
                "rel_lift_pct": 10.0,
                "p_value": 0.01,
                "ci_low": 0.002,
                "ci_high": 0.018,
                "significant": True,
            }
        ]
    )
    markdown = _segments_markdown({"device": {"table": table, "dropped": ["tablet"], "column": "device"}})
    assert "планшеты" in markdown
    assert "Исключены из-за малого размера" in markdown


def test_funnel_pcts_present():
    df = generate_users(1000, seed=8)
    fn = funnel(df)
    assert {"control_pct", "treatment_pct"} <= set(fn.columns)
    assert fn["control_pct"].between(0, 1).all()


def test_no_formatter_crashes_on_nan():
    for formatter in (_pct, _signed_pct, _pp, _num, _p, _dec):
        assert formatter(float("nan")) == "—"
