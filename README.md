# Crosscode

A Python experiment tool comparing Claude Opus 5.5 and GPT-6.1 Sol as writers and reviewers on pinned BigCodeBench tasks. This is a pilot tool, with a mandatory Docker canonical-solution preflight before paid generation.

No paid inference was performed during development. The checked-in demonstration is synthetic and uses synthetic task IDs, outcomes, token counts and latencies. It is not evidence about either model.

## Setup

Use Python 3.12. On Linux, or Ubuntu under Windows WSL2 with Docker Desktop Linux integration enabled:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.lock
python -m pip install --no-deps -e .
python scripts/fetch_data.py
python -m unittest discover -s tests -v
```

On native Windows PowerShell, use `py -3.12 -m venv .venv`, then `.venv\Scripts\Activate.ps1` and the same Python commands. Docker must use Linux containers. WSL2 is the supported evaluator host; generated programs never run in Windows Python or host Python. Native Windows CLI/offline tests were exercised during development.

The data fetcher downloads only the pinned public v0.1.4 parquet files. It does not make inference calls. `sources.lock.json` records both dataset revisions and file SHA256 values. Actual verified counts: full 1,140; hard 148; non-hard 992 (our set difference, not an official difficulty category).

## Offline demonstration

```bash
crosscode --mock --tasks 5 --run-id offline-five --max-cost-usd 5
crosscode report --resume offline-five
```

Open `runs/offline-five/report/report.md`. Both analysis populations have Tables 2–5 (CSV, Markdown, LaTeX), Figure 2 (PNG, SVG, PDF), underlying data, all pairwise tests, stage/task JSON and inspection bundles. A saved example is in `examples/demo-run`. Regenerate it without inference:

```bash
crosscode report --runs-dir examples --resume demo-run
```

For exact requirements and responses, open `report/task-audit/index.md` within any run. Every selected task links all its condition/repetition outcomes, saved raw final response text, provider JSON, rendered prompts, parsed/evaluated code, review diffs and evaluator evidence. Shared drafts link to the same saved writer stage. Unstarted work and missing responses remain explicit; causal explanations require verified human annotations and are otherwise pending inspection. This audit is generated entirely from saved data, without model calls.

## First five real tasks: dry run

This command needs no keys, no running Docker and no inference:

```bash
crosscode --config configs/personal.json --subset hard --tasks 5 --seed 42 --run-id first-five-preview --dry-run --max-cost-usd 5 --max-task-cost-usd 2
```

It plans 50 calls with all conditions and the default independent design. `shared-draft` plans 30 calls for five tasks. Conservative reviewer allowances assume the maximum permitted input band; these deliberately overstate typical costs and are not expected-cost predictions. Execution uses the actual prompt byte bound before each call. A $5 limit can stop a run early; unstarted work is not counted as incorrect.

## Prepare the isolated evaluator

Start Docker Desktop/the Linux daemon. The smaller image verified for the seed-42 hard-five pilot can be built with:

```powershell
docker build -f docker/Integration.Dockerfile -t crosscode-evaluator-integration .
docker image inspect crosscode-evaluator-integration --format '{{.Id}}'
```

Its fixture integration test and all five pilot canonical solutions passed. It does not supply every full-dataset library. For the larger official dependency environment (a substantially larger download, not yet build-verified here), use:

```bash
docker build -f docker/Dockerfile -t crosscode-evaluator .
docker image inspect crosscode-evaluator --format '{{.Id}}'
```

The base official BigCodeBench evaluator image is pinned by registry digest. The evaluator code is overlaid at its recorded commit. Copy the returned `sha256:...` ID of your chosen image into the commands below. No API key enters the image. The runtime has no network, host bind mounts, writable root filesystem or capabilities; it has bounded CPU, memory, process count and wall time. See [evaluation](docs/EVALUATION.md) for image provenance and integration evidence.

The later 50-task expansion outgrew the smaller dependency image. `docker/Expanded.Dockerfile` adds the missing packages; `docker/Networked.Dockerfile` and `docker/EgressProxy.Dockerfile` implement the user-authorized Wikibooks HTTPS transport required by task BigCodeBench/590. The evaluator retains network isolation and receives only a restricted private proxy socket for that task; see [evaluation](docs/EVALUATION.md). An explicit `fork-evaluator` continuation preserves compatible saved generations and cumulative spending across this evaluator upgrade. Do not edit frozen settings in place or bypass canonical preflight.

## First five-task live run

Set `OPENAI_API_KEY` and `ANTHROPIC_API_KEY` in your shell. `.env.example` is a template; Crosscode intentionally does not load arbitrary environment files. Do not commit credentials.

After replacing `sha256:YOUR_IMAGE_ID` with the actual image ID:

```bash
crosscode --config configs/personal.json --subset hard --tasks 5 --seed 42 --run-id first-five --evaluator-image sha256:YOUR_IMAGE_ID --dry-run --max-cost-usd 5 --max-task-cost-usd 2
crosscode preflight --resume first-five
crosscode --resume first-five --max-cost-usd 5 --max-task-cost-usd 2
```

The last command purchases inference only after canonical preflight succeeds and read-only provider model lookups confirm access. An unavailable requested model blocks execution; there is no substitution. The command itself is your explicit choice to start paid inference. Local budget guards are not provider-enforced billing limits.

PowerShell can capture the image ID with `$evalImage = docker image inspect crosscode-evaluator --format '{{.Id}}'` and pass `--evaluator-image $evalImage`.

## Expand, resume, evaluate and report

```bash
# Append the next five tasks from the originally frozen eligible ordering.
crosscode expand --resume first-five --tasks 10
crosscode --resume first-five --max-cost-usd 10 --max-task-cost-usd 2

# Ordinary resume never changes task selection or resets spending.
crosscode --resume first-five --max-cost-usd 10
crosscode --resume first-five --evaluate-only
crosscode --resume first-five --report-only
crosscode report --resume first-five --annotations configs/annotations.example.json

# A separately funded company run; the same package scales without code edits.
crosscode --config configs/company.json --subset hard --tasks all --run-id company-hard --evaluator-image sha256:YOUR_IMAGE_ID --dry-run
crosscode --resume company-hard --max-cost-usd 500 --max-task-cost-usd 5
```

Credentials can change between runs through environment variables. Keep company work in a new run with `--profile company`; a personal run's profile is frozen. Spending limits can change explicitly on resume, but the ledger remains cumulative. A source/prompt/model/effort/cap/design change requires a separate run identity.

Live console progress is enabled by default for generation, Docker preflight/evaluation and report generation. It shows task/condition/role/model, attempt IDs, cache reuse, saved-stage counts, spending/reservations and errors, with a waiting heartbeat every 15 seconds. These messages are also appended to the run's `progress.log`. `--progress-interval 10` changes the heartbeat interval; `--quiet-progress` hides console messages while retaining the log. Both are presentation-only settings and do not change configuration hashes, retries, cache identities or provider requests. Existing running processes are not restarted or modified; progress appears on the next invocation. Dry-run JSON output remains unchanged.

## Selection and experiment options

Run `crosscode --help` for all flags. `--subset full|hard|non-hard`, `--tasks N|all`, `--seed INTEGER`, `--task-ids BigCodeBench/1,BigCodeBench/2` or `--task-file PATH`, `--split instruct|complete` (default instruct), and `--list-tasks` are supported. Include/exclude libraries use exact case-sensitive names from `libs`: inclusion requires every named library; exclusion rejects any named match. IDs conflicting with filters, duplicate/unknown IDs, empty pools and oversized counts fail before inference. Selection sorts then shuffles the entire eligible pool once, then takes a prefix. The seed affects task selection only.

Conditions: `all`, `baselines`, `cross-review`, or explicit IDs. A=Claude solo, O=GPT solo, AO=Claude→GPT, OA=GPT→Claude, AA and OO=self review. Reviewed conditions always include prerequisite writer calls even if the solo condition is omitted. Exactly one review is used, and its final output is mandatory: no test-based choice between writer and reviewer. Both draft and final are scored after generation. No evaluator result feeds the prompt builder.

`--phase calibration` creates a separately labeled pilot identity. Use disjoint explicit task IDs for calibration and main runs; [calibration](docs/OPERATIONS.md) describes overlap auditing. No paid calibration was performed. Both roles use the same per-model effort/cap. Initial defaults are medium and 16,384 output tokens, including the providers' reasoning/thinking allowance; these require calibration, not claims of equal compute. API and evaluation timeouts are separate. Personal defaults have zero retries. Sampling controls and provider seeds are omitted.

See [methodology and replication differences](docs/METHODOLOGY.md), [operations and accounting](docs/OPERATIONS.md), [verification](docs/VERIFICATION.md), and [attribution](NOTICE.md).
