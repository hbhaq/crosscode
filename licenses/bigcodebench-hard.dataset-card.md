---
dataset_info:
  features:
  - name: task_id
    dtype: string
  - name: complete_prompt
    dtype: string
  - name: instruct_prompt
    dtype: string
  - name: canonical_solution
    dtype: string
  - name: code_prompt
    dtype: string
  - name: test
    dtype: string
  - name: entry_point
    dtype: string
  - name: doc_struct
    dtype: string
  - name: libs
    dtype: string
  - name: q_idx
    dtype: int64
  - name: question
    dtype: string
  - name: score
    dtype: float64
  - name: _id
    dtype: string
  splits:
  - name: v0.1.0_hf
    num_bytes: 1271624
    num_examples: 148
  - name: v0.1.1
    num_bytes: 1271607
    num_examples: 148
  - name: v0.1.2
    num_bytes: 1271812
    num_examples: 148
  - name: v0.1.3
    num_bytes: 1271812
    num_examples: 148
  - name: v0.1.4
    num_bytes: 1272012
    num_examples: 148
  download_size: 2758366
  dataset_size: 6358867
configs:
- config_name: default
  data_files:
  - split: v0.1.0_hf
    path: data/v0.1.0_hf-*
  - split: v0.1.1
    path: data/v0.1.1-*
  - split: v0.1.2
    path: data/v0.1.2-*
  - split: v0.1.3
    path: data/v0.1.3-*
  - split: v0.1.4
    path: data/v0.1.4-*
---
