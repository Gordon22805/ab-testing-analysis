"""One entry point: generate -> validate -> analyse -> report."""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

import pandas as pd

from abtest import plots
from abtest.config import (
    ALPHA,
    DATA_PATH,
    DOCS_DIR,
    EXPERIMENT_DAYS,
    EXPERIMENT_START,
    FIGURES_DIR,
    IMPACT_TARGET_USERS,
    N_USERS,
    RESULTS_DIR,
    ROOT,
    SAMPLE_PATH,
    SEED,
)
from abtest.data_quality import REQUIRED_COLUMNS, clean
from abtest.generate import generate_users, write_dataset
from abtest.metrics import all_segments, daily_conversion, funnel, group_metrics, revenue_impact
from abtest.report import (
    build_analysis_report,
    build_readme_results,
    build_validation,
    decide,
    inject_readme_results,
)
from abtest.stats import (
    chi_square_independence,
    min_detectable_effect,
    power_for_proportions,
    sample_ratio_mismatch,
    two_proportion_ztest,
)

SAMPLE_ROWS = 2_000


def _json_safe(value):
    if isinstance(value, dict):
        return {k: _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    if isinstance(value, float) and math.isnan(value):
        return None
    return value


def _frame_to_records(df: pd.DataFrame) -> list[dict]:
    return _json_safe(df.to_dict(orient="records"))


def _limited_metrics(df: pd.DataFrame) -> dict:
    gm = group_metrics(df).set_index("experiment_group")
    a = gm.loc["control"]
    b = gm.loc["treatment"]
    atc = two_proportion_ztest(
        int(a["add_to_cart_users"]), int(a["users"]), int(b["add_to_cart_users"]), int(b["users"])
    )
    pr = two_proportion_ztest(
        int(a["purchasers"]), int(a["add_to_cart_users"]), int(b["purchasers"]), int(b["add_to_cart_users"])
    )
    return {
        "atc_diff": b["add_to_cart_rate"] - a["add_to_cart_rate"],
        "atc_test": atc,
        "pr_diff": b["purchase_rate"] - a["purchase_rate"],
        "pr_test": pr,
        "rpu_diff": b["revenue_per_user"] - a["revenue_per_user"],
        "rpp_diff": b["revenue_per_purchaser"] - a["revenue_per_purchaser"],
    }


def run(out_dir: Path, data_path: Path, generate: bool) -> dict:
    if generate or not data_path.exists():
        write_dataset(generate_users(N_USERS, SEED), data_path)
    if generate or not SAMPLE_PATH.exists():
        write_dataset(generate_users(SAMPLE_ROWS, SEED), SAMPLE_PATH)

    raw = pd.read_csv(data_path, parse_dates=["session_date"])
    missing = [c for c in REQUIRED_COLUMNS if c not in raw.columns]
    if missing:
        raise SystemExit(f"В файле нет обязательных колонок: {missing}")

    df, quality, dropped = clean(raw)
    if df.empty:
        raise SystemExit("После очистки не осталось данных.")

    gm = group_metrics(df)
    fn = funnel(df)
    daily = daily_conversion(df)

    gm_idx = gm.set_index("experiment_group")
    stats = two_proportion_ztest(
        int(gm_idx.loc["control", "purchasers"]),
        int(gm_idx.loc["control", "users"]),
        int(gm_idx.loc["treatment", "purchasers"]),
        int(gm_idx.loc["treatment", "users"]),
    )
    srm = sample_ratio_mismatch(stats["n_control"], stats["n_treatment"])
    randomization = [chi_square_independence(df, col) for col in ("device", "traffic_source", "visitor_type")]
    segments = all_segments(df)
    limited = _limited_metrics(df)
    impact = revenue_impact(df, IMPACT_TARGET_USERS, ALPHA)
    decision = decide(stats, impact, segments)

    n_per_arm = min(stats["n_control"], stats["n_treatment"])
    planning = {
        "observed_cr_control": stats["cr_control"],
        "required_n_per_arm_for_10pct": power_for_proportions(stats["cr_control"], stats["cr_control"] * 1.10),
        "required_n_per_arm_for_5pct": power_for_proportions(stats["cr_control"], stats["cr_control"] * 1.05),
        "mde_pct": min_detectable_effect(n_per_arm, stats["cr_control"]),
    }

    window_text = (
        f"{pd.Timestamp(EXPERIMENT_START):%d.%m.%Y} — "
        f"{pd.Timestamp(EXPERIMENT_START) + pd.Timedelta(days=EXPERIMENT_DAYS - 1):%d.%m.%Y}"
    )

    negative_segments = [
        f"{res['column']}={row['segment']} ({row['rel_lift_pct']:+.2f}%)"
        for res in segments.values()
        for _, row in res["table"].iterrows()
        if row["significant"] and row["rel_lift_pct"] < 0
    ]
    heterogeneity_text = (
        "значимое ухудшение в сегментах: " + ", ".join(negative_segments) + "."
        if negative_segments
        else "ни в одном сегменте нет статистически значимого снижения conversion rate."
    )

    balance_ok = all(r["balanced"] for r in randomization)
    conclusion = (
        "Эксперимент корректен: SRM не обнаружен, сегменты сбалансированы, контаминации пользователей нет. "
        "Результаты можно интерпретировать."
        if (not srm["srm_detected"] and balance_ok)
        else "Внимание: обнаружены проблемы валидации. Результатам нельзя доверять без дополнительной проверки "
        "механики разбиения, даже если статистика показывает значимый эффект."
    )
    srm["window"] = f"{window_text}, {EXPERIMENT_DAYS} дней эксперимента, все строки вне окна удалены."
    srm["conclusion"] = conclusion

    figures = {
        "01_group_sizes": plots.plot_group_sizes(df, FIGURES_DIR / "01_group_sizes.png"),
        "02_conversion": plots.plot_conversion(gm, FIGURES_DIR / "02_conversion.png"),
        "03_funnel": plots.plot_funnel(fn, FIGURES_DIR / "03_funnel.png"),
        "04_confidence_interval": plots.plot_ci(stats, FIGURES_DIR / "04_confidence_interval.png"),
        "06_dynamics": plots.plot_dynamics(daily, FIGURES_DIR / "06_dynamics.png"),
        "07_revenue_impact": plots.plot_revenue_impact(impact, FIGURES_DIR / "07_revenue_impact.png"),
        "08_revenue_distribution": plots.plot_revenue_distribution(df, FIGURES_DIR / "08_revenue_distribution.png"),
    }
    for col, res in segments.items():
        figures[f"05_segments_{col}"] = plots.plot_segments(
            res["table"], col, FIGURES_DIR / f"05_segments_{col}.png"
        )

    context = {
        "rows_raw": len(raw),
        "rows_clean": len(df),
        "rows_dropped": len(dropped),
        "quality": quality,
        "group_metrics": gm,
        "funnel": fn,
        "daily": daily,
        "stats": stats,
        "srm": srm,
        "randomization": randomization,
        "segments": segments,
        "segments_markdown": "",
        "impact": impact,
        "decision": decision,
        "limited_metrics": limited,
        "n_per_arm": n_per_arm,
        "mde_pct": planning["mde_pct"],
        "window_text": window_text,
        "heterogeneity_text": heterogeneity_text,
    }
    from abtest.report import _segments_markdown

    context["segments_markdown"] = _segments_markdown(segments)

    payload = {
        "meta": {
            "seed": SEED,
            "n_users_requested": N_USERS,
            "rows_raw": len(raw),
            "rows_clean": len(df),
            "rows_dropped": len(dropped),
            "experiment_start": EXPERIMENT_START,
            "experiment_days": EXPERIMENT_DAYS,
            "alpha": ALPHA,
        },
        "data_quality": _frame_to_records(quality),
        "groups": _frame_to_records(gm),
        "funnel": _frame_to_records(fn.reset_index().rename(columns={"index": "step"})),
        "primary_test": stats,
        "srm": srm,
        "randomization": randomization,
        "segments": {
            col: {
                "table": _frame_to_records(res["table"]),
                "dropped": res["dropped"],
            }
            for col, res in segments.items()
        },
        "limited_metrics": {
            "add_to_cart": limited["atc_test"],
            "purchase_rate": limited["pr_test"],
            "rpu_diff": limited["rpu_diff"],
            "rpp_diff": limited["rpp_diff"],
        },
        "planning": planning,
        "business_impact": impact,
        "decision": decision,
        "figures": sorted(str(p.relative_to(ROOT)).replace("\\", "/") for p in figures.values()),
    }

    out_dir.mkdir(parents=True, exist_ok=True)
    results_path = out_dir / "results.json"
    results_path.write_text(json.dumps(_json_safe(payload), indent=2, ensure_ascii=False), encoding="utf-8")

    docs_dir = DOCS_DIR
    docs_dir.mkdir(parents=True, exist_ok=True)
    (docs_dir / "experiment_validation.md").write_text(build_validation(context), encoding="utf-8")
    (docs_dir / "analysis_report.md").write_text(build_analysis_report(context), encoding="utf-8")

    readme_path = ROOT / "README.md"
    if readme_path.exists():
        readme_text = readme_path.read_text(encoding="utf-8")
        updated = inject_readme_results(readme_text, build_readme_results(context))
        if updated != readme_text:
            readme_path.write_text(updated, encoding="utf-8")

    _print_summary(stats, srm, decision, len(raw), len(df))
    return payload


def _print_summary(stats: dict, srm: dict, decision: str, rows_raw: int, rows_clean: int) -> None:
    print(f"Строк: {rows_raw:,} -> {rows_clean:,}".replace(",", " "))
    print(f"SRM: {'обнаружен' if srm['srm_detected'] else 'не обнаружен'} (p={srm['p_value']:.4f})")
    print(f"CR control  : {stats['cr_control']:.4%} (n={stats['n_control']})")
    print(f"CR treatment: {stats['cr_treatment']:.4%} (n={stats['n_treatment']})")
    print(f"Abs diff: {stats['abs_diff']:+.4%}  Rel lift: {stats['rel_lift_pct']:+.2f}%")
    print(f"95% CI: [{stats['ci_low']:+.4%}; {stats['ci_high']:+.4%}]  p={stats['p_value']:.4f}")
    print(f"Решение: {decision}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the whole A/B test analysis")
    parser.add_argument("--out-dir", type=Path, default=RESULTS_DIR)
    parser.add_argument("--data", type=Path, default=DATA_PATH)
    parser.add_argument("--no-generate", action="store_true", help="do not regenerate dataset")
    args = parser.parse_args()

    payload = run(args.out_dir, args.data, not args.no_generate)
    if payload["srm"]["srm_detected"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
