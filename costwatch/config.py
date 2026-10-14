"""Single place for every tunable number. Nothing else in the package hard-codes a threshold."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
OUT_DIR = ROOT / "outputs"

SHIPMENTS_FILE = "shipment_records.csv"
NOTES_FILE = "context_notes.csv"
FORMAT_FILE = "sample_output_format_v2.csv"

# The output contract (column names and order) from sample_output_format_v2.csv.
OUTPUT_COLUMNS = [
    "route", "week_of", "cost_per_tonne_km", "vs_own_history",
    "vs_similar_routes", "flagged", "matched_note_id", "reason",
]

# --- Baselines (fixed by the brief, do not change) -------------------------------------
BASELINE_WEEKS = 8  # trailing weeks used for "vs own history"

# --- Detector ---------------------------------------------------------------------------
# A week is only judged once the route has a full baseline: with fewer prior weeks the
# average itself is too noisy to call anything "out of the ordinary" (numbers are still
# reported for those weeks).
MIN_PRIOR_WEEKS_TO_FLAG = BASELINE_WEEKS
# Robust z-score (median/MAD of the route's own *prior* weeks) needed to call a single
# route-week unusual on its own.
Z_STRONG = 3.0
# Lower bar, only used when many routes rise in the same week (market-wide event, e.g. fuel).
Z_MARKET = 1.5
MARKET_MIN_ROUTES = 4
MARKET_MIN_SHARE = 0.5
# Weekly noise is ~3% (only 3-5 shipments/week). Floors stop a lucky-quiet history from
# producing a tiny spread and a huge z-score. Calibrated on the 2024 quiet period.
OWN_SPREAD_FLOOR = 2.5   # percentage points
PEER_SPREAD_FLOOR = 3.0  # percentage points
MIN_OBS_FOR_SPREAD = 8   # prior observations needed before a z-score is computed

# --- Retrieval --------------------------------------------------------------------------
EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
RETRIEVAL_TOP_K = 5
# A rejected note is only worth citing in an explanation if it is this close in time to the week.
NEAR_NOTE_DAYS = 28
