"""Charts for the report and README."""
from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

from abtest.config import GROUPS, GROUP_LABELS
from abtest.report import _segment_label

COLORS = {"control": "#7f8c9b", "treatment": "#2a7ab9"}
STEP_LABELS = {
    "users": "Визит",
    "viewed": "Просмотр товара",
    "added_to_cart": "В корзину",
    "purchased": "Покупка",
}
SEGMENT_TITLES = {
    "device": "Устройство",
    "traffic_source": "Источник трафика",
    "visitor_type": "Тип посетителя",
}


def _setup() -> None:
    plt.rcParams.update(
        {
            "figure.dpi": 110,
            "font.size": 10,
            "axes.spines.top": False,
            "axes.spines.right": False,
            "axes.grid": True,
            "axes.grid.axis": "y",
            "grid.color": "#e3e6ea",
            "grid.linewidth": 0.8,
            "axes.axisbelow": True,
            "axes.titlesize": 12,
            "axes.titleweight": "bold",
        }
    )


def _save(fig, out: Path) -> Path:
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(out, dpi=150, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return out


def plot_group_sizes(df: pd.DataFrame, out: Path) -> Path:
    _setup()
    counts = df["experiment_group"].value_counts().reindex(GROUPS)
    fig, ax = plt.subplots(figsize=(6, 4))
    bars = ax.bar([GROUP_LABELS[g] for g in GROUPS], counts.values, color=[COLORS[g] for g in GROUPS], width=0.5)
    ax.bar_label(bars, labels=[f"{v:,}".replace(",", " ") for v in counts.values], padding=4)
    ax.set_title("Размер групп")
    ax.set_ylabel("Пользователи")
    ax.set_ylim(0, counts.max() * 1.15)
    return _save(fig, out)


def plot_conversion(gm: pd.DataFrame, out: Path) -> Path:
    _setup()
    gm = gm.set_index("experiment_group").reindex(GROUPS)
    fig, ax = plt.subplots(figsize=(6, 4))
    bars = ax.bar(
        [GROUP_LABELS[g] for g in GROUPS],
        gm["conversion_rate"].values,
        color=[COLORS[g] for g in GROUPS],
        width=0.5,
    )
    ax.bar_label(bars, labels=[f"{v:.2%}" for v in gm["conversion_rate"].values], padding=5)
    ax.set_title("Конверсия: A против B")
    ax.set_ylabel("Доля пользователей с покупкой")
    ax.yaxis.set_major_formatter(matplotlib.ticker.PercentFormatter(1.0, decimals=0))
    ax.set_ylim(0, gm["conversion_rate"].max() * 1.25)
    return _save(fig, out)


def plot_funnel(fn: pd.DataFrame, out: Path) -> Path:
    _setup()
    steps = list(fn.index)
    x = range(len(steps))
    width = 0.38
    fig, ax = plt.subplots(figsize=(8, 4.5))
    for offset, group in zip((-width / 2, width / 2), GROUPS):
        values = fn[group].values
        bars = ax.bar([i + offset for i in x], values, width=width, color=COLORS[group], label=GROUP_LABELS[group])
        ax.bar_label(bars, labels=[f"{v:,}".replace(",", " ") for v in values], padding=3, fontsize=8)
    ax.set_xticks(list(x))
    ax.set_xticklabels([STEP_LABELS[s] for s in steps])
    ax.set_title("Воронка: от визита до покупки")
    ax.set_ylabel("Пользователи")
    ax.legend(frameon=False)
    ax.set_ylim(0, fn[list(GROUPS)].max().max() * 1.15)
    return _save(fig, out)


def plot_ci(stats: dict, out: Path) -> Path:
    _setup()
    diff = stats["abs_diff"] * 100
    low = stats["ci_low"] * 100
    high = stats["ci_high"] * 100
    fig, ax = plt.subplots(figsize=(7, 3.2))
    ax.errorbar(
        [diff],
        [0],
        xerr=[[diff - low], [high - diff]],
        fmt="o",
        color=COLORS["treatment"],
        capsize=6,
        markersize=8,
        linewidth=2,
    )
    ax.axvline(0, color="#c0392b", linestyle="--", linewidth=1.2, label="Нет эффекта")
    ax.set_yticks([])
    ax.set_xlabel("Разница конверсии, п.п.")
    ax.set_title(f"95% ДИ разницы: [{low:+.2f}; {high:+.2f}] п.п., p = {stats['p_value']:.3f}")
    ax.legend(frameon=False, loc="upper right")
    return _save(fig, out)


def plot_segments(table: pd.DataFrame, segment_col: str, out: Path) -> Path:
    _setup()
    labels = [_segment_label(s) for s in table["segment"].tolist()]
    y = range(len(labels))
    height = 0.38
    fig, ax = plt.subplots(figsize=(8, 0.9 + 0.7 * len(labels)))
    for offset, group, column in zip((-height / 2, height / 2), GROUPS, ("cr_control", "cr_treatment")):
        bars = ax.barh([i + offset for i in y], table[column].values, height=height, color=COLORS[group], label=GROUP_LABELS[group])
        ax.bar_label(bars, labels=[f"{v:.2%}" for v in table[column].values], padding=3, fontsize=8)
    ax.set_yticks(list(y))
    ax.set_yticklabels(labels)
    ax.set_title(f"Конверсия по сегментам: {SEGMENT_TITLES.get(segment_col, segment_col).lower()}")
    ax.xaxis.set_major_formatter(matplotlib.ticker.PercentFormatter(1.0, decimals=0))
    ax.set_xlim(0, max(table["cr_control"].max(), table["cr_treatment"].max()) * 1.25)
    ax.grid(axis="x")
    ax.grid(axis="y", visible=False)
    ax.legend(frameon=False, loc="lower right")
    return _save(fig, out)


def plot_dynamics(daily: pd.DataFrame, out: Path) -> Path:
    _setup()
    fig, ax = plt.subplots(figsize=(9, 4))
    for group in GROUPS:
        part = daily[daily["experiment_group"] == group]
        ax.plot(part["session_date"], part["conversion_rate"], color=COLORS[group], alpha=0.3, linewidth=1)
        ax.plot(part["session_date"], part["rolling_cr"], color=COLORS[group], linewidth=2, label=GROUP_LABELS[group])
    ax.set_title("Конверсия по дням (линия — скользящее среднее за 3 дня)")
    ax.set_ylabel("Конверсия")
    ax.set_xlabel("Дата")
    ax.yaxis.set_major_formatter(matplotlib.ticker.PercentFormatter(1.0, decimals=0))
    ax.legend(frameon=False)
    fig.autofmt_xdate()
    return _save(fig, out)


def plot_revenue_impact(impact: dict, out: Path) -> Path:
    _setup()
    labels = ["Нижняя граница 95% ДИ", "Наблюдаемая оценка", "Верхняя граница 95% ДИ"]
    values = [
        impact["extra_revenue_ci_low"],
        impact["extra_revenue"],
        impact["extra_revenue_ci_high"],
    ]
    colors = ["#a9c4d8", COLORS["treatment"], "#a9c4d8"]
    fig, ax = plt.subplots(figsize=(7.5, 4))
    bars = ax.bar(labels, values, color=colors, width=0.55)
    ax.bar_label(bars, labels=[f"{v:,.0f} ₽".replace(",", " ") for v in values], padding=4)
    ax.axhline(0, color="#333", linewidth=0.8)
    ax.set_title(f"Оценка дополнительной выручки на {impact['n_target']:,} пользователей".replace(",", " "))
    ax.set_ylabel("Руб.")
    fig.autofmt_xdate()
    return _save(fig, out)


def plot_revenue_distribution(df: pd.DataFrame, out: Path) -> Path:
    _setup()
    buyers = df[df["purchased"]]
    fig, ax = plt.subplots(figsize=(8, 4))
    for group in GROUPS:
        values = buyers.loc[buyers["experiment_group"] == group, "revenue"].clip(upper=buyers["revenue"].quantile(0.99))
        ax.hist(values, bins=40, alpha=0.55, color=COLORS[group], label=GROUP_LABELS[group], density=True)
    ax.set_title("Распределение чека среди покупателей")
    ax.set_xlabel("Выручка с пользователя, ₽")
    ax.set_ylabel("Плотность")
    ax.legend(frameon=False)
    return _save(fig, out)
