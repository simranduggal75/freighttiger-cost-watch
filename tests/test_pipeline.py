"""End-to-end checks on the real inputs. Skipped automatically if data/ is empty."""
import csv
from pathlib import Path

import pandas as pd
import pytest

from costwatch import config, pipeline

DATA = config.DATA_DIR
pytestmark = pytest.mark.skipif(not (DATA / config.SHIPMENTS_FILE).exists(), reason="input data not present")


@pytest.fixture(scope="module")
def out(tmp_path_factory):
    d = tmp_path_factory.mktemp("out")
    pipeline.run(DATA, d, backend="tfidf")   # tfidf: no model download needed in CI
    return d


def test_output_header_matches_contract(out):
    with open(out / "output.csv", newline="", encoding="utf-8") as fh:
        assert next(csv.reader(fh)) == config.OUTPUT_COLUMNS


def test_every_justified_row_cites_a_note_and_flagged_rows_do_not(out):
    df = pd.read_csv(out / "output.csv", keep_default_na=False)
    just = df[df.flagged == "No (justified)"]
    assert (just.matched_note_id != "").all()
    assert (df[df.flagged == "Yes"].matched_note_id == "").all()
    assert set(df.flagged) <= {"Yes", "No (justified)"}


def test_cited_note_text_appears_verbatim_in_reason(out):
    notes = pd.read_csv(DATA / config.NOTES_FILE, dtype=str).set_index("note_id").note
    df = pd.read_csv(out / "output.csv", keep_default_na=False)
    for r in df[df.matched_note_id != ""].itertuples():
        assert notes[r.matched_note_id] in r.reason


def test_known_sample_rows_reproduce_exactly(out):
    df = pd.read_csv(out / "weekly_metrics_full.csv").set_index(["route", "week_of"])
    dj = df.loc[("Delhi-Jaipur", "2024-11-11")]
    assert round(dj.cost_per_tonne_km, 2) == 4.17
    assert round(dj.vs_own_pct, 1) == 35.5 and round(dj.vs_peer_pct, 1) == 21.0
    mp = df.loc[("Mumbai-Pune", "2025-09-15")]
    assert round(mp.vs_own_pct, 1) == 9.2 and round(mp.vs_peer_pct, 1) == 23.6


def test_quiet_2024_produces_no_review_rows(out):
    df = pd.read_csv(out / "output.csv")
    assert (df.week_of < "2024-10-28").sum() == 0
