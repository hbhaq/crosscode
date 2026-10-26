"""Local evaluator verification only; never imports or invokes model providers."""
from dataclasses import asdict, replace
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from crosscode.core import Config, read, save
from crosscode.evaluator import preflight, evaluate
from crosscode.progress import Progress

root=Path(__file__).resolve().parents[1]
source=root/'runs/docker-hard-five-check'
destination=root/'runs/evaluator-wikibooks-validation'
destination.mkdir(exist_ok=True)
config=replace(Config(**read(source/'config.json')),
    evaluator_image='sha256:afd0ca41f44b14dd7460a52cde246c49e0e4fff6dd84256e2643728917072c7f',
    evaluator_egress_proxy_image='sha256:3304f6c216ff7e417f71a675773d5a1c939dfa4414423fb009e5404685a19ef9')
manifest=read(source/'manifest.json')
manifest['config_hash']=config.identity()
save(destination/'config.json',asdict(config))
save(destination/'manifest.json',manifest)
preflight(config,manifest,destination,Progress(log_path=destination/'progress.log'))
