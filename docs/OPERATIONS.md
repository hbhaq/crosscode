# Operations, calibration and accounting

## Freeze and resume

Every run has immutable experimental settings in `config.json`, a task manifest, and SQLite transactional stages/attempts/evaluations. SHA256 identities cover task contents, locked dataset revision, provider/model/settings, prompt/template, design, condition, repetition, actual parent-draft digest and frozen experimental configuration. A template/source/settings change blocks incompatible resume. A different model, effort, cap or split uses a new run and report; budget/runtime parallelism are separately controlled.

The selected manifest is a snapshot of full task records, including evaluation-only tests/canonicals. Treat it as evaluation data, not generation context. Only prompt allowlisted fields enter vendors. `expand --resume ID --tasks 10` preserves the original five and appends the next frozen eligible IDs after verifying task hashes. It saves a prior-manifest hash in history. Ordinary resume rejects selection changes. Completed stages and their attempt/price provenance remain intact.

## Runtime progress

Each new CLI invocation prints flushed, timestamped, thread-safe progress lines to stderr and appends them to `progress.log` in the run directory. Phases include provider access checks, cached/uncached canonical preflight, each writer/reviewer API attempt, evaluation and report regeneration. Generation events identify task/condition/repetition/role/model and attempt ID, with saved/remaining stage counts and cumulative settled/reserved USD. Saved-stage counts include terminal errors and must not be interpreted as pass counts. Blocked review stages are explicitly skipped.

Long operations print a heartbeat every 15 seconds (`--progress-interval` can change this). Heartbeats report elapsed time, do not initiate retries, and do not poll providers or launch additional evaluations. `--quiet-progress` hides console events while retaining the log. Both flags are runtime presentation choices, excluded from frozen experimental configuration and cache identities; dry runs retain their existing JSON output and create no progress log. Messages exclude prompts, response bodies, headers and raw exception text. Errors expose only safe exception types/status codes and the attempt ID needed for billing reconciliation. Output/log I/O failures do not turn successful model calls into failures. A running older Python process is left alone; changes apply to subsequent invocations.

## Explicit evaluator-only continuation

An evaluator dependency upgrade is not a reason to repurchase compatible model outputs, but its different image requires a separate configuration and fresh evaluation. `fork-evaluator --resume SOURCE --new-run-id DESTINATION --evaluator-image IMMUTABLE_IMAGE` creates that continuation without inference. Destination must be new, in the same runs directory; source config/manifest and logical checkpoint data are preserved. SQLite may create transient read-only snapshot sidecars, but source records are not modified.

The operation snapshots the source SQLite database, validates every saved stage against the exact task, rendered prompt, model/settings, condition, repetition and actual parent draft, then creates a derived cache binding with explicit original provenance. Original responses, generation configuration hashes, attempts, prices, spending, reservations and budget controls are retained. Only the evaluator image and explicitly supplied evaluator proxy setting may change; destination evaluation records are cleared so saved programs must be rescored. `migration.json`, origin metadata and every report disclose the lineage. **Destination spending includes inherited purchases; never add source and continuation spending as if they were separate purchases.** Unresolved reservations are retained and still block generation.

For the user-authorized Wikibooks policy, also pass `--evaluator-egress-proxy-image IMMUTABLE_PROXY_IMAGE` when creating the continuation. This grants only task 590 the restricted transport described in EVALUATION.md; it does not grant general networking. Ordinary resume still rejects changes to frozen evaluator settings.

An optional `--verified-preflight PATH` can carry over a completed canonical preflight only when its key, immutable image, exact selected task contents/order, split, timeout/runtime and all passed outcomes match the destination. A failed or mismatched preflight is rejected. Without matching evidence, the ordinary mandatory canonical preflight runs before any paid work. This is not a preflight bypass. Source and destination reports remain separate configurations. After creating a continuation, use its new run ID for future resume/expand/report commands.

## Budget guard

SQLite `BEGIN IMMEDIATE` serializes reservations. Before dispatch, cumulative settled costs + reserved/unknown allowances + this proposed call must satisfy both total and per-task limits. The task limit covers all its conditions and repetitions. Parallelism distributes whole task pipelines across workers so stage dependencies remain ordered. Duplicate active/completed stage checks prevent duplicate purchases through concurrent workers. SDK retries are absent because REST uses Python's standard library without a retry layer.

The allowance bounds input text by UTF-8 bytes plus 4,096 framing tokens and charges the full output ceiling. Inputs with a conservative upper bound above 200,000 tokens are blocked, avoiding long-context price-band ambiguity. Reviewer dry-run allowances use that entire accepted input band; live reservations use actual saved-draft bytes. Input reservations use the largest documented input/read/write rate, including longer-lived writes, to cover all supported token classes. Pricing is a dated standard/global snapshot, not a promise of provider billing. No explicit cache policy, region premium, fast tier or provider tools are requested; OpenAI's provider-default implicit caching can still incur writes. OpenAI explicitly uses the standard tier. Both providers' output totals already include reasoning/thinking, which are not charged a second time. OpenAI cached/read/write tokens are disjoint subsets of total input; their write components are billed once at the respective 30-minute or 12-hour rate. Anthropic cache-read/creation fields are separate from uncached input, with five-minute and one-hour creation rates. Unsupported custom model prices block live work.

Known-unbilled 429 errors retry only within `--max-retries` (default zero). Other known request/auth/not-found 4xx errors are terminal and cost zero. Unknown transport/timeout/server errors retain the entire allowance, checkpoint a typed error without potentially secret-bearing exception text, and stop scheduling. Already in-flight calls finish and settle. No cap is raised or effort lowered. Parse failures and truncation are terminal and visible, not silently regenerated. Stop reasons/content-filter incompleteness remain distinct from output-cap truncation.

On process death after reservation, the reservation stays unresolved. Resume stops until billing is reconciled; no presumption that the lost response was free. After checking the vendor's billing records:

```bash
crosscode reconcile --resume first-five --attempt-id 7 --verified-cost-usd 0.12 --billing-evidence 'Vendor billing record reference and verification date'
```

This appends evidence and updates actual cost; it does not invent the missing response or automatically repurchase that failed stage. Terminal failed stages remain failed. A lost stage with no saved response may only retry if the original explicit retry allowance has room after reconciliation. Preserve the database; deleting it loses the accounting protection.

Limits can be explicitly increased with a resume command, never reset cumulative spending. Profile metadata is frozen; use a separate company run when changing funding source. Environment keys are never stored. Request bodies contain task text and settings only; HTTP headers are not logged.

## Three cost concepts

Actual API spending is the sum of settled purchased attempts once; unresolved charges remain separately reserved. Standalone workflow cost charges its writer plus reviewer (including retries). An intentional shared writer contributes to multiple hypothetical standalone workflows, but only one purchased attempt. Report bookkeeping assigns actual call spending once to the first requested condition using it, in canonical A/O/AO/OA/AA/OO order; attribution is explicitly independent of analysis population.

End-to-end workflow latency is the sum of writer and reviewer attempt latencies, not global experiment wall time or overlapping jobs. Stage latency, raw usage, responses, stop details and attempt IDs remain queryable in SQLite. A partial workflow cost is NA if unknown; table sums show known coverage and the whole-run unresolved reserve alongside them. Synthetic demo workflow prices are token-price illustrations; actual spending is zero.

## Calibration protocol

Run a separately named pilot with `--phase calibration` only when ready to authorize paid calls. Use disjoint task IDs for the main evaluation whenever possible. For example, choose pilot IDs via `--list-tasks` and write a different explicit main task file; do not vary main tasks based on model outcomes.

```bash
crosscode --phase calibration --task-file calibration-ids.txt --tasks all --run-id calibration-1 --evaluator-image sha256:YOUR_IMAGE_ID --dry-run --max-cost-usd 5
# Explicitly purchasing the calibration pilot:
crosscode --resume calibration-1 --max-cost-usd 5
```

Inspect `report/calibration_summary.json` for usage, truncation, parse validity, latency, stop reasons and evaluator infrastructure status; inspect preflight evidence. Store settings choices and rationale before the main run, focusing on token/integration needs rather than model success. Attach compatible evidence at main run creation with `--calibration-summary runs/calibration-1/report/calibration_summary.json`. The tool freezes it, validates prompts/model/effort/caps/design/split and provenance, records overlapping IDs (also on expansion), and qualifies expected cost as a sum of per-model/per-role pilot means, excluding unknown future retries. This is not a guaranteed prediction. A separate overlap audit is available through `python scripts/audit_overlap.py runs/calibration-1/manifest.json runs/main/manifest.json`; retain its JSON with the main report. Any overlap must be disclosed. Settings freeze at run creation; pilot settings that change create a different configuration identity. No paid calibration occurred during implementation, and expected-cost predictions are unavailable without representative pilot data. Conservative allowances are always distinguished from expectations.

## Report populations and annotations

`report` never imports generation transports or purchases analysis. Complete-case and reliability-inclusive reports live in separate folders. Selected/attempted/valid/not-run counts describe all requested task-repetition workflows; evaluated/pass/fail and intervals describe the named population. Infrastructure is unscored and reported separately. Budget-unstarted final stages are excluded from the reliability denominator. Generation-invalid terminal attempts count as reliability failures. Exact tests use the common paired set across all requested conditions within each repetition; all 15 pairs for six conditions are corrected before displaying six requested contrasts. Repeated-task aggregates use task clusters and remain descriptive.

`report/task-audit/index.md` provides a separate audit of every selected task and stage, including incomplete work. Requirements export only public problem/interface fields; canonical solutions and tests are not mixed into that requirements file. Each condition/repetition links its actual writer and final stage, exact response text, provider response JSON, prompt, parsed program, evaluation evidence and all recorded attempts. Raw text files preserve the saved text without newline conversion. Exported programs are never executed by the reporter. Same-draft transitions are descriptive pass/fail transitions, not automatic explanations of causes. Evaluator evidence may include test failure traces and remains evaluation-only data. Shared writers are exported once and linked by all their workflows.

Inspect both fixes and regressions selected by the documented deterministic rule. Bundle task, draft.py, final.py, unified diff, code hashes, and evaluator evidence before annotating. Add entries keyed `task_id:repetition:condition` to a local annotation JSON; `verified:true` means a human checked the action/interpretation against the bundle. Without this flag, descriptions remain provisional; no annotations say pending inspection. No automatic model explanation calls are made.
