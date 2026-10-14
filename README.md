# costwatch: a shipping-cost watchdog that cannot invent reasons

costwatch watches freight **cost per tonne-km**, route by route and week by week. It flags rises that
look unjustified and explains every verdict using **only the supplied notes, quoted verbatim**. When no
note genuinely applies, it says so and sends the week for human review instead of guessing.

> A confident wrong reason is worse than "I could not find one", so the system is built around
> a strict evidence gate rather than around a language model.

## At a glance

| | |
|---|---|
| Data | 2,940 shipments, 7 routes, 104 weeks (Jan 2024 - Dec 2025), 10 notes |
| Output | **22** route-weeks reviewed: **7 justified** (each cites a note), **15 flagged** as unexplained |
| False alarms | **0** in the quiet Jan-Oct 2024 window (301 route-weeks) |
| Hallucination audit | **0 problems** across all justified rows, checked against a hand-written truth table |
| Labeled set | **22 / 22** behave as expected |
| Reproducibility | 3 fresh processes, different hash seeds: **byte-identical** outputs |
| Tests | **33** passing (14 are adversarial cases for the evidence gate) |
| Cost of one full run | **0** LLM calls, 0 tokens, $0 |

## Contents

1. [Quick start](#quick-start)
2. [The problem](#the-problem)
3. [What the data looked like](#what-the-data-looked-like)
4. [How it works](#how-it-works)
5. [Results](#results)
6. [Example output rows](#example-output-rows)
7. [How I know it is right](#how-i-know-it-is-right)
8. [Reproducibility](#reproducibility)
9. [Cost and responsible LLM use](#cost-and-responsible-llm-use)
10. [Design decisions and trade-offs](#design-decisions-and-trade-offs)
11. [Assumptions and limitations](#assumptions-and-limitations)
12. [Configuration](#configuration)
13. [Repository layout and extending it](#repository-layout-and-extending-it)

## Quick start

```bash
pip install -r requirements.txt
# copy shipment_records.csv, context_notes.csv, sample_output_format_v2.csv into data/
python -m costwatch run                      # writes outputs/
python -m costwatch ask "why did Chennai-Bangalore get pricier in March?"
python eval/run_eval.py                      # labeled set + citation audit + threshold sweep
python scripts/repro_check.py                # 3 fresh runs, byte-for-byte comparison
python -m pytest -q                          # 33 tests
```

Retrieval uses `all-MiniLM-L6-v2` from the local Hugging Face cache. If it is not cached the run falls
back to TF-IDF automatically: verdicts are identical, only the retrieval trace differs. To cache the model once:

```bash
python -c "from sentence_transformers import SentenceTransformer as S; S('sentence-transformers/all-MiniLM-L6-v2')"
```

### What a run produces (`outputs/`)

| file | contents |
|---|---|
| `output.csv` | **The deliverable.** One row per route-week that needed a verdict, in the exact column contract of `sample_output_format_v2.csv` (checked at run time). |
| `weekly_metrics_full.csv` | All 728 route-weeks with the underlying numbers, z-scores, triggers and verdicts. |
| `retrieval_trace.csv` | For every reviewed week, which notes the vector search returned and in what order. |
| `note_facts.csv` | How each note was read: scope, effect, dates, magnitude and how the window was derived. |
| `eval_report.md` | Labeled-set score, citation audit and threshold sweep. |
| `repro_report.md` | The 3-run hash comparison. |
| `cost_log.md`, `run_log.json` | Tokens, calls, backend, and every setting used. |

## The problem

Transporters are paid per trip, and cost normally depends on distance and load. Over time a route can get
more expensive for a real reason (fuel, tolls, floods, festival surcharges) or for no good reason. The
assistant must:

1. Group shipments by route and by the provided `route_type` (Short / Medium / Long).
2. Compute weekly cost per tonne-km = total freight cost / (tonnes x km), weeks running Monday to Sunday.
3. Compare each week with **(a)** the route's trailing 8-week average and **(b)** the average of the other
   routes of the same type that week.
4. Flag rises that look out of the ordinary, then check the notes for a real reason, and explain each verdict.
5. Be trustworthy: no invented reasons, identical results on repeat runs, honest cost reporting.

## What the data looked like

I profiled the data before designing anything, because the design depends on it.

| check | finding | consequence |
|---|---|---|
| Quality | no nulls, duplicates, bad dates or non-positive values; one `route_type` per route | no cleaning needed, but the loader still validates and counts dropped rows |
| Coverage | every route has all 104 weeks, 3-5 shipments per week | no gaps in the 8-week window; weekly values are noisy |
| Noise | weekly cost moves about **3%** in quiet periods | a flat "+5%" rule would drown in false alarms |
| Peer gaps | a route's gap to its peers is **structural** (below) | a raw "vs similar routes" threshold would flag one route forever |
| Transporters | every carrier charges the same rate on a given route; Coromandel only runs Delhi-Chennai | transporter mix is not a confound, so per-route aggregation is sound |

Typical gap to similar routes in the quiet 2024 period (median of weekly `vs similar routes`):

| route | typical gap |
|---|---|
| Mumbai-Pune | +10.5% |
| Chennai-Bangalore | +5.0% |
| Delhi-Chennai | +3.7% |
| Kolkata-Bhubaneswar | -0.7% |
| Mumbai-Delhi | -3.6% |
| Ahmedabad-Mumbai | -4.1% |
| Delhi-Jaipur | -9.5% |

## How it works

```
shipments --> weekly cost/tonne-km --> baselines --> detector --> retrieval --> evidence gate --> explanation
 (metrics.py)  (metrics.py)         (metrics.py)  (detect.py)  (retrieval.py)   (verdict.py)    (explain.py)
                                                                      ^
                                           notes --> structured facts (notes.py)
```

### 1. Weekly metric and baselines (`metrics.py`)

The weekly cost per tonne-km is a **ratio of sums**, `sum(cost) / sum(tonnes x km)`, so a 20-tonne load
counts more than a 10-tonne one. The two baselines follow the brief exactly:

- **vs own history**: the mean of the weekly values in the (up to) 8 weeks **strictly before** this one.
  With fewer than 8 prior weeks, all available weeks are used and nothing is padded or extrapolated. This
  only affects the first 8 weeks of 2024.
- **vs similar routes**: the mean of the *other* routes with the same `route_type` in the same week. The
  route is excluded from its own peer average.

Worked example (Delhi-Jaipur, week of 2024-11-11): cost per tonne-km `4.17`; own 8-week average `3.08`
gives **+35.5%**; the other Short route (Mumbai-Pune) averaged `3.45` that week gives **+21.0%**. These
reproduce the sample file's numbers, and so do the other two sample rows.

### 2. Detector (`detect.py`)

A week is judged only once the route has a full 8-week baseline (a thinner baseline is too noisy to call
anything unusual). Each signal is a **robust z-score against the route's own past**: the median and MAD of
that route's *prior* weeks only, so there is no look-ahead. Medians and MADs are used so that past
anomalies do not inflate the spread and hide the next one.

| signal | triggers when |
|---|---|
| own history | cost is rising and z >= 3.0 |
| similar routes | cost is rising and the *gap to peers* is z >= 3.0 above that route's usual gap |
| market-wide | at least 4 routes (and at least half) are each z >= 1.5 in the same week, which is how a fuel move shows up |

The market-wide rule exists because one route at +6% is inside the noise, but four routes at +6% in the
same week is not. Floors on the spread (2.5 pp own, 3.0 pp peer) stop an unusually quiet history from
producing a huge z-score.

### 3. Note understanding (`notes.py`)

Each note becomes structured, checkable facts:

| field | how it is derived |
|---|---|
| scope | `applies_to`: a named route, or "All Routes" |
| effect | cue lists, checked in this order: *no effect* ("not significantly affected", "returned to normal", "absorbed ... without a rate change", "not part of this dataset") then *decrease* then *increase*. Unrecognised text defaults to **no effect**. |
| window | explicit range ("from Feb 24 to Mar 8"), else "starting this week" (open-ended), else the note's own Monday-Sunday week |
| magnitude | a "5-7%" style range, only for increases |

Defaulting to "no effect" means a misread note can only cause a *missed* justification, never a false one.

### 4. Retrieval (`retrieval.py`)

For each reviewed week the notes are searched in three layers:

1. **Metadata filter**: only notes scoped to that route or to "All Routes".
2. **Hybrid ranking**: embedding similarity (`all-MiniLM-L6-v2`, local, open-source) + a bonus for naming
   the exact route + a bonus for being close in time. Pure embeddings ranked a generic "costs rose" fuel note
   above the route-specific flood note, which is why the extra signals exist.
3. **Exact vector search** (FAISS flat index, numpy if FAISS is absent) with ties broken by note id.

`retrieval_trace.csv` records the ranking for every week. Verdicts never depend on the scores.

### 5. Evidence gate (`verdict.py`)

A note justifies a week only if **all five** conditions hold:

| # | condition | example of what it stops |
|---|---|---|
| 1 | **Scope**: names this route, or "All Routes" | a flood note for Delhi-Jaipur cannot explain Chennai-Bangalore |
| 2 | **Effect**: says costs went *up* | N005 ("costs were not significantly affected") and N009 ("returned to normal") |
| 3 | **Window**: the week overlaps the note's dates; a persistent step only counts while the 8-week baseline still straddles it | Chennai-Bangalore on 10 Mar, after N001's window ended on 8 Mar |
| 4 | **Size**: if the note quantifies the effect, the rise cannot exceed it by more than normal noise | Mumbai-Delhi +11.6% against N003's 5-7% |
| 5 | **Relative**: a cause that hits all routes equally cannot explain a gap versus similar routes | the Mumbai-Pune creep versus the fuel note |

If several notes qualify, a route-specific note is preferred over an all-routes note. Anything that fails is
`Yes` (flagged) with a blank `matched_note_id`.

### 6. Explanations (`explain.py`) and Q&A (`qa.py`)

Reasons are **templates** filled with computed numbers and the note's own text, so they cannot introduce a
cause that is not in the notes. A rejected note is only mentioned if it is within 4 weeks of the week,
otherwise the reason says "No matching note found". `python -m costwatch ask "..."` answers from the run's
own result files and says so when there is nothing to explain, instead of improvising.

## Results

| route | weeks | verdict | why |
|---|---|---|---|
| Delhi-Jaipur | 11 and 18 Nov 2024 | flagged | +35% and +28%; no note anywhere near |
| Ahmedabad-Mumbai | 20 Jan 2025 | justified N002 | festival-week surcharge on this corridor |
| Chennai-Bangalore | 24 Feb, 3 Mar 2025 | justified N001 | flood disruption 24 Feb to 8 Mar |
| Chennai-Bangalore | 10 and 17 Mar 2025 | **flagged** | still +22% and +14%, but N001 ended 8 Mar and N009 says normal |
| Delhi-Chennai, Delhi-Jaipur, Mumbai-Delhi, Mumbai-Pune | 5 May 2025 | justified N003 | nationwide diesel rise of roughly 5-7% |
| Mumbai-Delhi | 12 May 2025 | **flagged** | +11.6% is about twice what N003 can account for |
| Mumbai-Pune | 10 weeks, Sep-Dec 2025 | flagged | slow creep, +23% to +39% vs similar routes; N006 and N010 are decoys |

The two **bold** rows are the interesting ones: the rise is real and a note exists, but the note does not
fit the dates or the size, so the system refuses to credit it.

## Example output rows

**Justified** (Ahmedabad-Mumbai, 2025-01-20, `matched_note_id = N002`)

> Matches note N002 dated 2025-01-20: "A regional festival week saw a temporary surcharge applied by
> transporters on the Ahmedabad-Mumbai corridor due to high demand and limited truck availability." The week
> of 2025-01-20 falls inside the note's window (2025-01-20 to 2025-01-26). The cost rise (+29.5% vs this
> route's past average and +22.5% vs similar-length routes) has a clear explanation.

**Right route, wrong dates** (Chennai-Bangalore, 2025-03-10, flagged)

> No genuine justification found. Closest note: N009 (2025-03-17): "Highway authorities confirmed the
> Chennai-Bangalore route returned to normal conditions after flood-related repairs were completed." That note
> describes no cost impact. Another nearby note, N001 (2025-02-24), covered 2025-02-24 to 2025-03-08, which
> ended before this week. Neither explains this week's cost rise (+22.1% vs this route's past average and
> +33.8% vs similar-length routes). Flagged for human review.

**Rise bigger than the note supports** (Mumbai-Delhi, 2025-05-12, flagged)

> No genuine justification found. Closest note: N003 (2025-05-05): "Diesel prices rose nationwide starting
> this week, pushing up transportation costs across all routes by roughly 5-7%." That note accounts for at
> most about 6% of a rise, but this week is +11.6% above the route's past average. ...

**Nothing relevant** (Delhi-Jaipur, 2024-11-11, flagged)

> No matching note found for this route or date range. Cost rise (+35.5% vs this route's past average and
> +21.0% vs similar-length routes) looks unexplained and worth a human review.

## How I know it is right

| check | what it shows | where |
|---|---|---|
| Sample rows reproduce | my baseline definitions match the grader's: 4.17 / +35.5% / +21.0%, 3.29 / +29.5% / +22.5%, 3.98 / +9.2% / +23.6% | `tests/test_pipeline.py` |
| Unit tests | week boundaries; ratio of sums; baseline excludes the current week and is never padded; peers exclude the route itself | `tests/test_metrics.py`, `tests/test_notes.py` |
| Adversarial gate tests (14) | wrong route, wrong window, "not affected" note, "back to normal" note, note that starts later, note far away, expired step, rise larger than the note, all-routes cause vs peers, no notes, route-specific preferred | `tests/test_verdict.py` |
| Labeled set (22 weeks) | flagged / justified / normal cases, including weeks that coincide with decoy-note dates | `eval/labeled_cases.csv` |
| Independent citation audit | every justified row re-checked against a hand-written truth table that does not use the parser | `eval/note_truth.py` |
| Quiet-period check | no review rows before 28 Oct 2024 | `eval_report.md` |
| Threshold sweep | nine threshold pairs; the chosen one gives zero quiet-period false alarms and 2.5 would add one | `eval_report.md` |

Honest caveat: I wrote the labels from the notes and a read of the data, so the labeled set is a
**regression set, not independent ground truth**. The citation audit is the stronger check, because its
truth table does not share code with the system.

## Reproducibility

`scripts/repro_check.py` runs the full pipeline three times in fresh processes, each with a different
`PYTHONHASHSEED`, and compares the SHA-256 of every output file. All six files match
(see `outputs/repro_report.md`).

Nothing in the system is random: no sampling, no LLM, exact vector search, ties broken by note id, and no
timestamps in the outputs. There is no temperature to set because there is no model generating text.

## Cost and responsible LLM use

One full run over the shipment file: **0 LLM calls, 0 input tokens, 0 output tokens, $0.** Retrieval uses a
small open-source embedding model on CPU (32 short texts). `outputs/cost_log.md` is generated by the run itself.

This is a deliberate trade-off. With ten short notes, structured extraction plus templates is cheaper,
perfectly repeatable and cannot fabricate; an LLM would only polish wording. If one were added, the cost log
projects roughly 22 explanations at about 300 input and 80 output tokens each, and the verdict, cited note
and numbers would still be computed before any wording step.

## Design decisions and trade-offs

| decision | alternative | why |
|---|---|---|
| Robust z-score vs the route's own past | flat % threshold | weekly noise is about 3% and peer gaps are structural |
| Median / MAD | mean / standard deviation | past anomalies would inflate the spread and mask the next one |
| Market-wide rule | judge every route alone | a 6% fuel step is invisible on one route but obvious across four |
| Deterministic gate on structured facts | an LLM judges "is this note relevant?" | a wrong confident reason scores worse than "no reason found"; the gate is testable and repeatable |
| Hybrid retrieval | embeddings only | pure similarity ranked a generic fuel note above the route-specific flood note |
| Templated explanations quoting the note | free-form generation | cannot introduce a cause that is not in the notes |
| Unknown note wording defaults to "no effect" | best-effort guess | failure mode is a missed justification, never a false one |
| Persistent steps expire after 8 weeks | open-ended justification | once the baseline absorbs the step, it is no longer a rise |
| `output.csv` holds weeks needing a verdict | all 728 rows | matches the sample file; the full grid is in `weekly_metrics_full.csv` |

## Assumptions and limitations

- **Output scope.** `output.csv` lists weeks that needed a verdict, as the sample does. The first 8 weeks of
  each route are never flagged (`No (insufficient history)` in the full file).
- **Sensitivity limit.** A +5% step on a single route is inside the noise. On 5 May 2025, Ahmedabad-Mumbai,
  Chennai-Bangalore and Kolkata-Bhubaneswar rose only +1% to +5% and are not listed.
- **Policy call.** Mumbai-Delhi on 12 May 2025 (+11.6%) is flagged although diesel partly explains it, because
  the note supports about 6%. A "partially explained" verdict is the natural extension.
- **Rule-based note reader.** Reliable on these 10 notes; new phrasing may need new cues. An LLM extractor with
  schema validation is the natural upgrade, and it would still pass through the same gate.
- **Two-route groups.** Short and Long each have two routes, so "similar routes" is a single other route.
  Normalising by the route's own usual gap keeps it usable but noisier.
- **Direction.** `Mumbai-Delhi` and `Delhi-Mumbai` would be different routes.
- **Calibration.** Thresholds were tuned on this one two-year dataset; production would need
  re-calibration and a larger, independently labelled set.

## Configuration

Every tunable number lives in `costwatch/config.py` (retrieval weights in `costwatch/retrieval.py`).

| setting | value | meaning |
|---|---|---|
| `BASELINE_WEEKS` | 8 | trailing weeks for "vs own history" (fixed by the brief) |
| `MIN_PRIOR_WEEKS_TO_FLAG` | 8 | full baseline required before a week can be judged |
| `Z_STRONG` | 3.0 | z needed for a single route-week on its own |
| `Z_MARKET` | 1.5 | lower z used only when several routes rise together |
| `MARKET_MIN_ROUTES` / `MARKET_MIN_SHARE` | 4 / 0.5 | breadth needed for the market-wide rule |
| `OWN_SPREAD_FLOOR` / `PEER_SPREAD_FLOOR` | 2.5 / 3.0 pp | minimum spread used in a z-score |
| `MIN_OBS_FOR_SPREAD` | 8 | prior observations needed before a z-score exists |
| `RETRIEVAL_TOP_K` | 5 | notes passed to the gate per week |
| `NEAR_NOTE_DAYS` | 28 | a rejected note is only cited if this close in time |

## Repository layout and extending it

```
costwatch/
  config.py      all thresholds
  metrics.py     weekly cost per tonne-km, own-history and peer baselines
  detect.py      robust z-scores, market-wide check, candidate flags
  notes.py       free text -> scope, effect, window, magnitude
  retrieval.py   metadata filter + hybrid ranking over notes
  verdict.py     the five-condition evidence gate
  explain.py     templated, grounded explanations
  qa.py          plain-English questions answered from results
  pipeline.py    orchestration and output contract
  cli.py         `run` and `ask`
tests/           metrics, notes, verdict (adversarial), end-to-end
eval/            labeled cases, independent truth table, evaluator
scripts/         repro_check.py
outputs/         generated deliverables and evidence
```

**Adding a note:** append a row to `context_notes.csv` and rerun. If its wording is new, add the cue to
`NO_EFFECT_CUES`, `DECREASE_CUES` or `INCREASE_CUES` in `notes.py`, add a case to `tests/test_notes.py`, and
add its truth entry to `eval/note_truth.py` so the audit covers it.
