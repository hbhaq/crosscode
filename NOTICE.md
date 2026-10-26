# Attribution

Crosscode is an original implementation adapting the design and prompts of Zuodong Xiang, Yike Zhang, YueMing Zhang and Hailu Xu, *Cross-Model LLM Code Review: Should you use Claude to review Codex or vice versa?* (2026), [paper](https://arxiv.org/abs/2607.21656), [released code](https://github.com/shawnzxiang/cross-model-review-code). Study code/prompts are MIT licensed; the complete notice and original prompt templates are preserved under `licenses`.

BigCodeBench is by the BigCodeBench authors: [repository](https://github.com/bigcode-project/bigcodebench), [full dataset](https://huggingface.co/datasets/bigcode/bigcodebench), [hard subset](https://huggingface.co/datasets/bigcode/bigcodebench-hard). Repository and full dataset identify Apache-2.0. The inspected hard card does not declare a separate license field; its records are a subset of the Apache-2.0 full corpus. We preserve both dataset cards and do not assert an independently specified hard-card license. Official evaluator code is used in the pinned container, not copied into the Python package; the full upstream license is preserved. Its HumanEval-derived modules retain upstream MIT notices in the source/container.

Source versions and dataset checksums are recorded in `sources.lock.json`. Synthetic fixtures are original Crosscode examples and contain no paper result numbers.
