"""Score the system against the labeled set, audit every justification, sweep thresholds.

Run after `python -m costwatch run`:   python eval/run_eval.py
Writes outputs/eval_report.md and exits non-zero if any hard check fails.
"""
from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from costwatch import config, detect, metrics  # noqa: E402
from eval.note_truth import NOTE_TRUTH  # noqa: E402


def score_labeled(out: pd.DataFrame) -> tuple[list[str], int, int]:
    labels = pd.read_csv(ROOT / "eval" / "labeled_cases.csv", keep_default_na=False)
    by_key = out.set_index(["route", "week_of"])
    rows, failures = [], 0
    for r in labels.itertuples():
        hit = by_key.loc[(r.route, r.week_of)] if (r.route, r.week_of) in by_key.index else None
        if r.expected == "normal":
            ok, got = hit is None, "absent" if hit is None else hit.flagged
        elif r.expected == "flagged":
            ok = hit is not None and hit.flagged == "Yes" and hit.matched_note_id == ""
            got = "absent" if hit is None else f"{hit.flagged} / {hit.matched_note_id or '-'}"
        else:
            ok = hit is not None and hit.flagged == "No (justified)" and hit.matched_note_id == r.expected_note
            got = "absent" if hit is None else f"{hit.flagged} / {hit.matched_note_id or '-'}"
        failures += 0 if ok else 1
        rows.append(f"| {'PASS' if ok else '**FAIL**'} | {r.route} | {r.week_of} | {r.expected}"
                    f"{' ' + r.expected_note if r.expected_note else ''} | {got} |")
    return rows, len(labels), failures


def audit_citations(out: pd.DataFrame) -> tuple[list[str], int, int]:
    """Independent re-check of every justified row against the hand-written truth table."""
    justified = out[out.flagged == "No (justified)"]
    problems = []
    for r in justified.itertuples():
        t = NOTE_TRUTH.get(r.matched_note_id)
        wk = date.fromisoformat(r.week_of)
        if t is None:
            problems.append(f"{r.route} {r.week_of}: cites unknown note {r.matched_note_id}")
            continue
        if t["route"] not in ("*", r.route):
            problems.append(f"{r.route} {r.week_of}: {r.matched_note_id} is for {t['route']}")
        if not t["raises_cost"]:
            problems.append(f"{r.route} {r.week_of}: {r.matched_note_id} does not describe a cost rise")
        if wk + timedelta(days=6) < t["start"] or wk > t["end"]:
            problems.append(f"{r.route} {r.week_of}: outside {r.matched_note_id} window {t['start']}..{t['end']}")
    unjustified_with_id = out[(out.flagged == "Yes") & (out.matched_note_id != "")]
    for r in unjustified_with_id.itertuples():
        problems.append(f"{r.route} {r.week_of}: flagged row carries matched_note_id {r.matched_note_id}")
    return problems, len(justified), len(problems)


def sweep() -> list[str]:
    """How many review rows (and quiet-2024 false alarms) different thresholds would give."""
    shipments, _ = metrics.load_shipments(config.DATA_DIR / config.SHIPMENTS_FILE)
    base = metrics.add_baselines(metrics.weekly_metrics(shipments))
    original = (config.Z_STRONG, config.Z_MARKET)
    rows = []
    try:
        for z_strong in (2.5, 3.0, 3.5):
            for z_market in (1.25, 1.5, 2.0):
                config.Z_STRONG, config.Z_MARKET = z_strong, z_market
                s = detect.add_signals(base)
                quiet = int((s.candidate & (s.week_of < "2024-10-28")).sum())
                mark = " <- chosen" if (z_strong, z_market) == original else ""
                rows.append(f"| {z_strong} | {z_market} | {int(s.candidate.sum())} | {quiet} |{mark}")
    finally:
        config.Z_STRONG, config.Z_MARKET = original
    return rows


def main() -> int:
    out = pd.read_csv(config.OUT_DIR / "output.csv", keep_default_na=False)
    lab_rows, n_lab, lab_fail = score_labeled(out)
    problems, n_just, n_bad = audit_citations(out)
    sweep_rows = sweep()

    report = [
        "# Evaluation report", "",
        "## 1. Labeled set", "",
        f"{n_lab - lab_fail}/{n_lab} labeled route-weeks behave as expected.", "",
        "| result | route | week_of | expected | got |", "|---|---|---|---|---|", *lab_rows, "",
        "Caveat: labels were written from the notes and a read of the data, so this is a regression "
        "set, not independent ground truth.", "",
        "## 2. Citation audit (hallucination check)", "",
        f"{n_just} justified rows re-checked against a hand-written truth table "
        f"(`eval/note_truth.py`): **{n_bad} problems**.", "",
        *(f"- {p}" for p in problems), "",
        "## 3. Threshold sensitivity", "",
        "| Z_STRONG | Z_MARKET | review rows | false alarms in quiet Jan-Oct 2024 |", "|---|---|---|---|",
        *sweep_rows, "",
    ]
    (config.OUT_DIR / "eval_report.md").write_text("\n".join(report), encoding="utf-8")
    print("\n".join(report))
    return 1 if (lab_fail or n_bad) else 0


if __name__ == "__main__":
    sys.exit(main())
