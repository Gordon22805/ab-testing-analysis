"""CLI: build the synthetic experiment dataset."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from abtest.config import DATA_PATH, N_USERS, SEED
from abtest.generate import generate_users, write_dataset


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate synthetic A/B test dataset")
    parser.add_argument("--users", type=int, default=N_USERS)
    parser.add_argument("--seed", type=int, default=SEED)
    parser.add_argument("--out", type=Path, default=DATA_PATH)
    args = parser.parse_args()

    df = generate_users(args.users, args.seed)
    path = write_dataset(df, args.out)
    cr = df.groupby("experiment_group")["purchased"].mean().round(4).to_dict()
    print(f"Wrote {len(df):,} rows to {path}")
    print(f"Raw conversion (not analysed here): {cr}")


if __name__ == "__main__":
    main()
