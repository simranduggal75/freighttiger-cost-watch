# Cost log (one full run over shipment_records.csv)

Measured by the run itself; regenerated on every `python -m costwatch run`.

| item | value |
|---|---|
| LLM calls | 0 |
| LLM input tokens | 0 |
| LLM output tokens | 0 |
| LLM cost at published rates | $0.00 |
| Retrieval backend | `embeddings:sentence-transformers/all-MiniLM-L6-v2` |
| Texts embedded locally (10 notes + 22 candidate queries) | 32 |
| Embedding tokens (approx., local CPU model) | 867 |
| Embedding cost | $0.00 (open-source model, runs locally) |

## Why zero LLM calls
Every verdict and every sentence is produced by deterministic code from structured note
facts, so an LLM would add cost and non-determinism without changing a single verdict.
Retrieval uses a small open-source embedding model on CPU.

## If an LLM were added to polish wording (projection, not measured)
About 22 short explanations x (~300 input + ~80 output tokens) = roughly
6,600 input / 1,760 output tokens per run, with temperature 0.
The verdict, cited note and numbers would stay fixed because they are computed before any wording step.
