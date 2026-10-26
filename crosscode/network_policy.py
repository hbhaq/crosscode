"""Explicit, versioned evaluator-only egress authorization."""
EGRESS_POLICY = {
    'version': 'wikibooks-connect-sni-v1',
    'hosts': ['en.wikibooks.org'],
    'ports': [443],
    'task_ids': ['BigCodeBench/590'],
    'transport': 'read-only named-volume Unix socket; evaluator network=none',
    'user_agent': 'CrosscodeBenchmark/0.1 (BigCodeBench reproducibility pilot)',
    'proxy_limits': {'connections':16,'bytes_per_connection':16777216,'connection_seconds':60},
}
