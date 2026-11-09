"""Bounded actual native qualification job; public progress, no raw provider output."""
import os
import json
from pathlib import Path
import subprocess
import sys
import time
import uuid
ROOT=Path(__file__).resolve().parent.parent
workspace=Path(os.environ["CRAFT_NATIVE_WORKSPACE"])
mode=sys.argv[1] if len(sys.argv)>1 else 'run'
identity=time.strftime('%Y%m%dT%H%M%S')+'-'+uuid.uuid4().hex[:6]
public=ROOT/'test-artifacts'/('native-'+mode+'-'+identity)
if mode=='controls':
    private=ROOT/'test-artifacts'/('native-control-work-'+identity);private.mkdir(parents=True)
    command=[sys.executable,str(ROOT/'scripts/run_native_qualification.py'),'--models-json',str(private/'unused-models.json'),'--private-work',str(private),'--output',str(public),'--controls-only']
    timeout=150
else:
    command=[sys.executable,str(workspace/'verification/craft-implementation-2026-11-09/runtime-qualification/private_provider_env.py'),'--purpose','build','--max-output-tokens','8192','--timeout-seconds','1200','--',sys.executable,str(ROOT/'scripts/run_native_qualification.py'),'--models-json','{models_json}','--private-work','{private_work}','--output',str(public)]
    timeout=1225
progress=ROOT/'native-job-progress.json'
record={'mode':mode,'state':'running','public_output':str(public),'command':command,'started_unix':time.time()}
progress.write_text(json.dumps(record,indent=2),encoding='utf-8')
with (ROOT/('native-'+mode+'.stdout.log')).open('wb') as out,(ROOT/('native-'+mode+'.stderr.log')).open('wb') as err:
    p=subprocess.Popen(command,stdout=out,stderr=err)
    try:code=p.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        subprocess.run(['taskkill','/PID',str(p.pid),'/T','/F'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=15);p.wait(timeout=10);code=124
record.update(state='finished',exit_code=code,seconds=time.time()-record['started_unix'])
progress.write_text(json.dumps(record,indent=2),encoding='utf-8')
(ROOT/('native-'+mode+'.result.json')).write_text(json.dumps(record,indent=2),encoding='utf-8')
sys.exit(code)
