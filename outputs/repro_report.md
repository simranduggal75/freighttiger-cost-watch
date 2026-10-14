# Reproducibility check

3 untouched runs, each a fresh process with a different PYTHONHASHSEED.

| file | run 1 | run 2 | run 3 | identical |
|---|---|---|---|---|
| output.csv | 4276a877cb35 | 4276a877cb35 | 4276a877cb35 | yes |
| weekly_metrics_full.csv | d74ce67ba19b | d74ce67ba19b | d74ce67ba19b | yes |
| note_facts.csv | dd2606165651 | dd2606165651 | dd2606165651 | yes |
| retrieval_trace.csv | a945ed33a4f4 | a945ed33a4f4 | a945ed33a4f4 | yes |
| run_log.json | c6df983b48c6 | c6df983b48c6 | c6df983b48c6 | yes |
| cost_log.md | 93bde4375a77 | 93bde4375a77 | 93bde4375a77 | yes |

**Result: IDENTICAL - flags, numbers, cited notes and wording match byte for byte.**
