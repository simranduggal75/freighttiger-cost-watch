# costwatch: a shipping-cost watchdog that cannot invent reasons

Watches freight cost per tonne-km, route by route and week by week. Flags rises that look
unjustified, and explains each verdict using **only** the supplied notes, quoted verbatim.
If no note genuinely applies, it says so and sends the row for human review.

## Run it

```bash
pip install -r requirements.txt
# put shipment_records.csv, context_notes.csv, sample_output_format_v2.csv in data/
python -m costwatch run                      # writes outputs/
python -m costwatch ask "why did Chennai-Bangalore get pricier in March?"
python eval/run_eval.py                      # labeled set + citation audit + threshold sweep
python scripts/repro_check.py                # 3 fresh runs, byte-for-byte comparison
python -m pytest -q                          # 33 tests
```

Retrieval uses `all-MiniLM-L6-v2` from the local Hugging Face cache; if it is not cached the
run falls back to TF-IDF automatically (verdicts are identical, only the retrieval trace differs).
Cache it once with `python -c "from sentence_transformers import SentenceTransformer as S; S('sentence-transformers/all-MiniLM-L6-v2')"`.

## What it produces (`outputs/`)

| file | what |
|---|---|
| `output.csv` | **The deliverable.** One row per route-week that needed a verdict, in the exact column contract of `sample_output_format_v2.csv`. |
| `weekly_metrics_full.csv` | All 728 route-weeks with the underlying numbers, z-scores and verdicts. |
| `retrieval_trace.csv` | For every reviewed week: which notes the vector search returned, in rank order. |
| `note_facts.csv` | How each note was read: scope, effect, dates, magnitude, and how the window was derived. |
| `eval_report.md`, `repro_report.md`, `cost_log.md` | Evidence for correctness, repeatability, cost. |

**Result of the run:** 22 weeks reviewed, 7 justified (each citing a note), 15 flagged as unexplained.

| route | weeks | verdict | why |
|---|---|---|---|
| Delhi-Jaipur | 11 & 18 Nov 2024 | flagged | +35% / +28%; no note anywhere near |
| Ahmedabad-Mumbai | 20 Jan 2025 | justified N002 | festival-week surcharge on this corridor |
| Chennai-Bangalore | 24 Feb, 3 Mar 2025 | justified N001 | flood disruption 24 Feb - 8 Mar |
| Chennai-Bangalore | 10 & 17 Mar 2025 | **flagged** | still +22% / +14%, but N001 ended 8 Mar and N009 says normal |
| 4 routes | 5 May 2025 | justified N003 | diesel rise of ~5-7% across all routes |
| Mumbai-Delhi | 12 May 2025 | **flagged** | +11.6% is about twice what N003 can account for |
| Mumbai-Pune | 10 weeks, Sep-Dec 2025 | flagged | slow creep, +23% to +39% vs similar routes; N006 / N010 are decoys |

## How it works

```
shipments --> weekly cost per tonne-km --> baselines --> detector --> retrieval --> verdict gate --> explanation
 (metrics.py)                (metrics.py)               (detect.py)  (retrieval.py)  (verdict.py)    (explain.py)
                                                                          ^
                                          notes --> structured facts (notes.py)
```

1. **Weekly metric.** `cost / (tonnes x km)` summed over each Monday-Sunday week per route (ratio of
   sums, so a big shipment counts more than a small one). 7 routes x 104 weeks, no gaps.
2. **Baselines, exactly as the brief defines them.**
   *vs own history* = mean of the weekly values in the up-to-8 weeks strictly before this one; with
   fewer than 8 prior weeks, all available weeks are used, never padded (this affects only the first 8
   weeks of 2024). *vs similar routes* = mean of the other routes of the same `route_type` that week.
   These reproduce the three rows in the sample file to the digit.
3. **Detector** (see below) picks the weeks worth a verdict.
4. **Retrieval.** For each such week, a metadata filter keeps notes scoped to that route or to
   "All Routes", then a hybrid score ranks them: embedding similarity + route-name match + closeness in time.
5. **Verdict gate.** Pure code on the structured note facts. A note justifies a week only if its scope,
   effect, dates and size all fit. Otherwise the week is flagged.
6. **Explanation.** Template sentences filled with computed numbers and the note's own text.

### Detector: why not a flat threshold?

Two facts in the data drove the design:

- **Weekly noise is ~3%** (3-5 shipments per week), so "flag anything above +5%" drowns in false alarms.
- **The gap to similar routes is structural.** Mumbai-Pune sits ~10% above Delhi-Jaipur even in quiet
  weeks; Delhi-Jaipur sits ~9% below. A raw peer threshold would flag Mumbai-Pune forever.

So each signal is a **robust z-score against the route's own past** (median and MAD of that route's
*prior* weeks only, so there is no look-ahead):

| signal | triggers when |
|---|---|
| own history | cost is rising and z >= 3.0 |
| similar routes | cost is rising and the *gap to peers* is z >= 3.0 above that route's usual gap |
| market-wide | >= 4 routes (and >= half) are each z >= 1.5 in the same week, which is how a fuel move shows up |

A week is judged only once the route has a full 8-week baseline. Calibration on the quiet period
(Jan - Oct 2024: 301 route-weeks, 245 of them with a full baseline) gives **0 false alarms**; `eval_report.md` shows what happens at looser
thresholds (z = 2.5 starts producing one).

### Verdict gate: the rules that stop hallucination

A note can justify a week only if **all** hold:

1. **Scope**: names this route, or "All Routes".
2. **Effect**: says costs went *up*. Notes saying "not affected", "returned to normal", "absorbed without a
   rate change", "not part of this dataset", or "improved road conditions" can never justify.
3. **Window**: the week overlaps the dates the note is in force. A persistent step ("starting this week")
   only counts while the 8-week baseline still straddles it, after which the rise is no longer a rise.
4. **Size**: if the note quantifies the effect (N003: 5-7%), the observed rise may not exceed it by more
   than ordinary noise.
5. **Relative**: a cause that hits all routes equally cannot explain a gap versus similar routes.

Anything that fails is `Yes` (flagged), `matched_note_id` blank. The closest relevant note is still named in the
reason (as in the sample file), but only if it is within 4 weeks of the week; otherwise the reason says
"No matching note found". Note text that cannot be classified defaults to "no effect": the failure mode is
a missed justification, never a false one.

## How I convinced myself it is right

- **Sample rows reproduce exactly** (4.17 / +35.5% / +21.0%, 3.29 / +29.5% / +22.5%, 3.98 / +9.2% / +23.6%).
- **33 tests**: week boundaries, ratio-of-sums, baseline excludes current week and never pads, peers exclude
  the route itself, and 14 adversarial verdict cases (wrong route, wrong window, "not affected" note,
  "back to normal" note, note that starts later, expired step, rise larger than the note, all-routes cause vs peers).
- **Labeled set** (`eval/labeled_cases.csv`, 22 weeks incl. decoy-note dates): 22/22. Caveat: I wrote the labels
  from the notes and a read of the data, so this is a regression set, not independent ground truth.
- **Citation audit**: every justified row is re-checked against a hand-written truth table
  (`eval/note_truth.py`) that does not use the parser. 0 problems.
- **Quiet-period check**: no review rows before 28 Oct 2024.
- **Threshold sweep** in `eval_report.md` shows the choice is not knife-edge.

## Reproducibility

`scripts/repro_check.py` runs the pipeline three times in fresh processes with different `PYTHONHASHSEED`s
and compares SHA-256 of every output. Result: identical (see `outputs/repro_report.md`). Nothing is random:
no sampling, no LLM, exact vector search, ties broken by note id, no timestamps in outputs.

## Cost

One full run: **0 LLM calls, 0 tokens, $0**. Embeddings are a small open-source model on CPU (32 short texts).
A deliberate trade-off: with 10 short notes, structured extraction plus templates is cheaper, exactly
repeatable and cannot fabricate; an LLM would only polish wording. See `outputs/cost_log.md` for the
projection if one were added.

## Assumptions and limitations

- **Output scope.** `output.csv` holds weeks that needed a verdict (like the sample); the full grid is in
  `weekly_metrics_full.csv`. First 8 weeks of each route are never flagged (`No (insufficient history)`).
- **Sensitivity limit.** A +5% diesel step on a single route is inside the noise. It is caught only when
  several routes move together, so on 5 May 2025 three of seven routes (Ahmedabad-Mumbai, Chennai-Bangalore,
  Kolkata-Bhubaneswar) are not listed even though they rose slightly.
- **Policy call.** Mumbai-Delhi 12 May 2025 (+11.6%) is flagged although diesel partly explains it, because the
  note supports ~6% and the rest is unexplained. A "partial" verdict would be a natural extension.
- **Rule-based note reader.** Reliable on these 10 notes; new phrasing may need new cues. An LLM extractor
  with schema validation is the natural upgrade, and its output would still pass through the same gate.
- **Two-route groups.** Short and Long have two routes each, so "similar routes" is a single other route.
  Normalising by the route's own usual gap keeps this usable but noisier.
- **Direction-sensitive routes.** `Mumbai-Delhi` and `Delhi-Mumbai` would be different routes.
- Thresholds were calibrated on this one dataset.

## Layout

```
costwatch/   metrics.py detect.py notes.py retrieval.py verdict.py explain.py pipeline.py qa.py cli.py config.py
tests/       metrics, notes, verdict (adversarial), end-to-end
eval/        labeled_cases.csv, note_truth.py, run_eval.py
scripts/     repro_check.py
outputs/     generated deliverables and evidence
```

All tunable numbers live in `costwatch/config.py`.
