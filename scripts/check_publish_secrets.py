"""Scan the Git publish set without printing any credential values.

Use --staged to inspect exact index contents, including archives and PDF text.
The optional ignored local credential backup supplies additional exact matches.
"""
from pathlib import Path
import io
import json
import os
import re
import shutil
import subprocess
import sys
import zipfile

ROOT=Path(__file__).resolve().parents[1]
GIT=shutil.which('git') or str(Path.home()/'.cache/codex-runtimes/codex-primary-runtime/dependencies/native/git/cmd/git.exe')
staged='--staged' in sys.argv
command=[GIT,'ls-files','--cached','-z'] if staged else [GIT,'ls-files','--cached','--others','--exclude-standard','-z']
files=sorted(set(subprocess.check_output(command,cwd=ROOT).decode('utf-8').split('\0'))-{''})
patterns={
    'provider-key':re.compile(rb'(?<![A-Za-z0-9])sk-[A-Za-z0-9_-]{20,}'),
    'github-token':re.compile(rb'(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{30,})'),
    'aws-access-key':re.compile(rb'(?:AKIA|ASIA)[A-Z0-9]{16}'),
    'private-key':re.compile(rb'-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----'),
}
known=[]
backup=ROOT/'.env.credentials-backup'
if backup.exists():
    for line in backup.read_text(encoding='utf-8').splitlines():
        key,sep,value=line.partition('=')
        if sep and len(value.strip())>=20:
            known.append(value.strip().encode())
for name in ['OPENAI_API_KEY','ANTHROPIC_API_KEY','GH_TOKEN','GITHUB_TOKEN']:
    value=os.environ.get(name,'')
    if len(value)>=20: known.append(value.encode())
findings=[]
def inspect(name,data,depth=0):
    for label,pattern in patterns.items():
        if pattern.search(data): findings.append({'path':name,'rule':label})
    if any(value in data for value in known):
        findings.append({'path':name,'rule':'exact-local-credential'})
    if data.startswith(b'PK\x03\x04') and depth<3:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            for item in archive.infolist():
                if not item.is_dir(): inspect(name+'!'+item.filename,archive.read(item),depth+1)
    if data.startswith(b'%PDF'):
        from pypdf import PdfReader
        reader=PdfReader(io.BytesIO(data))
        inspect(name+'!extracted-text','\n'.join(p.extract_text() or '' for p in reader.pages).encode(),depth+1)
for name in files:
    data=subprocess.check_output([GIT,'show',':'+name],cwd=ROOT) if staged else (ROOT/name).read_bytes()
    inspect(name,data)
print(json.dumps({'mode':'staged' if staged else 'publishable working files','files_scanned':len(files),
                  'credential_matches':findings},indent=2))
raise SystemExit(bool(findings))
