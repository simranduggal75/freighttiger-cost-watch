"""End-to-end run: shipments + notes -> output.csv (+ audit files)."""
from __future__ import annotations

import csv
import json
import math
from pathlib import Path

import pandas as pd

from . import config, detect, explain, metrics, notes as notes_mod, retrieval, verdict

NA_OWN = "n/a (fewer than 1 prior week)"
NA_PEER = "n/a (no other route of this type that week)"


def _own_text(v: float) -> str:
    return NA_OWN if math.isnan(v) else f"{v:+.1f}% vs this route's past average"


def _peer_text(v: float) -> str:
    return NA_PEER if math.isnan(v) else f"{v:+.1f}% vs similar-length routes this week"


def _check_contract(data_dir: Path) -> None:
    fmt = data_dir / config.FORMAT_FILE
    if fmt.exists():
        header = fmt.read_text(encoding="utf-8").splitlines()[0].strip().split(",")
        if header != config.OUTPUT_COLUMNS:
            raise ValueError(f"output columns {config.OUTPUT_COLUMNS} do not match {header}")


def run(data_dir: Path = config.DATA_DIR, out_dir: Path = config.OUT_DIR, backend: str = "auto") -> dict:
    data_dir, out_dir = Path(data_dir), Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    _check_contract(data_dir)

    shipments, dropped = metrics.load_shipments(data_dir / config.SHIPMENTS_FILE)
    weekly = detect.add_signals(metrics.add_baselines(metrics.weekly_metrics(shipments)))
    note_facts = notes_mod.load_notes(data_dir / config.NOTES_FILE)
    index = retrieval.NoteIndex(note_facts, backend=backend)

    verdict_code, matched, reason, flagged, trace = [], [], [], [], []
    for r in weekly.itertuples():
        if not r.candidate:
            verdict_code.append("normal")
            matched.append("")
            reason.append("")
            flagged.append("No (insufficient history)" if r.own_weeks_used < config.MIN_PRIOR_WEEKS_TO_FLAG else "No")
            continue
        week = r.week_of.date()
        peer = None if math.isnan(r.vs_peer_pct) else r.vs_peer_pct
        hits = index.search(retrieval.candidate_query(r.route, week.isoformat()), r.route, week)
        trace += [{"route": r.route, "week_of": week.isoformat(), "rank": i + 1, "note_id": n.note_id,
                   "hybrid_score": hybrid, "cosine": cos} for i, (n, hybrid, cos) in enumerate(hits)]
        v = verdict.decide([n for n, _, _ in hits], r.route, week, r.vs_own_pct, r.own_spread, r.trigger)
        verdict_code.append(v.code)
        matched.append(v.note.note_id if v.justified else "")
        flagged.append("No (justified)" if v.justified else "Yes")
        reason.append(explain.render_reason(v, week, r.vs_own_pct, peer))

    weekly["verdict"], weekly["flagged"] = verdict_code, flagged
    weekly["matched_note_id"], weekly["reason"] = matched, reason

    table = pd.DataFrame({
        "route": weekly.route,
        "week_of": weekly.week_of.dt.strftime("%Y-%m-%d"),
        "cost_per_tonne_km": weekly.cost_per_tonne_km.round(2),
        "vs_own_history": [_own_text(v) for v in weekly.vs_own_pct],
        "vs_similar_routes": [_peer_text(v) for v in weekly.vs_peer_pct],
        "flagged": weekly.flagged,
        "matched_note_id": weekly.matched_note_id,
        "reason": weekly.reason,
    })[config.OUTPUT_COLUMNS]

    review = table[weekly.candidate.to_numpy()]
    review.to_csv(out_dir / "output.csv", index=False, lineterminator="\n", quoting=csv.QUOTE_MINIMAL)

    full = weekly.assign(week_of=weekly.week_of.dt.strftime("%Y-%m-%d"))[[
        "route", "route_type", "week_of", "shipments", "freight_cost_inr", "tonne_km",
        "cost_per_tonne_km", "own_avg", "own_weeks_used", "peer_avg", "peers_used",
        "vs_own_pct", "vs_peer_pct", "z_own", "z_peer", "trigger", "candidate", "flagged",
        "verdict", "matched_note_id"]]
    full.round(4).to_csv(out_dir / "weekly_metrics_full.csv", index=False, lineterminator="\n")

    pd.DataFrame(trace).to_csv(out_dir / "retrieval_trace.csv", index=False, lineterminator="\n")

    facts = pd.DataFrame([{
        "note_id": n.note_id, "note_date": n.note_date, "applies_to": n.applies_to,
        "effect": n.effect, "window_start": n.window_start, "window_end": n.window_end or "open-ended",
        "magnitude_pct": n.magnitude_pct or "", "window_basis": n.window_basis} for n in note_facts])
    facts.to_csv(out_dir / "note_facts.csv", index=False, lineterminator="\n")

    summary = {
        "route_weeks": int(len(weekly)),
        "candidates": int(weekly.candidate.sum()),
        "flagged_unexplained": int((weekly.flagged == "Yes").sum()),
        "justified": int((weekly.flagged == "No (justified)").sum()),
        "dropped_invalid_shipments": dropped,
        "retrieval_backend": index.backend,
        "llm_calls": 0, "llm_input_tokens": 0, "llm_output_tokens": 0, "llm_cost_usd": 0.0,
        "embedding_texts": index.texts_embedded, "embedding_tokens": index.tokens_embedded,
        "settings": {k: getattr(config, k) for k in (
            "BASELINE_WEEKS", "MIN_PRIOR_WEEKS_TO_FLAG", "Z_STRONG", "Z_MARKET", "MARKET_MIN_ROUTES",
            "MARKET_MIN_SHARE", "OWN_SPREAD_FLOOR", "PEER_SPREAD_FLOOR", "RETRIEVAL_TOP_K")},
    }
    (out_dir / "run_log.json").write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    (out_dir / "cost_log.md").write_text(_cost_log(summary), encoding="utf-8")
    return summary


def _cost_log(s: dict) -> str:
    flagged_rows = s["candidates"]
    return f"""# Cost log (one full run over shipment_records.csv)

Measured by the run itself; regenerated on every `python -m costwatch run`.

| item | value |
|---|---|
| LLM calls | {s["llm_calls"]} |
| LLM input tokens | {s["llm_input_tokens"]} |
| LLM output tokens | {s["llm_output_tokens"]} |
| LLM cost at published rates | ${s["llm_cost_usd"]:.2f} |
| Retrieval backend | `{s["retrieval_backend"]}` |
| Texts embedded locally (10 notes + {flagged_rows} candidate queries) | {s["embedding_texts"]} |
| Embedding tokens (approx., local CPU model) | {s["embedding_tokens"]} |
| Embedding cost | $0.00 (open-source model, runs locally) |

## Why zero LLM calls
Every verdict and every sentence is produced by deterministic code from structured note
facts, so an LLM would add cost and non-determinism without changing a single verdict.
Retrieval uses a small open-source embedding model on CPU.

## If an LLM were added to polish wording (projection, not measured)
About {flagged_rows} short explanations x (~300 input + ~80 output tokens) = roughly
{flagged_rows * 300:,} input / {flagged_rows * 80:,} output tokens per run, with temperature 0.
The verdict, cited note and numbers would stay fixed because they are computed before any wording step.
"""
