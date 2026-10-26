# Verification record

Development used Windows PowerShell and Python 3.12. No inference credentials were read during development and no paid inference calls were made. Both requested API contracts were checked against official documentation; provider requests were tested with transport fixtures, not real model calls.

## Executed

- Initially, 21 offline tests passed and the Docker integration test was skipped. On 2026-10-24, the full suite passed with Docker enabled: **22 tests, no failures or skips** (`Ran 22 tests in 66.639s`).
- Stable full-pool prefix sampling and explicit five-to-ten manifest expansion, plus stage reuse when actually expanding execution from 50 to 100 independent-design stages.
- Ten versus six calls per task, prerequisite writers for selected reviewed arms, independently keyed drafts and intentional shared-draft input/hash reuse.
- Prompt allowlists exclude tests, canonical solutions, unpermitted task fields and writer confidence/reasoning outside the parsed program.
- Atomic concurrent reservations, cumulative resume accounting, no duplicate purchases on cached resume, conservative unknown usage, explicit 429 retry limits, terminal truncation and budget-unstarted versus incorrect outcomes.
- Exact provider IDs, medium effort, 16,384 defaults, adaptive thinking, empty tools, stop/incomplete flags, text-block extraction and token pricing. Cached reads and both write lifetimes are tested without double-counting input or reasoning tokens.
- Configuration/cache changes, selected-task evaluation fixtures, exact McNemar known values, BH adjustment, per-repetition test families, seeded cluster intervals, known same-draft fixes/regressions, parse/infrastructure denominator separation and table/figure coordinate equality.
- Both mock five-task end-to-end execution and report-only regeneration completed. Demo ledger has zero actual spending. Figure PNG visually inspected after label collision fixes; SVG/PDF and CSV/Markdown/LaTeX outputs generated.
- Real pinned parquet data loaded and SHA256 checked: 1,140 full, 148 hard, 992 custom non-hard. A real hard-five dry run selected BigCodeBench/969, /108, /526, /915 and /917, planned 50 calls and made zero inference calls. Example five/ten manifests share the same five-task prefix.
- Python byte-compilation, CLI help and wheel build succeeded. The local dependency lock records the resolved Python 3.12 environment.

## Docker verification follow-up (2026-10-24)

Docker Engine 29.8.2 became available after the user started it. The full official dependency-image download was stopped because its large layers included approximately 2.1 GB and 6.4 GB downloads. Its Dockerfile remains available; the full official-base image build is still unverified.

Built `docker/Integration.Dockerfile`, a smaller selected-task environment with the same pinned official evaluator code. A transient Docker Hub DNS error resolved on retry. The initial build exposed an unavailable `e2b==1.0.7` pin, corrected to the published `1.0.6` release. The first real fixture test exposed root-owned `/work`; fixed by setting UID/GID 65534 and mode 0700 on that tmpfs, preserving the sandbox restrictions. Preflight/evaluation identities now include the runtime command, and canonical assembly explicitly separates prompt/body with a newline.

The official evaluator accepted a known correct program and rejected a known incorrect program inside Docker. The selected hard-five canonical solutions all passed: BigCodeBench/969, /108, /526, /915 and /917. The run ledger contains zero purchased calls and $0 spending. This is infrastructure verification, not model-performance evidence. See `docs/verification/docker-2026-10-24.json`, `docker/integration.image.lock.json`, and `docker/integration.requirements.lock` for provenance. The mandatory per-selection preflight remains enabled; there is no bypass.

## Still unverified

Actual account model availability, vendor latency, billable usage, thinking-token sufficiency and model performance remain unmeasured. GET-model access checks occur before a user-initiated paid run; no model substitution exists. Full-dataset dependency coverage and the larger official-base Docker build are not verified by the selected-task image. Native WSL2 host installation was not separately exercised. Tiny synthetic confidence intervals only demonstrate the pipeline; they are not experimental findings.

## Task-audit follow-up

Added readable audit pages for every selected task, condition/repetition and saved stage/attempt. Three focused audit tests passed, covering exact UTF-8 response bytes and CRLF preservation, shared-draft links, all selected tasks, unresolved/unstarted work, genuine transitions and verified-versus-provisional annotations. The existing report/figure consistency test also passed with the audit integrated. Generated the synthetic demonstration and the prepared real-task requirements audit without inference, and checked all synthetic audit Markdown links resolve. This follow-up did not repeat the full Docker suite or purchase model analysis.

## Progress-only follow-up (2026-10-26)

Added flushed, thread-safe terminal/file status events and elapsed-time heartbeats around existing operations, with default 15-second waiting messages. No prompts, provider parameters, generation/evaluation cache identities, source locks, frozen configuration fields, retry policy or spending rules changed. The existing running experiment was not interrupted/restarted, and no live inference or Docker evaluation was launched by this update.

The suite ran 33 tests in 95.575 seconds: 32 passed and the optional real-Docker test was not enabled (the previous Docker integration verification above remains applicable). Eight focused progress tests cover stopping heartbeats without retries, cache reuse and ledger preservation, safe error metadata with attempt IDs, preflight/evaluation cache reuse, runtime-only CLI flags, concurrent log integrity, quiet logging, and resilience to closed/unwritable output destinations. A separate offline one-task end-to-end run showed all ten mock stages, evaluation events and report heartbeats, with zero API spending.

A read-only compatibility check against the existing real run verified all 100 saved generation-stage identities still match. The frozen configuration identity remained `942092a703e188b1e50d71a658cb7aa9973e907dae246c137451515a72349997`; config.json SHA256 remained `acfa902eaf00b5b04a7d05d01f9b4905297af95163df27630106faf147360173`, and manifest.json SHA256 remained `82acb9fffa9471d21e88650dd62c834ebfeb91d8a4fd1a2fdff3cbe208404b6e`. Checkpoints were read in SQLite read-only mode; they were not edited or reset.

## Hard-50 evaluator repair and authorized egress (2026-10-26)

The original pilot dependency image passed 37/50 canonical solutions after expansion. Thirteen failures were missing libraries, including imports used only by official tests. The expanded image adds 43 packages while preserving every existing pilot package version, and passes 49/50 offline. Task 590 additionally requires live Wikibooks HTTPS access. The user explicitly authorized restricted access to that domain.

The final evaluator retains network=none and receives a read-only private Unix socket only for task 590. A separate credential-free trusted proxy restricts CONNECT authority, TLS SNI and public destination IPs to en.wikibooks.org:443. A descriptive default urllib User-Agent is recorded as a transport adaptation because the site's response to the default Python agent was HTTP 403. Official tests, selected task order and reference/generated programs were not rewritten. All **50/50 canonical solutions passed**, completing at 01:09:18 Asia/Karachi. Exact image IDs, source hashes, policy and outcomes are saved in `docker/wikibooks.image.lock.json` and `docs/verification/docker-wikibooks-2026-10-26.json`.

Real-container security checks passed for approved HTTPS, denied other/private destinations, denied direct evaluator internet access, absent provider keys and read-only socket volume. Correct/incorrect fixture Docker integration passed separately. The final automated suite ran 51 tests in 91.583 seconds: 50 passed, one optional Docker test skipped (the separately enabled Docker check passed). Eight policy tests cover authority/IP/SNI restrictions, network isolation, configuration identity and cleanup. Nine continuation tests cover exact output/attempt/ledger preservation, cache reuse, fresh evaluation, incompatible-input rejection, unresolved reservations, matching preflight and CLI behavior. A transient Windows rename denial was handled with bounded retries of only the final filesystem rename. No inference retry behavior changed. Python compilation, CLI help and a rebuilt wheel succeeded.

Created `docker-hard-fifty-fixed` as an explicit evaluator continuation. It inherits 100 saved stages/attempts and $1.776121 cumulative spending with zero unresolved reservations. Read-only checks verified both runs' cache bindings and exact outputs, prompts, usage and attempts. Original configuration identity remains unchanged; the source's expanded 50-task manifest SHA256 is `5238aa00952ee6fd6487192f947a8d1011f5419f33e9af91de44c1a6bf4d12f7`. The new configuration is `195cc38f16c75479932b7b7a4e9445b920c88864b898547e1fcbcb06dc19919f`. Original 98 evaluation records were not reused in the continuation: saved programs require fresh evaluation in the upgraded environment. Dry run confirms 100 cached / 400 remaining of 500 planned stages, valid completed preflight and preserved $40/$4 controls. Migration and verification made zero provider inference calls. Do not sum overlapping source/continuation spending. Dependency coverage beyond these 50 tasks and future live-site availability remain unverified.
