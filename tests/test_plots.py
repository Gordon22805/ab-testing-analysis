import pytest

from abtest.generate import generate_users
from abtest.metrics import daily_conversion, funnel, group_metrics, revenue_impact, segment_metrics
from abtest.plots import (
    plot_ci,
    plot_conversion,
    plot_dynamics,
    plot_funnel,
    plot_group_sizes,
    plot_revenue_distribution,
    plot_revenue_impact,
    plot_segments,
)
from abtest.stats import two_proportion_ztest


@pytest.fixture(scope="module")
def data():
    return generate_users(6000, seed=5)


def _assert_png(path):
    assert path.exists()
    assert path.suffix == ".png"
    assert path.stat().st_size > 5000


def test_group_sizes_plot(data, tmp_path):
    _assert_png(plot_group_sizes(data, tmp_path / "01.png"))


def test_conversion_plot(data, tmp_path):
    _assert_png(plot_conversion(group_metrics(data), tmp_path / "02.png"))


def test_funnel_plot(data, tmp_path):
    _assert_png(plot_funnel(funnel(data), tmp_path / "03.png"))


def test_ci_plot(data, tmp_path):
    gm = group_metrics(data).set_index("experiment_group")
    stats = two_proportion_ztest(
        int(gm.loc["control", "purchasers"]),
        int(gm.loc["control", "users"]),
        int(gm.loc["treatment", "purchasers"]),
        int(gm.loc["treatment", "users"]),
    )
    _assert_png(plot_ci(stats, tmp_path / "04.png"))


@pytest.mark.parametrize("column", ["device", "traffic_source", "visitor_type"])
def test_segment_plot(data, tmp_path, column):
    table = segment_metrics(data, column)["table"]
    _assert_png(plot_segments(table, column, tmp_path / f"05_{column}.png"))


def test_dynamics_plot(data, tmp_path):
    _assert_png(plot_dynamics(daily_conversion(data), tmp_path / "06.png"))


def test_revenue_impact_plot(data, tmp_path):
    _assert_png(plot_revenue_impact(revenue_impact(data), tmp_path / "07.png"))


def test_revenue_distribution_plot(data, tmp_path):
    _assert_png(plot_revenue_distribution(data, tmp_path / "08.png"))
