"""Dev helper: write a deliberately dirty copy of the dataset to exercise data quality."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from abtest.config import RAW_DIR
from abtest.generate import generate_users, write_dataset


def corrupt(df: pd.DataFrame, seed: int = 0) -> pd.DataFrame:
    df = df.copy()
    rng = np.random.default_rng(seed)
    idx = rng.choice(len(df), size=60, replace=False)

    df = pd.concat([df, df.iloc[idx[:8]]], ignore_index=True)
    # duplicate pairs must change mind before concat; do it on the copy first
    flipped = df.iloc[idx[8:14]].copy()
    flipped["experiment_group"] = np.where(flipped["experiment_group"] == "control", "treatment", "control")
    df = pd.concat([df, flipped], ignore_index=True)
    df.loc[idx[14:18], "experiment_group"] = "variant_c"
    df.loc[idx[18:22], "experiment_group"] = None
    df.loc[idx[22:27], "revenue"] = -199.0
    df.loc[idx[27:33], ["viewed_product", "added_to_cart", "purchased"]] = [True, False, True]
    df.loc[idx[33:38], "revenue"] = 1500.0
    df.loc[idx[38:43], "session_date"] = "2026-08-01"
    df.loc[idx[43:47], "device"] = "smart_tv"
    return df


def main() -> None:
    out = RAW_DIR / "experiment_dirty.csv"
    write_dataset(corrupt(generate_users()), out)
    print(f"Wrote dirty dataset to {out}")


if __name__ == "__main__":
    main()
