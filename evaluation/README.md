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
