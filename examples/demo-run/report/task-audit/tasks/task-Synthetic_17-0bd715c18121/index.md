# Synthetic/17

[Audit index](../../index.md).

Design: paper-independent. Configuration: `0b3d2db146022ac420d76679f7f8cc721a258ae7f73410353986655b4538d4c5`. [Dataset/settings provenance](../../metadata.json).

Task hash: `581e90a25c435cab590eea3d0ab220afa404a307e832f15efa424b4dde412c4d`. Required entry point: `task_func`. Libraries: math.

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
| 0 | A | PASS — supplied evaluator tests passed | PASS — supplied evaluator tests passed | Solo baseline; no reviewer | [Open](repetition-0-A.md) |
| 0 | O | FAIL — supplied evaluator tests failed (synthetic_fail) | FAIL — supplied evaluator tests failed (synthetic_fail) | Solo baseline; no reviewer | [Open](repetition-0-O.md) |
| 0 | AO | PASS — supplied evaluator tests passed | PASS — supplied evaluator tests passed | Kept passing outcome | [Open](repetition-0-AO.md) |
| 0 | OA | FAIL — supplied evaluator tests failed (synthetic_fail) | PASS — supplied evaluator tests passed | Genuine reviewer fix | [Open](repetition-0-OA.md) |
| 0 | AA | PASS — supplied evaluator tests passed | PASS — supplied evaluator tests passed | Kept passing outcome | [Open](repetition-0-AA.md) |
| 0 | OO | FAIL — supplied evaluator tests failed (synthetic_fail) | PASS — supplied evaluator tests passed | Genuine reviewer fix | [Open](repetition-0-OO.md) |
