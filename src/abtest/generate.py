"""Synthetic dataset for the CTA A/B test."""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from abtest.config import EXPERIMENT_DAYS, EXPERIMENT_START, GROUPS, SEED, TRUE_RELATIVE_LIFT

DEVICE_P = {"mobile": 0.68, "desktop": 0.26, "tablet": 0.06}
SOURCE_P = {"organic": 0.34, "paid_search": 0.28, "social": 0.18, "email": 0.12, "referral": 0.08}
COUNTRY_P = {"RU": 0.75, "KZ": 0.12, "BY": 0.07, "UA": 0.06}
VISITOR_P = {"new": 0.62, "returning": 0.38}

CART_DEVICE = {"mobile": 1.0, "desktop": 0.8, "tablet": 0.9}
CART_SOURCE = {"organic": 1.0, "paid_search": 1.15, "social": 0.85, "email": 1.1, "referral": 0.9}
CART_VISITOR = {"new": 0.9, "returning": 1.25}

BUY_DEVICE = {"mobile": 0.95, "desktop": 1.12, "tablet": 0.9}
BUY_SOURCE = {"organic": 1.05, "paid_search": 0.9, "social": 0.88, "email": 1.1, "referral": 1.0}
BUY_VISITOR = {"new": 0.85, "returning": 1.2}

TICKET_DEVICE = {"mobile": 1.0, "desktop": 1.15, "tablet": 1.05}

WEEKDAY_WEIGHTS = np.array([0.95, 1.0, 1.0, 1.0, 1.05, 1.1, 1.05])

CART_BASE = 0.22
BUY_BASE = 0.42
VIEW_PROB = 0.96


def _pick(rng: np.random.Generator, n: int, probs: dict[str, float]) -> np.ndarray:
    keys = np.array(list(probs))
    weights = np.array(list(probs.values()))
    return rng.choice(keys, size=n, p=weights / weights.sum())


def _multipliers(values: np.ndarray, table: dict[str, float]) -> np.ndarray:
    return np.vectorize(table.__getitem__)(values)


def generate_users(n: int = 30_000, seed: int = SEED) -> pd.DataFrame:
    rng = np.random.default_rng(seed)

    group = rng.choice(GROUPS, size=n, p=[0.5, 0.5])
    device = _pick(rng, n, DEVICE_P)
    source = _pick(rng, n, SOURCE_P)
    country = _pick(rng, n, COUNTRY_P)
    visitor = _pick(rng, n, VISITOR_P)

    viewed = rng.random(n) < VIEW_PROB

    cart_p = (
        CART_BASE
        * _multipliers(device, CART_DEVICE)
        * _multipliers(source, CART_SOURCE)
        * _multipliers(visitor, CART_VISITOR)
    ).clip(max=0.95)
    added = viewed & (rng.random(n) < cart_p)

    buy_p = BUY_BASE * _multipliers(device, BUY_DEVICE) * _multipliers(source, BUY_SOURCE) * _multipliers(
        visitor, BUY_VISITOR
    )
    buy_p = buy_p * np.where(group == "treatment", 1 + TRUE_RELATIVE_LIFT, 1.0)
    buy_p = buy_p.clip(max=0.95)
    purchased = added & (rng.random(n) < buy_p)

    sigma = 0.55
    ticket = rng.lognormal(mean=np.log(2600) - sigma**2 / 2, sigma=sigma, size=n)
    ticket = ticket * _multipliers(device, TICKET_DEVICE)
    revenue = np.where(purchased, np.round(np.clip(ticket, 199, 29_999), 2), 0.0)

    duration = rng.lognormal(mean=np.log(240), sigma=0.6, size=n) * np.where(purchased, 1.4, 1.0)
    duration = np.clip(duration, 20, 1800).astype(int)

    start = pd.Timestamp(EXPERIMENT_START)
    day_weights = np.tile(WEEKDAY_WEIGHTS, EXPERIMENT_DAYS // len(WEEKDAY_WEIGHTS) + 1)[:EXPERIMENT_DAYS]
    day_idx = rng.choice(EXPERIMENT_DAYS, size=n, p=day_weights / day_weights.sum())
    session_date = start + pd.to_timedelta(day_idx, unit="D")

    return pd.DataFrame(
        {
            "user_id": [f"U{i:06d}" for i in range(1, n + 1)],
            "experiment_group": group,
            "device": device,
            "country": country,
            "traffic_source": source,
            "visitor_type": visitor,
            "session_date": session_date,
            "viewed_product": viewed,
            "added_to_cart": added,
            "purchased": purchased,
            "revenue": revenue,
            "session_duration": duration,
        }
    )


def write_dataset(df: pd.DataFrame, path: str | Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False, date_format="%Y-%m-%d")
    return path
