"""Ephemeral trusted proxy; the untrusted evaluator retains network=none."""
from contextlib import contextmanager
import json
import subprocess
import time


class EgressSetupError(Exception):
    pass


@contextmanager
def restricted_broker(image,name,timeout):
    volume=name+'-socket'
    service=name+'-egress'
    deadline=time.monotonic()+timeout
    def command(args):
        left=deadline-time.monotonic()
        if left<=0:
            raise subprocess.TimeoutExpired(args,timeout)
        result=subprocess.run(args,capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=min(30,left))
        if result.returncode:
            raise EgressSetupError('Restricted proxy setup failed: '+result.stderr[-3000:])
        return result.stdout.strip()
    try:
        command(['docker','volume','create','--driver','local','--opt','type=tmpfs','--opt','device=tmpfs',
                 '--opt','o=uid=65534,gid=65534,mode=0700,size=1m',volume])
        command(['docker','run','-d','--rm','--name',service,'--network','bridge','--read-only',
                 '--cap-drop','ALL','--security-opt','no-new-privileges','--pids-limit','64',
                 '--memory','128m','--cpus','0.5','--user','65534:65534',
                 '--mount',f'type=volume,source={volume},target=/egress,volume-nocopy',
                 '--health-cmd','test -S /egress/proxy.sock','--health-interval','1s',
                 '--health-timeout','1s','--health-retries','10',image])
        ready_deadline=min(deadline,time.monotonic()+20)
        while time.monotonic()<ready_deadline:
            state=json.loads(command(['docker','inspect','--format','{{json .State}}',service]))
            if not state.get('Running'):
                raise EgressSetupError('Restricted proxy stopped before becoming ready')
            health=state.get('Health',{}).get('Status')
            if health=='healthy':
                yield volume,max(.01,deadline-time.monotonic())
                return
            if health=='unhealthy':
                raise EgressSetupError('Restricted proxy health check failed')
            time.sleep(.2)
        raise EgressSetupError('Restricted proxy readiness timed out')
    finally:
        for args in [['docker','rm','-f',service],['docker','volume','rm','-f',volume]]:
            try:
                subprocess.run(args,capture_output=True,timeout=15)
            except (OSError,subprocess.TimeoutExpired):
                pass
