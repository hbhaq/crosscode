# Isolated official evaluation

The evaluator is invoked only by `docker run`. There is no Python exec/import/subprocess fallback for generated solutions on the host. Docker integration was verified on 2026-10-24 using the selected-task image described below: a correct fixture passed, an incorrect fixture failed, and all five selected hard-task canonical solutions passed. This does not establish full-dataset dependency coverage.

## Verified five-task pilot image

`docker/Integration.Dockerfile` uses pinned Python and BigCodeBench sources with the libraries needed by the seed-42 hard-five pilot. The image is available locally as `crosscode-evaluator-integration`; its immutable ID and build provenance are saved in `docker/integration.image.lock.json`. Installed dependencies are inventoried in `docker/integration.requirements.lock`; its local BigCodeBench reference corresponds to the separately pinned source checkout, not a public package release. This image deliberately omits model-generation packages such as vLLM, which Crosscode does not use inside evaluation. SciPy 1.10.1 is a selected-environment adaptation rather than the old upstream requirements-file pin; NumPy 1.24.3 follows the upstream Docker environment override. Different image IDs remain separate configurations.

```powershell
docker build -f docker/Integration.Dockerfile -t crosscode-evaluator-integration .
$env:CROSSCODE_TEST_IMAGE = docker image inspect crosscode-evaluator-integration --format '{{.Id}}'
python -m unittest discover -s tests -p test_docker_integration.py -v
```

Canonical preflight is saved under `runs/docker-hard-five-check/preflight.json`; a portable summary without solutions/tests is in `docs/verification/docker-2026-10-24.json`. No model inference was performed. For a larger/different task selection, preflight must pass again; do not assume this smaller image supplies every benchmark library.

## Full dependency image

### Expanded seed-42 hard-50 dependency image (2026-10-26)

`docker/Expanded.Dockerfile` extends the verified pilot image, constraining its existing package versions and adding the packages needed by the expanded selection, including imports in official tests. NLTK stopwords are installed at image build time; evaluation still has no network access. Exact installed versions are inventoried in `docker/expanded.freeze.txt`.

The original pilot image passed 37/50 canonical solutions; 13 failures reported missing modules (including test-only imports such as Faker and openpyxl). The expanded image passed **49/50** with networking disabled. BigCodeBench/590's unchanged official tests also require live HTTPS requests to `https://en.wikibooks.org/wiki/Main_Page`. The user explicitly authorized restricted access to this domain. No task was removed/replaced and official tests/reference programs remain unchanged.

### Authorized Wikibooks transport

`docker/Networked.Dockerfile` adds a loopback relay to the expanded image. The evaluator retains `--network none`, all isolation limits, and no host bind mounts or credentials. Only task 590 receives a private Unix socket through a read-only ephemeral Docker named volume. A separate trusted service, built from `docker/EgressProxy.Dockerfile`, has bridge networking and accepts only CONNECT to `en.wikibooks.org:443`, with matching TLS SNI and public resolved destination addresses. It has no TCP listening port, credentials or host files. TLS stays end-to-end. Other destinations/ports, private addresses and direct evaluator internet connections are denied. Limits are 16 connections, 16 MiB per connection and 60 seconds per connection, within the overall evaluation timeout. Owned containers and socket volumes are removed after evaluation, including setup failures/timeouts.

The relay installs a descriptive default urllib User-Agent (`CrosscodeBenchmark/0.1 (BigCodeBench reproducibility pilot)`), because the public site rejected Python's default agent with HTTP 403. This is an explicit evaluator transport adaptation, applied equally to canonical and generated programs for task 590. It does not rewrite programs or tests. Live website content/availability can change, so record evaluation dates and avoid assuming a future request is identical.

Enable this only through the explicit immutable `--evaluator-egress-proxy-image` setting. The proxy image, transport policy and evaluator image are included in configuration/preflight/evaluation identities. Empty proxy settings preserve existing offline run identities. All other tasks continue without the relay or socket. See `scripts/verify_egress_isolation.py` and its saved evidence under `docs/verification` for real-container checks of allowed/denied requests, absent API keys and read-only volume behavior.

Changing images requires an explicitly separate configuration. The `fork-evaluator` operation supports inheriting exact validated generation outputs and their original attempts/cumulative ledger into a new run, while discarding destination evaluation caches for rescoring. It does not overwrite the source run or make model calls. The expanded image alone is not sufficient to authorize a live 50-task run until the required-network policy is resolved and all canonical tasks pass.

`docker/Dockerfile` pins the official dependency image by OCI manifest digest and overlays BigCodeBench source at `09dd993f46c3fbf3a799465bb96d524edcb0b199`. This freezes the provided dependency environment without attempting to resolve the upstream's mutually old requirements again. The final locally built image ID is required in live configuration, saved into the configuration hash and preflight evidence. Build-time git/pip tooling is not used during evaluation. For an archival company run, publish that image to an internal registry, retain its digest and SBOM, and archive `pip freeze` from it.

The host passes a JSON payload through stdin containing precisely one selected task and one candidate. No host directory, Docker socket, credential file or API key is mounted or passed. The container runs as UID/GID 65534 with no network, read-only root, dropped capabilities, no-new-privileges, 128-PID limit, two CPUs, 4 GiB memory, 1 GiB tmpfs work/tmp directories and an outer per-container timeout. `/work` is explicitly owned by UID/GID 65534 with mode 0700 so the non-root evaluator can write its temporary samples/results. Runtime settings are included in preflight and evaluation cache identities. Image-supplied environment contains no user API keys. Generated code is never granted credentials. Isolated `/work` allows temporary executables needed by some library tasks; this is still inside the bounded container.

The wrapper sets `BIGCODEBENCH_OVERRIDE_PATH` before importing the official loader, giving it the exact pinned selected task. `completeness_check` checks required fields, not full-dataset row count. It invokes official `evaluate(... execution='local', selective_evaluate=task_id, parallel=1, pass_k='1', calibrated=True)`. Here `local` means **inside the isolated container**. This avoids full-dataset missing-task assertions and prevents runtime downloads from replacing the pinned tasks. The official hash derives from the override file.

Both prompt splits require a full program in Crosscode. Instruct gets `instruct_prompt` and the allowed `code_prompt`; complete gets `complete_prompt`. Samples use the official `solution` key, never `completion`, so the evaluator does not prepend a second complete prompt. Canonical preflight assembles `complete_prompt + canonical_solution`, as required by BigCodeBench's function-body canonical solutions.

The official `sanitize(code, entrypoint)` runs inside the container. The official evaluator's `calibrated=True` prepends `code_prompt + '\n    pass\n'` to the sanitized solution, preserving its documented calibration behavior. This supplies the interface shell, not a test-driven repair. Raw text, parsed program and hashes are retained in SQLite; evaluation evidence saves raw, sanitized and effective calibrated artifacts. No test or canonical content is used to rewrite a generated program.

Each selected canonical solution must pass before inference. Preflight cache identity includes image ID, every selected task, split and evaluation timeout; expansion invalidates the old preflight. Infrastructure failures do not become model failures. Program timeouts are official evaluator outcomes; outer container timeouts are infrastructure timeouts, conservatively unscored. Invalid parse/truncation/API responses are recorded separately. If canonical preflight fails (including because a task needs unavailable network/service access), fix the environment and use a new pinned configuration; do not silently replace tasks. Crosscode does not implement an override flag that bypasses preflight.

When Docker is running, build and pin the image, then run the optional integration smoke test with no API calls:

```bash
export CROSSCODE_TEST_IMAGE=$(docker image inspect crosscode-evaluator --format '{{.Id}}')
python -m unittest discover -s tests -p test_docker_integration.py -v
```

PowerShell: `$env:CROSSCODE_TEST_IMAGE = docker image inspect crosscode-evaluator --format '{{.Id}}'`. This exercises a synthetic unittest fixture in the official evaluator, not a fake host evaluator. A real selected-task canonical preflight remains necessary before a paid run.
