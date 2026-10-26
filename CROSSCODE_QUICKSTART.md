# Crosscode — quickstart and runtime reference

Updated for this workspace on 26 October 2026, including live console progress and the evaluator continuation.

Workspace: `C:\Users\hinab\Documents\ChatGPT\CrossCode`

All commands below use **Windows PowerShell** and the project's existing Python environment. You do not need to activate the environment when using the full Python command shown here.

## 1. Current readiness

- The package, dataset and Docker images are installed in this workspace.
- The current continuation is **`docker-hard-fifty-fixed`**, with 50 selected hard tasks.
- It preserves 100 saved generation stages and their cumulative spending from `docker-hard-five-check`.
- The original run is preserved. Use the continuation ID for future resume/report/expand commands.
- Both models use medium effort, 16,384 output tokens and the original independent six-condition design.
- Task 590 uses the explicitly authorized Wikibooks-only HTTPS proxy; other tasks remain offline.
- All 50 canonical solutions passed in this environment on 26 October 2026.
- Current inherited spend is $1.776121, with no unresolved reservations; the dry run confirms 100 cached / 400 remaining stages.
- Setup/verification/migration makes no paid inference calls. Inspect the dry run for the current ledger and preflight state.

Before paid execution, set both API keys in your terminal and start Docker Desktop's Linux engine.

## 2. Open the project and enter your API keys

Open PowerShell and run:

```powershell
Set-Location "C:\Users\hinab\Documents\ChatGPT\CrossCode"

$env:OPENAI_API_KEY = [System.Net.NetworkCredential]::new('', (Read-Host "OpenAI API key" -AsSecureString)).Password
$env:ANTHROPIC_API_KEY = [System.Net.NetworkCredential]::new('', (Read-Host "Anthropic API key" -AsSecureString)).Password
```

- `OPENAI_API_KEY` is for GPT-6.1 Sol.
- `ANTHROPIC_API_KEY` is for Claude Opus 5.5.
- These values apply to this PowerShell session. Enter them again in a new session.
- The prompts hide your keys and do not put the key values into command history.
- Crosscode reads environment variables. **It does not automatically load `.env` files.**
- Do not put keys in configuration JSON, source code, reports, or chat messages.

Check that variables are populated without printing the keys:

```powershell
"OpenAI key set: $([bool]$env:OPENAI_API_KEY)"
"Anthropic key set: $([bool]$env:ANTHROPIC_API_KEY)"
docker info --format '{{.ServerVersion}}'
```

If Docker reports access denied, use a terminal/account with access to Docker Desktop's engine. This is an operating-system permission issue, not an API-key issue.

## 3. Inspect the current 50-task run — no inference spending

```powershell
.\.venv\Scripts\python.exe -m crosscode --resume docker-hard-fifty-fixed --dry-run --max-cost-usd 40 --max-task-cost-usd 4
```

This prints task IDs, settings, planned calls, cached/remaining stages, pricing assumptions, the cumulative ledger, and preflight state. It makes zero inference calls and needs no API keys.

For 50 tasks across all six independent conditions, the plan is **500 generation stages** before retries. The 100 saved stages are reused; terminal errors stay recorded.

The dry run persists its run manifest/settings and supplied budget controls. If you intend to resume a newly created run, choose its evaluator image and experimental settings before creating it.

## 4. Start paid inference on the prepared run

**The next command purchases model inference. Run it only when ready.**

```powershell
.\.venv\Scripts\python.exe -m crosscode --resume docker-hard-fifty-fixed --max-cost-usd 40 --max-task-cost-usd 4
```

It checks evaluator preflight and provider model access before generation. Model substitution is not allowed.

The **$40 total / $4 per-task limit** is the current spending allowance, not a measured cost prediction. The run can stop before finishing. Local guards reserve conservative allowances and are not provider-enforced billing guarantees. Never assume that the full budget will be spent or that it guarantees completion.

## 5. Resume after a budget stop

Use the **same run ID**. Completed saved stages are reused; do not create a new run if your intention is to continue.

Resume with the current cumulative limits:

```powershell
.\.venv\Scripts\python.exe -m crosscode --resume docker-hard-fifty-fixed --max-cost-usd 40 --max-task-cost-usd 4
```

The total limit includes inherited spending; it is not an additional allowance. Per-task spending also remains cumulative across conditions and repetitions.

If a writer completed but its reviewer has not started, the saved writer can be reused. Terminal API/parse/truncation failures remain recorded; resume does not silently regenerate every unsuccessful output. Unknown spending after a timeout requires billing reconciliation before further generation.

Keep the entire run directory, especially `checkpoint.sqlite`, `config.json`, and `manifest.json`. Deleting checkpoints removes the protection against repurchasing work.

### Live PowerShell progress

Progress is enabled automatically on the next invocation of the updated code. Let an already-running older process finish normally; editing the code does not retrofit its console output or require you to restart it.

The console shows the current task, condition, repetition, writer/reviewer, model, attempt ID, cache reuse, saved/remaining generation stages, actual spending and reserved allowances. Docker preflight, evaluation outcomes and report generation have separate phase messages. During long operations it prints an elapsed-time waiting message every **15 seconds**. A waiting message is not a retry and makes no additional API call. Saved-stage counts include terminal errors; they are not pass counts. Some remaining stages may be blocked by an invalid parent draft and are explicitly skipped.

To change the waiting-message interval to ten seconds on your next resume:

```powershell
.\.venv\Scripts\python.exe -m crosscode --resume docker-hard-fifty-fixed --progress-interval 10
```

That command uses the run's persisted spending limits unless you explicitly provide different limits, and can start remaining paid inference. It does not change experimental settings or cache identities.

Console progress is also appended to `runs\docker-hard-fifty-fixed\progress.log`. It contains status/cost metadata, not API keys, prompts, model response text or raw exception messages. You can follow this log in a second PowerShell window:

```powershell
Get-Content -LiteralPath .\runs\docker-hard-fifty-fixed\progress.log -Tail 20 -Wait
```

To hide progress from the console while keeping the log file, add `--quiet-progress`. Progress goes to stderr, leaving the existing JSON summaries on stdout. Dry runs do not print or create progress logs. These two flags are presentation-only and may change between resumes without invalidating cached work. New log messages do not change retries, budgets, model requests or evaluator settings.

## 6. Find and regenerate results

The report entry point for the prepared run is:

```text
C:\Users\hinab\Documents\ChatGPT\CrossCode\runs\docker-hard-fifty-fixed\report\report.md
```

The report contains separate complete-case and reliability-inclusive populations. Each has Tables 2–5, Figure 2, underlying CSV data and metadata, plus inspection bundles where genuine fixes/regressions were observed.

### Task-by-task visibility

Open this page to inspect every selected task, including work that has not run:

```text
runs\docker-hard-fifty-fixed\report\task-audit\index.md
```

Each task page contains its exact official requirements/interface and a table for every requested condition/repetition. Each workflow links its writer and final-stage evidence. The audit exports:

- `response.txt`: the exact saved final text returned by the model, including solution tags/confidence text where present.
- `provider-response.json`: the full saved provider response structure, with returned model/version and usage where available.
- `prompt.txt`: the exact rendered prompt sent for that stage.
- `program.py`: the parsed program; `sanitized.py` and `evaluated.py` are saved when available from Docker evaluation.
- `evaluation.json`: evaluator outcomes, test-failure details/tracebacks where available, or infrastructure errors.
- `attempt-N.json`: every recorded attempt's status, cost/reservation and provenance; exact attempt responses are separate text files when available.
- Per-workflow diffs, genuine same-draft fixes/regressions, costs, latencies, and human inspection annotations.

Shared writers are exported once and linked explicitly by all workflows using them. A pass means the supplied evaluator tests passed; it is not proof that all possible requirements are satisfied. An unstarted stage has no invented output. Explanations of why code failed remain **pending inspection** unless a human verifies them; no causal explanation is inferred from pass/fail alone. Provider-private reasoning that was not returned is unavailable.

The normal report command generates/regenerates the audit without inference. Audit evidence is for your inspection and is never added to writer/reviewer prompts. A synthetic example is available at `examples\demo-run\report\task-audit\index.md`.

Regenerate reports without inference calls:

```powershell
.\.venv\Scripts\python.exe -m crosscode report --resume docker-hard-fifty-fixed
```

Evaluate saved valid programs without generating new ones:

```powershell
.\.venv\Scripts\python.exe -m crosscode --resume docker-hard-fifty-fixed --evaluate-only
```

Equivalent report-only form:

```powershell
.\.venv\Scripts\python.exe -m crosscode --resume docker-hard-fifty-fixed --report-only
```

Evaluation-only requires Docker. Report-only does not require model credentials or inference.

## 7. Expand the selection later

The current run already selects 50 tasks. To extend it to 60:

```powershell
.\.venv\Scripts\python.exe -m crosscode expand --resume docker-hard-fifty-fixed --tasks 60
.\.venv\Scripts\python.exe -m crosscode --resume docker-hard-fifty-fixed --dry-run
```

Expansion retains completed work and cumulative spending. Newly selected tasks must pass canonical preflight; dependency coverage beyond the current 50 is unverified. Inspect the plan and budget before starting paid inference. Do not replace tasks to avoid preflight failures.

## 8. Create a different experiment

Use a new run ID when changing models, effort, token caps, design, conditions, repetitions, split, profile, phase, or other frozen experimental settings. Changes to prompts or locked sources also invalidate incompatible resume.

The locally verified pilot image is `crosscode-evaluator-integration`. Capture its immutable ID:

```powershell
$evalImage = docker image inspect crosscode-evaluator-integration --format '{{.Id}}'
```

Create a new five-task plan:

```powershell
.\.venv\Scripts\python.exe -m crosscode --run-id my-five-task-run --subset hard --tasks 5 --seed 42 --design paper-independent --conditions all --evaluator-image $evalImage --dry-run --max-cost-usd 40 --max-task-cost-usd 4
```

Run canonical preflight separately; this executes reference solutions in Docker but makes no model inference calls:

```powershell
.\.venv\Scripts\python.exe -m crosscode preflight --resume my-five-task-run
```

**To start paid inference after preflight:**

```powershell
.\.venv\Scripts\python.exe -m crosscode --resume my-five-task-run --max-cost-usd 40 --max-task-cost-usd 4
```

An existing run ID continues that run; it does not create a fresh experiment. Run IDs may contain letters, digits, underscores and hyphens.

## 9. Experimental designs and conditions

| Condition | Writer | Reviewer |
| --- | --- | --- |
| A | Claude | None |
| O | GPT | None |
| AO | Claude | GPT |
| OA | GPT | Claude |
| AA | Claude | Claude |
| OO | GPT | GPT |

Condition shortcuts:

- `--conditions all`: A, O, AO, OA, AA, OO.
- `--conditions baselines`: A and O.
- `--conditions cross-review`: AO and OA, including their required writer calls.
- `--conditions A,O,AO`: an explicit selection.

| Design | Draft handling | Calls for five tasks, all conditions, one repetition |
| --- | --- | --- |
| `paper-independent` (default) | Separate writer draft for each condition | 50 |
| `shared-draft` | One draft per writer reused in solo and both review arms | 30 |

Shared-draft is a cheaper methodological adaptation. Keep its results separate. Changing to it requires a new run; do not change an independent run in place.

## 10. Runtime option reference

### Tasks and selection

| Option | Meaning / default |
| --- | --- |
| `--subset full` | Full pool: 1,140 pinned tasks |
| `--subset hard` | Hard pool: 148 pinned tasks |
| `--subset non-hard` | Custom full-minus-hard pool: 992 tasks; not an official easy/medium label |
| `--tasks 5` | Select five tasks from the pool; default count is five |
| `--tasks all` | Select every eligible task |
| `--seed 42` | Task-selection seed; default 42; not a model-generation seed |
| `--task-ids BigCodeBench/969,BigCodeBench/108` | Restrict the pool to explicit IDs |
| `--task-file PATH` | Restrict the pool using IDs separated by whitespace/newlines; conflicts with `--task-ids` |
| `--include-libs pandas,numpy` | Require all named libraries; exact, case-sensitive matching |
| `--exclude-libs tensorflow` | Exclude tasks matching any named library |
| `--split instruct` | Official prompt style; `instruct` is default; `complete` also supported |
| `--list-tasks` | List selected task IDs/libraries without inference |

Selection shuffles the whole eligible pool deterministically and takes a prefix. Five-to-ten expansion preserves the first five when revision, filters and seed agree. Unknown/conflicting IDs, empty selections and excessive counts are rejected before inference.

### Models and generation

| Option | Default / meaning |
| --- | --- |
| `--design` | `paper-independent` or `shared-draft` |
| `--conditions` | `all`, `baselines`, `cross-review`, or explicit IDs |
| `--gpt-model` | `gpt-6.1-sol` |
| `--claude-model` | `claude-opus-5-5` |
| `--gpt-effort` | `medium`; allowed: low, medium, high, xhigh, max |
| `--claude-effort` | `medium`; allowed: low, medium, high, max |
| `--gpt-max-output-tokens` | 16384 |
| `--claude-max-output-tokens` | 16384 |
| `--repeats` | 1; additional repetitions multiply planned calls |
| `--max-retries` | 0; explicit retries apply to known-unbilled 429 errors, not arbitrary failed outputs |
| `--api-timeout` | 300 seconds per API attempt |
| `--eval-timeout` | 300 seconds per container evaluation |
| `--phase` | `main` or separately labeled `calibration` |

Thinking/reasoning is included in billable output usage. Equal effort names/caps do not mean equal compute or capability. Caps are initial settings to calibrate, not proven optimal values. Tools and provider generation seeds are not used. Truncation is recorded and caps are not automatically raised.

Model IDs are configurable for planning, but live nondefault model IDs are blocked until their pricing/parameter support is reviewed. No silent substitution occurs.

### Budget, execution and storage

| Option | Default / meaning |
| --- | --- |
| `--max-cost-usd` | Cumulative whole-run limit; default 5 |
| `--max-task-cost-usd` | Cumulative per-task limit, covering all its conditions/repetitions; default 2 |
| `--parallelism` | 1; higher values allow multiple task pipelines concurrently |
| `--progress-interval` | 15 seconds between waiting messages; presentation-only, not a timeout or retry |
| `--quiet-progress` | Hide console progress while retaining `progress.log`; does not alter the experiment |
| `--run-id NAME` | Name a new run; automatic timestamp if omitted |
| `--resume NAME` | Continue a saved run |
| `--runs-dir PATH` | Change run storage location; use the same path on resume/report/expansion |
| `--evaluator-image` | Immutable Docker image ID/digest; required for live execution |
| `--new-run-id` | New destination name for `fork-evaluator`; never overwrites an existing run |
| `--verified-preflight` | Optional strictly matching successful preflight for an evaluator-only continuation |
| `--profile` | `personal` (default) or `company`; frozen metadata, not a credential store |
| `--config PATH` | JSON settings file; explicit command-line settings override its supplied values |
| `--dry-run` | No inference; display plan, ledger and checks |
| `--mock` | Offline synthetic responses/outcomes; never real model results |
| `--evaluate-only` | Evaluate saved valid programs; no generation |
| `--report-only` | Regenerate report; no generation |
| `--annotations PATH` | Local human inspection annotations for examples |
| `--calibration-summary PATH` | Attach compatible pilot evidence at new-run creation, qualifying expected-cost forecasts and recording task overlap |

Budget limits and parallelism can be changed on resume without resetting spending. Frozen experimental settings cannot. Reservations include in-flight/unknown charges, so the guard can stop while the displayed settled spend is still below the limit.

Configuration examples shipped with the project:

- `configs/personal.json`: medium effort, zero retries, sequential execution, $5/$2 default guards.
- `configs/company.json`: separate company metadata and larger execution/budget settings.
- `configs/paper-like-timeouts.json`: deliberately more expensive high-effort/timeout/retry adaptation; not the personal default.

When resuming, usually omit `--config` and change only the desired runtime controls; this avoids accidentally reapplying different budget values or conflicting frozen settings.

## 11. Offline demonstration — no provider credentials needed

```powershell
.\.venv\Scripts\python.exe -m crosscode --mock --tasks 5 --run-id offline-example --max-cost-usd 5
.\.venv\Scripts\python.exe -m crosscode report --resume offline-example
```

These outputs are explicitly synthetic. They do not demonstrate actual model accuracy or cost. A saved synthetic example is also provided in `examples\demo-run`.

## 12. Docker rebuild and tests

The current 50-task evaluator uses these additional layers (already built locally):

```powershell
docker build -f docker/Expanded.Dockerfile -t crosscode-evaluator-expanded .
docker build -f docker/Networked.Dockerfile -t crosscode-evaluator-wikibooks .
docker build -f docker/EgressProxy.Dockerfile -t crosscode-wikibooks-proxy .
```

The expanded layer requires the pilot image below. Immutable image IDs and source hashes are saved in `docker/wikibooks.image.lock.json`. Rebuilds can produce different IDs; use a new configuration/explicit continuation instead of modifying a frozen run. Restricted access is enabled only by its explicit proxy setting, never by the image tag alone.

Rebuild the smaller pilot image if it is missing:

```powershell
docker build -f docker/Integration.Dockerfile -t crosscode-evaluator-integration .
$env:CROSSCODE_TEST_IMAGE = docker image inspect crosscode-evaluator-integration --format '{{.Id}}'
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

The smaller image is verified for the original five hard tasks, not every benchmark library. The larger official dependency image can be built with:

```powershell
docker build -f docker/Dockerfile -t crosscode-evaluator .
```

That larger image involves substantial downloads and has not been build-verified here. Any different image ID requires a new experimental configuration/run. Every new selection must pass its own canonical preflight.

## 13. Common problems

| Message / situation | What to do |
| --- | --- |
| Missing `OPENAI_API_KEY` or `ANTHROPIC_API_KEY` | Set both variables in the same terminal that launches Crosscode |
| Docker engine unavailable / access denied | Start Docker Desktop's Linux engine and check terminal permissions |
| Evaluator image missing | Build the appropriate image; do not replace a frozen run's image setting in place |
| Requested model unavailable | Check account model access/billing; Crosscode will not substitute another model |
| Budget reservation would exceed a limit | Inspect the ledger; resume the same run with higher total/per-task limits if desired |
| Frozen setting differs / incompatible cache | Resume with original settings or create a new run for the changed experiment |
| Resume cannot change task selection | Use the explicit `expand` command, or create a new experiment |
| Canonical preflight failed | Inspect `runs\RUN_ID\preflight.json`; fix environment/library problems before inference |
| Truncated or invalid generated output | Inspect saved status/artifact; it is terminal under the declared policy and is not silently regenerated |
| Unknown usage after timeout/crash | Verify vendor billing and reconcile before more generation; a timeout may have incurred charges |

Billing reconciliation is an advanced operation. Only enter a cost you verified against vendor records:

```powershell
.\.venv\Scripts\python.exe -m crosscode reconcile --resume docker-hard-fifty-fixed --attempt-id 7 --verified-cost-usd 0.12 --billing-evidence "Verified vendor billing record reference and date"
```

The attempt ID and dollar value above are examples, not instructions to change a real ledger entry. Reconciliation records spending evidence; it does not recover a missing response or automatically regenerate a terminal failed stage.

### If a larger selection outgrows the evaluator image

The original five-task image lacked dependencies needed by the 50-task selection. The upgraded evaluator adds these packages and the user-approved restricted Wikibooks transport for task 590. The separate continuation preserves exact saved model responses, prompts, attempts, costs and reservations; saved programs receive fresh evaluations in the upgraded environment.

Use **`docker-hard-fifty-fixed`** from now on. Its spending includes purchases inherited from `docker-hard-five-check`; do not add their ledgers together. Do not edit either run's frozen configuration in place.

For another explicit evaluator upgrade, the general command is:

```powershell
# Template only: use real immutable image IDs and a new destination ID.
.\.venv\Scripts\python.exe -m crosscode fork-evaluator --resume SOURCE_RUN --new-run-id DESTINATION_RUN --evaluator-image sha256:ACTUAL_IMAGE_DIGEST
```

Add `--evaluator-egress-proxy-image sha256:ACTUAL_PROXY_DIGEST` only for the approved Wikibooks transport. This creates a continuation without inference; it never bypasses canonical preflight. See `docs/EVALUATION.md` for the precise policy.

## 14. Built-in help and further reading

```powershell
.\.venv\Scripts\python.exe -m crosscode --help
```

Additional files in the project:

- `README.md`: setup and command overview.
- `docs\METHODOLOGY.md`: source study, preserved design and replication differences.
- `docs\OPERATIONS.md`: accounting, calibration, resumption and annotations.
- `docs\EVALUATION.md`: Docker isolation and evaluator behavior.
- `docs\VERIFICATION.md`: what was actually tested and remaining limitations.

Five-/ten-task results are pilots / proofs of concept. They should not be presented as establishing a general model winner.
