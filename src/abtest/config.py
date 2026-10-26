from pathlib import Path

SEED = 42
N_USERS = 30_000
GROUPS = ("control", "treatment")
GROUP_LABELS = {"control": "A (Control)", "treatment": "B (Treatment)"}

ALPHA = 0.05
SRM_ALPHA = 0.001
EXPECTED_SPLIT = 0.5

EXPERIMENT_START = "2026-09-01"
EXPERIMENT_DAYS = 21
PRIMARY_METRIC = "conversion_rate"

# True relative lift baked into the simulator. The analysis never reads this.
TRUE_RELATIVE_LIFT = 0.06

MIN_SEGMENT_USERS = 200
IMPACT_TARGET_USERS = 10_000
MIN_ROLLOUT_LIFT_PCT = 2.0

ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = ROOT / "data" / "raw"
SAMPLE_PATH = ROOT / "data" / "sample_experiment.csv"
DATA_PATH = RAW_DIR / "experiment.csv"
RESULTS_DIR = ROOT / "results"
RESULTS_PATH = RESULTS_DIR / "results.json"
FIGURES_DIR = RESULTS_DIR / "figures"
DOCS_DIR = ROOT / "docs"
SQL_DIR = ROOT / "sql"
