import pandas as pd
import pytest
from scipy.stats import chi2_contingency

from abtest.generate import generate_users

EXPECTED_COLUMNS = [
    "user_id",
    "experiment_group",
    "device",
    "country",
    "traffic_source",
    "visitor_type",
    "session_date",
    "viewed_product",
    "added_to_cart",
    "purchased",
    "revenue",
    "session_duration",
]


@pytest.fixture(scope="module")
def df() -> pd.DataFrame:
    return generate_users()


def test_shape_and_columns(df):
    assert len(df) == 30_000
    assert list(df.columns) == EXPECTED_COLUMNS
    assert df["user_id"].is_unique


def test_groups_balanced(df):
    share = df["experiment_group"].value_counts(normalize=True)
    assert set(share.index) == {"control", "treatment"}
    assert 0.48 < share.min() < 0.52


def test_funnel_logic_valid(df):
    assert (df["purchased"] & ~df["added_to_cart"]).sum() == 0
    assert (df["added_to_cart"] & ~df["viewed_product"]).sum() == 0


def test_revenue_matches_purchase(df):
    assert (df.loc[~df["purchased"], "revenue"] == 0).all()
    assert (df.loc[df["purchased"], "revenue"] > 0).all()


def test_deterministic():
    pd.testing.assert_frame_equal(generate_users(1_000, seed=7), generate_users(1_000, seed=7))


def test_effect_is_small(df):
    diff = df.groupby("experiment_group")["purchased"].mean().diff().dropna().abs().iloc[0]
    assert diff < 0.02


@pytest.mark.parametrize("column", ["device", "traffic_source", "visitor_type"])
def test_covariates_independent_of_group(df, column):
    table = pd.crosstab(df[column], df["experiment_group"])
    p_value = chi2_contingency(table, correction=False)[1]
    assert p_value > 0.01
