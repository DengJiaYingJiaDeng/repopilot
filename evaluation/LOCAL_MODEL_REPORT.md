# Local model run — 2026-10-04

This report separates retrieval ranking, protocol completion, and the correctness of a generated hypothesis. The benchmark has five manually selected Click issues at commit `fd183b2ced1cb5857784fe7fb22f4982f671f098`. The same cases informed integration and prompt fixes, so none of the following is a held-out result.

## Retrieval with real weights

| Method | File Recall@3 | File MRR@3 |
| --- | ---: | ---: |
| Keyword | 0.40 | 0.367 |
| BM25 | 0.90 | 0.80 |
| MiniLM cosine | 0.80 | 0.50 |
| BM25 + MiniLM RRF | 0.80 | 0.767 |
| Hybrid + MiniLM cross-encoder | 0.80 | 0.90 |

The embedding was `sentence-transformers/all-MiniLM-L6-v2` (384 dimensions). The reranker was `cross-encoder/ms-marco-MiniLM-L6-v2`, operating on 20 hybrid-ranked **chunks**. Both ran on CPU, with PyTorch 2.6.0+cpu and SentenceTransformers 5.1.2. [Exact revisions and runtime settings](results/local_models_manifest.json) and [per-case rankings](results/click_retrieval_local.json) are recorded.

BM25 retained the highest recall. Reranking moved a relevant source file to the first position on four cases, but still missed second labeled files for #2952 and #2836. On #3015 it ranked an example above the relevant source. This illustrates different objectives: MRR rewards the first relevant hit; Recall rewards recovering all labeled files. Dense embeddings and more stages did not automatically improve both.

To reproduce, use the [local setup guide](../docs/LOCAL_MODELS.md), then enable the local embedding provider and reranker:

```bash
REPOPILOT_EMBEDDING_PROVIDER=local \
REPOPILOT_RERANK_MODEL=cross-encoder/ms-marco-MiniLM-L6-v2 \
python -m repopilot.evaluation /tmp/repopilot-click-8.2.1 \
  evaluation/click_8_2_1_issues.jsonl --top-k 3 \
  --methods keyword bm25 vector hybrid rerank
```

## Real local Agent execution

Qwen3-4B Q4_K_M ran on the local llama.cpp Vulkan server, with a 16,384-token context, thinking disabled, temperature 0, and a 1,536-token response limit. The app used BM25 context, FastAPI, and the real LangGraph workflow. The first turn was explicitly required to read a source file; subsequent tool choices were automatic. No remote inference service or API key was involved.

| Issue | Protocol status | Tool calls | Observed seconds |
| --- | --- | ---: | ---: |
| #3019 | complete | 2 | 7.370 |
| #2952 | complete | 2 | 7.415 |
| #2836 | complete | 3 | 7.394 |
| #3015 | complete | 2 | 5.195 |
| #3043 | complete | 2 | 4.336 |

All five returned schema-valid hypotheses citing files present in observed context. Median latency was **7.370 seconds**. These are sequential observations with a loaded model, not a concurrency, cold-start, or statistically stable latency benchmark. [Outputs, tool names, arguments, and limitations](results/click_agent_local.json) are committed; upstream source excerpts are omitted from this artifact. The application itself returns the full tool trace to the local caller.

Reproduce with `scripts/evaluate_local_agent.py` as described in the benchmark README. Results may differ across runtime builds, hardware, and model versions.

## Manual source audit: completion is not correctness

The following is a qualitative review against the pinned source, not an independent or blinded accuracy score:

| Issue | Assessment of this run |
| --- | --- |
| #3019 | Correct file, weak explanation. The model largely restated the empty-suffix symptom; it did not identify the unconditional space passed to the input functions after stripping trailing spaces. |
| #2952 | Incorrect direction. It blamed `show_default`, while the relevant runtime path is environment-value resolution and conversion. The retrieved default-display tests distracted the model. |
| #2836 | Partially useful. It identified the boolean-only forwarding of `show_default` in `Option.prompt_for_value`; its explanation confused the missing custom string with the default value being absent entirely. |
| #3015 | Incorrect emphasis on case sensitivity. The inspected code stringifies enum members with `map(str, self.choices)`, which can disagree with the representation accepted by the choice normalization/conversion path. |
| #3043 | Consistent with the inspected formatting path: raw multi-line `item.help` is interpolated into Fish completion output. A reproducer and regression test are still required. |

File citation validation proves only that the path appeared in observed evidence. It does not prove causal support. `complete` means the protocol finished; it is not a model-quality grade. RepoPilot does not run the target repository's tests or implement patches.

## Failures found and fixes made

- Initially the model returned plausible final JSON without any tool calls. The adapter now requires a first source read and an explicit first-turn instruction.
- This llama.cpp build accepted string `tool_choice` values but ignored the object form for a named tool. The adapter offers only `read_file` on the required first turn, then restores all three tools.
- An 8K-context trial completed only 2/5 cases: one exceeded context and two hit the output-token cap while repeating a final response. The [initial failure record](results/local_agent_8k_failures.json) is retained. Increasing the context to 16K and clarifying the first-turn instruction resolved those protocol failures in the recorded run. This does not establish that they cannot recur.
- Long files were previously capped at their first 8,000 characters. The read tool now accepts source line ranges, with explicit truncation flags, so later implementation code can be inspected.
- Local HTTP failures and malformed output now return an incomplete investigation with a review flag. Each investigation receives a new model session, preventing cross-request history reuse.

## Claims supported by this experiment

Supported: a functioning local model/tool loop; a reproducible five-method retrieval comparison; error traces and a qualitative failure audit. Not supported: a general 90% diagnosis accuracy, reliable autonomous repair, generalization to unseen repositories, or production readiness. A separate larger held-out dataset and regression-test validation would be needed before making stronger claims.
