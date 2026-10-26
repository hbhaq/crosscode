# Methodology and replication differences

## Inspected sources

Inspected on 2026-10-24: [paper v1](https://arxiv.org/pdf/2607.21656), study repository commit `5573234ecd682dc864fdf775bbe808722d60126c`, BigCodeBench commit `09dd993f46c3fbf3a799465bb96d524edcb0b199`. Immutable dataset revisions, checksums, licenses and URLs are in `sources.lock.json`. The pinned BigCodeBench full/hard v0.1.4 releases contain 1,140/148 rows; non-hard has 992.

The source audit covered study `docs/SCOPE.md`, `docs/RESULTS.md`, `docs/REPRODUCIBILITY.md`, `experiments/run_experiment.py`, `harness/core/pipeline.py`, both `harness/prompts` templates, `experiments/configs`, and analysis scripts (`compute_metrics`, `statistical_tests`, `review_transitions`, `evaluate_writer_artifacts`, `plots`, `result_index`). BigCodeBench inspection covered `data/bigcodebench.py`, `data/utils.py`, `evaluate.py`, `sanitize.py`, `eval`, generation prompt handling, and `Docker/Evaluate.Dockerfile`.

## What is preserved

Six writer/reviewer pipelines, one static review pass, fresh contexts, no execution/tools in generation, solution tags, mandatory final replacement and same selected tasks in every condition. The reviewer receives only allowed problem/interface fields and the actual parsed writer program. Confidence text outside the solution is stored but never handed to a reviewer. Canonical solutions and evaluator tests exist only in local manifests and isolated evaluation inputs.

Independent sampling was verified in executable code: `run_experiment.py` creates a job for each task-condition and constructs its pipeline; `_run_task_once` in `pipeline.py` calls `self.writer.run` for that condition before optionally calling the reviewer. Solo artifacts are not inputs to other arms. Therefore paper-independent is the default: six writers plus four reviewers = ten generation calls/task/repetition. Cache identity includes condition, even when prompts coincide. Shared-draft deliberately creates two writers and four reviewers = six calls, reusing each frozen writer in its solo arm and two reviews; this adaptation remains a separate configuration and report.

## Changes for models and dataset

Claude Opus 5.5 and GPT-6.1 Sol replace Opus 4.7/GPT-5.5. BigCodeBench library-dependent Python functions replace LiveCodeBench competitive programming. Writer/reviewer prompts minimally change the domain wording and preserve `task_func` signatures. Exact original templates and the study MIT license are retained in `licenses`; adapted templates are in `crosscode/prompts` and rendered texts/hashes are saved per stage.

Both providers use medium effort instead of the study's high effort. Output ceilings are initially 16,384 tokens; calibration is necessary to assess truncation. Equal effort labels or ceilings do not imply equal capability, compute, visible-code budget or price. No provider seed, temperature or top_p is forced. We do not claim exact replication of CLI environments or repository-scale review. Dataset contamination and model alias changes remain limitations.

## Changes for API access and budgets

Direct REST Responses and Messages requests replace Claude Code/Codex CLI. No vendor SDK is used, so SDK compatibility/hidden retries are avoided; API request fields are tested at the transport boundary. Requested and returned model IDs, timestamps, stop/incomplete fields, token usage, raw final responses and parsed hashes are retained. No private reasoning trace is required. Tools are empty and every call has one independent user message.

The official [OpenAI model page](https://developers.openai.com/api/docs/models/gpt-6.1-sol) confirms `gpt-6.1-sol`, medium effort and the Responses interface. Standard global per-million token rates recorded on 2026-10-24: input $2, cached input $0.10, output $10. Reasoning counts within output, not as an additional charge. The [cache guide](https://developers.openai.com/api/docs/guides/prompt-caching) specifies disjoint cached/read/write subsets: 30-minute writes cost $2.50 and 12-hour writes $5 per million, replacing rather than adding to the ordinary-input rate for those tokens. Provider-default implicit caching is retained and all reported write fields are accounted for. Prompts beyond the conservatively supported input band are rejected before calling.

The official [Opus changes page](https://platform.claude.com/docs/en/models/opus-5-5/whats-new-opus-5-5) confirms `claude-opus-5-5`, `output_config.effort=medium`, adaptive thinking always enabled, and base input/output prices $4/$20 per million. Explicit `thinking.type=adaptive` is supported; manual/disabled thinking is not sent. Cache read/write snapshot: $0.20/$5 per million (5-minute write), $8 for one-hour writes. Crosscode does not set explicit cache controls; reported usage is still accounted for. Usage output includes billable thinking; hidden thought text is never used in reviews. [Thinking reference](https://platform.claude.com/docs/en/build-with-claude/thinking).

No stable dated model snapshot for either requested identifier was established from the inspected pages; requested aliases are preserved and returned IDs/timestamps recorded, without invented snapshots. Account-specific availability is checked without inference immediately before paid work. Models are configurable for offline planning; live nondefault IDs are blocked until their pricing/parameters are reviewed, rather than borrowing another model's price.

Spending is guarded before each call using atomic reservations and conservative input-byte bounds plus the full output cap. Timeout usage remains unresolved and reserved until explicit billing reconciliation. Cost limits persist across resumes. This differs from the study's generous post-writer budget check. No test-driven retries or draft selection are used.

## Paper versus released code

1. Paper section 4.1 uses same-draft wording and section 4.3 describes condition-level discordances as fixes/regressions. Released `SCOPE.md` explicitly says these are independently sampled pipelines. Crosscode labels those contrasts as pipeline comparisons and scores each actual reviewer input separately for genuine transitions.
2. The paper says 3,000 seconds per CLI turn; released `all_conditions.yaml` contains 30,000. The runner defaults to four task attempts, with an additional doubled-timeout turn inside each attempt; CLI rate-limit retry behavior adds another difference. Crosscode's personal profile uses 300 seconds, zero retries; `paper-like-timeouts.json` records the released 30,000 seconds/high effort/four maximum attempts but is only an adaptation: Crosscode retries known-unbilled 429 errors, not whole failed pipelines or unknown-charge timeouts. No claim of exact retry replication is made.
3. The repository reliability `pass_rate` column retains an evaluated-only denominator, while its reliability success metric is passed/all-attempted. Crosscode exports explicit evaluated and reliability denominators and excludes budget-unstarted/infrastructure failures from reliability scoring.

## Figure 2 and Tables 2–5 audit

The actual paper's pages 4–7 (zero-based PDF pages 3–6) were inspected, including the two-panel Figure 2. No original numerical results enter Crosscode outputs.

| Artifact | Preserved structure/purpose | Explicit changes |
| --- | --- | --- |
| Table 2 | Six condition rows; pass, CI, SID, cost, latency, regression rate | Adds evaluated/selected/attempted/invalid/not-run and known-cost coverage. SID uses percentage points rather than the paper's displayed fractional delta. Independent regression is labeled cross-condition; same-draft transitions separate. |
| Table 3 | Writer rows labeled with solo rate; two reviewer columns with pass rate and delta | Claude/GPT names updated; numeric components additionally exported as table3_data. |
| Table 4 | Discordant counts, exact McNemar, BH | Exports all 15 comparisons, displays six requested rows (the paper additionally displays some contrasts). Corrects full family before selecting; repeated runs get one exact-test family/repetition. |
| Table 5 | Task, condition, draft, final, action, interpretation | True scored reviewer draft, deterministic two examples/transition/condition, local annotation evidence, pending inspection by default. Never explains cause from pass/fail. |
| Figure 2 | Cost/accuracy and latency/accuracy panels; circles/diamonds; writer-colored arrows | Coordinates share Table 2 data exactly. Standalone workflow costs; writer+reviewer latency. Separate figures for each design/population. Missing observations omit unsupported points/arrows. |

## Statistical populations

Evaluator environments are separate configurations. The 2026-10-26 hard-50 continuation adds missing dependencies and a user-authorized Wikibooks-only HTTPS transport for BigCodeBench/590, including a descriptive default urllib User-Agent. Other tasks remain offline. Official tests, task selection and reference/generated programs are unchanged. Original compatible generations and their spending are inherited with provenance, while evaluation results are recomputed in the new environment. Reports disclose this lineage; do not pool original and continuation results or add their overlapping spending. Live website changes remain a reproducibility limitation. Exact images/policy and verification evidence are recorded in the evaluator documentation and image locks.

Complete-case: task-repetition observations with valid evaluated outcomes in every requested condition. Reliability-inclusive: terminal attempted workflows, invalid generation counted as failure, but budget-unstarted finals and evaluator infrastructure failures excluded. Each population is separately identified; neither is silently pooled with another design. For reliability SID with unequal coverage, marginal SID is descriptive; paired delta/CI and paired-regression denominator are also exported.

Seeded task-cluster percentile bootstrap (2,000 resamples, seed 42) retains all available repetitions per sampled task, for pass rate, workflow cost/latency, and paired differences/regression rate. Fewer than two task clusters gives undefined intervals; tiny samples can yield degenerate intervals. For each repetition, exact two-sided McNemar uses task pairs and BH across all requested condition pairs within that population/repetition. No exact test pools task-repetition rows. Empty comparisons are NA, zero discordance with observations gives p=1. No significance claim or general winner is warranted by a five-/ten-task proof of concept.
