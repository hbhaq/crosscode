"""Download pinned public dataset files; never makes inference calls."""
import json
import pathlib
import urllib.request

root = pathlib.Path(__file__).resolve().parents[1]
lock_path = root / 'sources.lock.json'
lock = json.loads(lock_path.read_text()) if lock_path.exists() else {}
lock.setdefault('datasets', {})
for name in ['bigcodebench', 'bigcodebench-hard']:
    repo = 'bigcode/' + name
    info = json.load(urllib.request.urlopen('https://huggingface.co/api/datasets/' + repo))
    revision = lock['datasets'].get(name, {}).get('revision', info['sha'])
    tree = json.load(urllib.request.urlopen(f'https://huggingface.co/api/datasets/{repo}/tree/{revision}?recursive=true'))
    files = [f['path'] for f in tree if f['path'].endswith('.parquet') and '/v0.1.4-' in f['path']]
    if not files:
        raise RuntimeError(f'No v0.1.4 parquet files found in {repo}: {tree}')
    out = root / 'data' / name
    out.mkdir(parents=True, exist_ok=True)
    for file in files:
        target = out / pathlib.Path(file).name
        if not target.exists():
            urllib.request.urlretrieve(f'https://huggingface.co/datasets/{repo}/resolve/{revision}/{file}', target)
    urllib.request.urlretrieve(f'https://huggingface.co/datasets/{repo}/resolve/{revision}/README.md', out/'README.md')
    lock['datasets'][name] = {'repo': repo, 'revision': revision, 'split': 'v0.1.4', 'files': files}
lock_path.write_text(json.dumps(lock, indent=2)+'\n')
print(json.dumps(lock, indent=2))
