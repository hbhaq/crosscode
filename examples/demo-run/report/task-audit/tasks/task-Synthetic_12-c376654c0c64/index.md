# Synthetic/12

[Audit index](../../index.md).

Design: paper-independent. Configuration: `0b3d2db146022ac420d76679f7f8cc721a258ae7f73410353986655b4538d4c5`. [Dataset/settings provenance](../../metadata.json).

Task hash: `6a33b2b002754b53b9c02b473337fec4e6a052ca878c07a8dca8e1996b880183`. Required entry point: `task_func`. Libraries: json.

## Official requirements used by this run

```text
Return x unchanged.
```

## Permitted starter/interface

```python
def task_func(x):
```

[Requirements JSON](requirements.json). Canonical solutions and hidden tests are not included in this requirements export; evaluator records may contain test-failure evidence.

| Repetition | Condition | Actual writer draft | Final | Review transition | Details |
| --- | --- | --- | --- | --- | --- |
| 0 | A | FAIL — supplied evaluator tests failed (synthetic_fail) | FAIL — supplied evaluator tests failed (synthetic_fail) | Solo baseline; no reviewer | [Open](repetition-0-A.md) |
| 0 | O | PASS — supplied evaluator tests passed | PASS — supplied evaluator tests passed | Solo baseline; no reviewer | [Open](repetition-0-O.md) |
| 0 | AO | FAIL — supplied evaluator tests failed (synthetic_fail) | PASS — supplied evaluator tests passed | Genuine reviewer fix | [Open](repetition-0-AO.md) |
| 0 | OA | PASS — supplied evaluator tests passed | FAIL — supplied evaluator tests failed (synthetic_fail) | Genuine reviewer regression | [Open](repetition-0-OA.md) |
| 0 | AA | FAIL — supplied evaluator tests failed (synthetic_fail) | PASS — supplied evaluator tests passed | Genuine reviewer fix | [Open](repetition-0-AA.md) |
| 0 | OO | PASS — supplied evaluator tests passed | PASS — supplied evaluator tests passed | Kept passing outcome | [Open](repetition-0-OO.md) |
