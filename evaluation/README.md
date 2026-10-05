# Click issue retrieval benchmark

This is a small, manually curated **development** set, not a held-out benchmark. It is suitable for checking that retrieval changes are measurable and for inspecting failure cases; do not present its scores as broad code-search performance.

- Repository: [pallets/click](https://github.com/pallets/click)
- Evaluated revision: `fd183b2ced1cb5857784fe7fb22f4982f671f098` (tag `8.2.1`), before each listed fix was merged.
- Query text: short paraphrases of the issue descriptions, written without referring to the fix implementation.
- Labels: source files changed by the linked fixing PRs. Tests, documentation, and changelog files are excluded. Multi-file labels are retained where both source files changed.

| Issue | Fix PR | Labeled source files |
| --- | --- | --- |
| [#3019](https://github.com/pallets/click/issues/3019) | [#3021](https://github.com/pallets/click/pull/3021) | `src/click/termui.py` |
| [#2952](https://github.com/pallets/click/issues/2952) | [#2956](https://github.com/pallets/click/pull/2956) | `src/click/core.py`, `src/click/types.py` |
| [#2836](https://github.com/pallets/click/issues/2836) | [#3328](https://github.com/pallets/click/pull/3328) | `src/click/core.py`, `src/click/termui.py` |
| [#3015](https://github.com/pallets/click/issues/3015) | [#3471](https://github.com/pallets/click/pull/3471) | `src/click/types.py` |
| [#3043](https://github.com/pallets/click/issues/3043) | [#3126](https://github.com/pallets/click/pull/3126) | `src/click/shell_completion.py` |

Clone and check out the pinned revision, then run:

```bash
git clone --branch 8.2.1 --depth 1 https://github.com/pallets/click.git /tmp/repopilot-click-8.2.1
python -m repopilot.evaluation /tmp/repopilot-click-8.2.1 evaluation/click_8_2_1_issues.jsonl --top-k 3
```

The evaluator reports file-level Recall@K and MRR@K. The data are public but tiny and manually selected, so these values are descriptive of these five cases only. Since this repository evolves, always verify the checkout SHA before comparing results.

## Measured local models

[The live model report](LOCAL_MODEL_REPORT.md) includes all five retrieval methods, the local Agent run, failure analysis, and exact model revisions. Raw ranking output is in `results/click_retrieval_local.json`. The cross-encoder reranks **20 chunks** from the hybrid retriever; file-level deduplication occurs after ranking. The candidate cap can exclude relevant files, so reranking is not guaranteed to increase Recall@K.

For a live investigation run (requires the local server plus `.[dev]`):

```bash
python scripts/evaluate_local_agent.py /tmp/repopilot-click-8.2.1 \
  evaluation/click_8_2_1_issues.jsonl --output /tmp/click-agent-local.json
```

This exercises indexing and investigation through FastAPI's in-process HTTP client and the real LangGraph workflow, with actual localhost requests to Qwen. It records latency and tool traces without claiming automated root-cause grading. The 5 cases also informed prompt/runtime fixes; they are not a held-out evaluation.

## V2 paired investigation evaluation

The [V2 report](V2_REPORT.md) expands investigation evaluation to **10 development cases across Click and Requests**. Every case in `investigation_cases.jsonl` includes a pinned pre-fix revision, public issue/PR provenance, source-file labels, and a source-review rubric. Labels and rubrics are never included in model requests. Some queries were paraphrased after reading the fixing PR; this dataset is explicitly not held out.

Prepare snapshots without running their code:

```bash
python scripts/prepare_benchmark.py /tmp/repopilot-benchmark
```

Start the local model as documented, then run (the workbench uses port 18081):

```bash
python scripts/evaluate_investigations.py evaluation/investigation_cases.jsonl \
  /tmp/repopilot-benchmark/checkouts.json --model-url http://127.0.0.1:18081/v1 \
  --output /tmp/repopilot-investigations.json
python -m repopilot.benchmark evaluation/results/v2_baseline.json \
  evaluation/results/v2_final.json --output /tmp/repopilot-comparison.json
```

`--private-output /outside/repository/directory` optionally saves full source traces for local review. Public run artifacts omit upstream source excerpts. The runner rejects a dirty/wrong Git checkout and missing labels. The comparison rejects different datasets, model/settings, case sets, duplicate IDs, or revisions; failed cases stay in the denominator.

The baseline was run before V2 code changes at commit `43bf904`. Intermediate failed runs remain in `results/v2_candidate.json` and `results/v2_draft_conditioned.json`. A `source_digest` identifies the Python source snapshot at run start, including uncommitted changes; `source_commit` alone is not the implementation identity for development runs.

## Follow-up: actual source-read coverage

The [follow-up report](V2_1_REPORT.md) compares source files retrieved, actually read, and finally cited. Reproduce the read-stage metric with:

```bash
python scripts/compare_read_coverage.py evaluation/investigation_cases.jsonl \
  evaluation/results/v2_final.json evaluation/results/v2_1_read_boundary.json
```

Only successful `read_file` ranges with complete returned lines count. The dataset labels are read after the investigation and never sent to the model.

## Symbol navigation follow-up

The [symbol navigation report](V2_2_REPORT.md) records AST-based assignment/import lookup, ten-case file coverage, and remaining causal errors. This is a development-set result; file recall is not diagnosis accuracy.
