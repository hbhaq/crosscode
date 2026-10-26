"""Direct REST transports; no SDK, hidden retry, tools, or retained conversation."""
import json
import os
import time
import urllib.error
import urllib.request
from .core import PACKAGE, ROOT, digest, read

PRICING = {
    'date': '2026-10-24', 'currency': 'USD', 'tier': 'standard global, prompts <=272K',
    'O': {'input': 2.0, 'cached': .1, 'cache_write': 2.5, 'cache_write_long': 5.0, 'output': 10.0,
          'source': 'https://developers.openai.com/api/docs/models/gpt-6.1-sol'},
    'A': {'input': 4.0, 'cached': .2, 'cache_write': 5.0, 'cache_write_long': 8.0, 'output': 20.0,
          'source': 'https://platform.claude.com/docs/en/models/opus-5-5/whats-new-opus-5-5'}
}

def settings(config, model):
    prefix = 'gpt' if model == 'O' else 'claude'
    return {k: getattr(config, prefix+'_'+k) for k in ['model', 'effort', 'max_output_tokens']}

def request_body(config, model, prompt):
    s = settings(config, model)
    if model == 'O':
        return {'model': s['model'], 'input': [{'role': 'user', 'content': prompt}],
                'reasoning': {'effort': s['effort']}, 'max_output_tokens': s['max_output_tokens'],
                'tools': [], 'store': False, 'service_tier': 'default'}
    return {'model': s['model'], 'messages': [{'role': 'user', 'content': prompt}],
            'output_config': {'effort': s['effort']}, 'max_tokens': s['max_output_tokens'],
            'thinking': {'type': 'adaptive'}, 'tools': []}

def allowance(model, prompt, output_cap):
    # UTF-8 bytes upper-bound text token count; margin covers message framing.
    upper_input = len(prompt.encode('utf-8')) + 4096
    if upper_input > 200000:
        raise ValueError('Conservative input bound exceeds supported pricing band; calibration/configuration required')
    return (upper_input * max_input_rate(model) + output_cap * PRICING[model]['output']) / 1e6

def max_input_rate(model):
    # Covers uncached input, reads and either documented write lifetime.
    return max(PRICING[model][k] for k in ['input','cached','cache_write','cache_write_long'])

def price(model, usage):
    p = PRICING[model]
    if model == 'O':
        inp, out = usage['input_tokens'], usage['output_tokens']
        details = usage.get('input_tokens_details') or {}
        cached = details.get('cached_tokens', 0)
        written = details.get('cache_write_tokens', 0)
        write_details = details.get('cache_write_tokens_details') or {}
        long_writes = write_details.get('ttl_12h_tokens', 0)
        short_writes = write_details.get('ttl_30m_tokens', written-long_writes)
        if short_writes+long_writes != written or cached+written > inp:
            raise ValueError('Inconsistent cache usage; retain unresolved reservation')
        # Reasoning tokens are already included in output_tokens.
        return ((inp-cached-written)*p['input'] + cached*p['cached'] + short_writes*p['cache_write']
                + long_writes*p['cache_write_long'] + out*p['output'])/1e6
    creation = usage.get('cache_creation_input_tokens', 0)
    long_writes = (usage.get('cache_creation') or {}).get('ephemeral_1h_input_tokens', 0)
    return (usage['input_tokens']*p['input'] + usage.get('cache_read_input_tokens', 0)*p['cached']
            + (creation-long_writes)*p['cache_write'] + long_writes*p['cache_write_long'] + usage['output_tokens']*p['output'])/1e6

def http(model, path, body=None, timeout=30):
    key = os.environ['OPENAI_API_KEY' if model == 'O' else 'ANTHROPIC_API_KEY']
    base = 'https://api.openai.com/v1' if model == 'O' else 'https://api.anthropic.com/v1'
    headers = {'Content-Type': 'application/json'}
    headers.update({'Authorization': 'Bearer '+key} if model == 'O' else {'x-api-key': key, 'anthropic-version': '2026-10-21'})
    req = urllib.request.Request(base+path, data=json.dumps(body).encode() if body is not None else None, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return json.load(response)

def availability(config):
    for model in set(c for cond in config.conditions for c in cond):
        requested = settings(config, model)['model']
        # Read-only model retrieval, no inference and no model substitution.
        result = http(model, '/models/'+requested, timeout=config.api_timeout)
        if not result.get('id'):
            raise ValueError(f'Model unavailable: {requested}')

def generate(config, job, rendered):
    started = time.time()
    model = job['model']
    body = request_body(config, model, rendered)
    raw = http(model, '/responses' if model == 'O' else '/messages', body, config.api_timeout)
    if model == 'O':
        text = '\n'.join(c['text'] for o in raw.get('output', []) if o.get('type') == 'message'
                         for c in o.get('content', []) if c.get('type') == 'output_text')
        stop = raw.get('status')
        truncated = stop == 'incomplete' and (raw.get('incomplete_details') or {}).get('reason') == 'max_output_tokens'
    else:
        text = '\n'.join(c['text'] for c in raw.get('content', []) if c.get('type') == 'text')
        stop = raw.get('stop_reason')
        truncated = stop == 'max_tokens'
    usage = raw.get('usage')
    cost = None
    if usage:
        try:
            cost = price(model, usage)
        except (KeyError, TypeError, ValueError):
            # Preserve the response and reservation if billing fields are absent.
            pass
    return {'text': text, 'raw': raw, 'usage': usage, 'requested_model': body['model'],
            'returned_model': raw.get('model'), 'stop_reason': stop, 'truncated': truncated,
            'provider_complete': stop == ('completed' if model == 'O' else 'end_turn'),
            'incomplete_details': raw.get('incomplete_details'), 'latency': time.time()-started,
            'timestamp': started, 'request_hash': digest(body)}, cost

def mock_generate(config, job, rendered):
    # Fixed offline fixtures encode outcomes without executing any generated code.
    index = int(job['task_id'].split('/')[-1])
    arm, role = job['arm'], job['role']
    passed = (index + (0 if job['model'] == 'A' else 1)) % 3 != 0
    if role == 'reviewer':
        passed = (index + {'AO': 1, 'OA': 0, 'AA': 2, 'OO': 1}[arm]) % 4 != 0
    fixture = ROOT/'fixtures'/'mock-responses.json'
    responses = read(fixture if fixture.exists() else PACKAGE/'resources'/'mock-responses.json')
    text = responses['pass' if passed else 'fail']
    usage = {'input_tokens': 120, 'output_tokens': 40}
    return {'text': text, 'raw': {'synthetic': True, 'text': text}, 'usage': usage,
            'requested_model': settings(config, job['model'])['model'], 'returned_model': 'SYNTHETIC-'+job['model'],
            'stop_reason': 'synthetic_end', 'truncated': False, 'latency': .1,
            'timestamp': time.time(), 'fixture_passed': passed}, 0.0
