"""Resolve the official evaluator image without starting Docker or generated code."""
import json
import pathlib
import urllib.request

repo = 'bigcodebench/bigcodebench-evaluate'
url = f'https://auth.docker.io/token?service=registry.docker.io&scope=repository:{repo}:pull'
token = json.load(urllib.request.urlopen(url))['token']
req = urllib.request.Request(f'https://registry-1.docker.io/v2/{repo}/manifests/latest', headers={
    'Authorization':'Bearer '+token,'Accept':'application/vnd.oci.image.index.v1+json, application/vnd.docker.distribution.manifest.list.v2+json, application/vnd.docker.distribution.manifest.v2+json'})
with urllib.request.urlopen(req) as response:
    digest = response.headers['Docker-Content-Digest']
root = pathlib.Path(__file__).resolve().parents[1]
dockerfile = f'''# Official dependency environment, frozen by registry manifest digest.
# Evaluator Python code is overlaid from its separately pinned commit.
FROM {repo}@{digest}
USER root
RUN git -C /bigcodebench fetch origin 09dd993f46c3fbf3a799465bb96d524edcb0b199 && git -C /bigcodebench checkout 09dd993f46c3fbf3a799465bb96d524edcb0b199 && pip install --no-deps /bigcodebench
COPY docker/worker.py /opt/worker.py
ENV PYTHONDONTWRITEBYTECODE=1
WORKDIR /work
USER 65534:65534
ENTRYPOINT ["python", "/opt/worker.py"]
'''
(root/'docker'/'Dockerfile').write_text(dockerfile)
(root/'docker'/'base.lock.json').write_text(json.dumps({'image':repo,'digest':digest,'resolved':'2026-10-24'},indent=2)+'\n')
print(repo+'@'+digest)
