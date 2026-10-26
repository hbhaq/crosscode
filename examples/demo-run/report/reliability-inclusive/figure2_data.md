Provenance: `{"analysis_population": "reliability-inclusive", "configuration_hash": "0b3d2db146022ac420d76679f7f8cc721a258ae7f73410353986655b4538d4c5", "dataset_revision": "\"synthetic-v1\"", "design_mode": "paper-independent", "output_token_caps": "16384 / 16384", "phase": "main", "reasoning_efforts": "medium / medium", "requested_models": "claude-opus-5-5;gpt-6.1-sol", "returned_models": "SYNTHETIC-A;SYNTHETIC-O", "selected_task_count": 5, "subset": "full"}`

| condition | passed | evaluated | denominator | pass_rate | ci_low | ci_high | sid_pp | mean_workflow_cost_usd | mean_workflow_latency_s | cross_condition_regression_rate | cross_condition_denominator |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| A | 3 | 5 | 5 | 0.6 | 0.2 | 1 | NA | 0.00128 | 0.1 | NA | 0 |
| O | 4 | 5 | 5 | 0.8 | 0.4 | 1 | NA | 0.00064 | 0.1 | NA | 0 |
| AO | 5 | 5 | 5 | 1 | 1 | 1 | 40 | 0.00192 | 0.2 | 0 | 5 |
| OA | 3 | 5 | 5 | 0.6 | 0.2 | 1 | -20 | 0.00192 | 0.2 | 0.4 | 5 |
| AA | 5 | 5 | 5 | 1 | 1 | 1 | 40 | 0.00256 | 0.2 | 0 | 5 |
| OO | 5 | 5 | 5 | 1 | 1 | 1 | 20 | 0.00128 | 0.2 | 0 | 5 |
