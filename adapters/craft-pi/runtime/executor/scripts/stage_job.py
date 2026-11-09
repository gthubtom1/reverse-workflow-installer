"""One bounded staging build; separate logs; no active installation or shared target."""
import os
import json
from pathlib import Path
import subprocess
import sys
import time
ROOT=Path(__file__).resolve().parent.parent
stage=ROOT/'staging'/('stage-'+time.strftime('%Y%m%dT%H%M%S'))
bundle=ROOT/'staging'/(stage.name+'-bundle')
command=[sys.executable,str(ROOT/'scripts/stage_build.py'),'--stage',str(stage),'--bundle',str(bundle),'--executor-source',str(ROOT),'--bridge-source',str(ROOT.parent/'craft-pi-bridge'),'--craft-source',str(ROOT.parent/'craft-anything-adapted'),'--patch-manifest',str(ROOT.parent/'craft-anything-adapted/patches/bounded-accepted-research/series.json'),'--gnu-bin',os.environ["CRAFT_GNU_BIN"],'--source-description','Reviewed owned executor + bridge and exact upstream 0326 + policy N1 ordered patches; isolated local GNU build']
started=time.time()
with (ROOT/'stage.stdout.log').open('wb') as out,(ROOT/'stage.stderr.log').open('wb') as err:
    p=subprocess.Popen(command,stdout=out,stderr=err)
    try:
        code=p.wait(timeout=900)
    except subprocess.TimeoutExpired:
        subprocess.run(['taskkill','/PID',str(p.pid),'/T','/F'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=15)
        p.wait(timeout=10)
        code=124
record={'command':command,'exit_code':code,'seconds':time.time()-started,'stage':str(stage),'bundle':str(bundle)}
(ROOT/'stage.result.json').write_text(json.dumps(record,indent=2),encoding='utf-8')
sys.exit(code)
