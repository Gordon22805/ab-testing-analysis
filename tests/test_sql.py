import pytest

from abtest.config import ROOT, SQL_DIR
from abtest.data_quality import clean
from abtest.generate import generate_users
from abtest.metrics import group_metrics, segment_metrics
from abtest.sql_check import build_mirror, run_all


@pytest.fixture(scope="module")
def sql_results():
    df, _, _ = clean(generate_users(8000, seed=11))
    con = build_mirror(df)
    results = run_all(con, SQL_DIR)
    yield df, results
    con.close()


def test_all_sql_files_present():
    names = sorted(p.name for p in SQL_DIR.glob("*.sql"))
    assert names == [
        "01_experiment_overview.sql",
        "02_conversion.sql",
        "03_segments.sql",
        "04_revenue.sql",
    ]


def test_every_statement_returns_rows(sql_results):
    _, results = sql_results
    for name, frames in results.items():
        assert frames, f"{name} did not run"
        for frame in frames:
            assert not frame.empty, f"{name} returned nothing"


def test_overview_matches_dataframe(sql_results):
    df, results = sql_results
    overview = results["01_experiment_overview.sql"][0].set_index("experiment_group")
    gm = group_metrics(df).set_index("experiment_group")
    for group in ("control", "treatment"):
        assert overview.loc[group, "users"] == gm.loc[group, "users"]
        assert overview.loc[group, "viewers"] == gm.loc[group, "viewers"]


def test_conversion_query_matches_python(sql_results):
    df, results = sql_results
    row = results["02_conversion.sql"][0].iloc[0]
    gm = group_metrics(df).set_index("experiment_group")
    assert row["cr_control_pct"] == pytest.approx(gm.loc["control", "conversion_rate"] * 100, abs=0.001)
    assert row["cr_treatment_pct"] == pytest.approx(gm.loc["treatment", "conversion_rate"] * 100, abs=0.001)
    expected_lift = (gm.loc["treatment", "conversion_rate"] - gm.loc["control", "conversion_rate"]) / gm.loc[
        "control", "conversion_rate"
    ] * 100
    assert row["relative_lift_pct"] == pytest.approx(expected_lift, abs=0.01)


def test_segments_query_matches_python(sql_results):
    df, results = sql_results
    table = results["03_segments.sql"][0].set_index("segment")
    py = segment_metrics(df, "device")["table"].set_index("segment")
    assert set(table.index) == set(py.index)
    for segment in py.index:
        assert table.loc[segment, "abs_diff_pp"] == pytest.approx(py.loc[segment, "abs_diff"] * 100, abs=0.001)


def test_revenue_share_sums_to_100(sql_results):
    _, results = sql_results
    frames = results["04_revenue.sql"]
    assert len(frames) == 2
    assert frames[1]["revenue_share_pct"].sum() == pytest.approx(100, abs=0.5)


def test_schema_parses_in_sqlite():
    con = build_mirror(clean(generate_users(200, seed=2))[0])
    tables = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    assert {"experiments", "users", "events"} <= tables
    with pytest.raises(Exception):
        con.execute(
            "INSERT INTO events (user_id, experiment_id, experiment_group, session_date, device, traffic_source,"
            " viewed_product, added_to_cart, purchased, revenue, session_duration)"
            " VALUES ('U000001','cta_buy_now_2026_09','control','2026-09-01','mobile','organic',1,0,0,-5,10)"
        )
    con.close()


def test_postgres_schema_file_contains_core_tables():
    schema = (ROOT / "database" / "schema.sql").read_text(encoding="utf-8")
    for table in ("CREATE TABLE experiments", "CREATE TABLE users", "CREATE TABLE events"):
        assert table in schema
    assert "CHECK (experiment_group IN ('control', 'treatment'))" in schema
    assert "CHECK (revenue >= 0)" in schema
