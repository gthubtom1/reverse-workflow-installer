"""Capture bounded public verification identity; never inspect provider/private resources."""
import os
import hashlib
import json
from pathlib import Path
import subprocess

ROOT=Path(__file__).resolve().parent.parent

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def command(args):
    p=subprocess.run(args,capture_output=True,text=True,timeout=15,check=True)
    return p.stdout

files={}
for name in ('Cargo.toml','Cargo.lock','README.md','entry-protocol.json','ATTRIBUTION.md','THIRD_PARTY_NOTICES.md'):
    files[name]=sha(ROOT/name)
for directory in ('src','scripts','tests','examples','docs'):
    for path in sorted((ROOT/directory).rglob('*')):
        if path.is_file() and '__pycache__' not in path.parts:
            files[path.relative_to(ROOT).as_posix()]=sha(path)
source_tree_sha256=hashlib.sha256(json.dumps(files,sort_keys=True,separators=(',',':')).encode('utf-8')).hexdigest()
result={'schema':1,'source_tree_sha256':source_tree_sha256,'source_tree_hash_rule':'SHA256 of UTF-8 JSON sorted source path->file SHA256 map, separators comma/colon, no trailing newline','source_files':files,'rustc':command(['rustc','+stable-x86_64-pc-windows-gnu','--version']).strip(),'binaries':{},'checks':{}}
for relative in ('target/debug/craft-pi-executor.exe','target/bridge-driver/debug/pi-rpc-driver.exe'):
    path=ROOT/relative
    if path.is_file():
        imports=command([str(Path(os.environ["CRAFT_GNU_BIN"]) / "objdump.exe"),'-p',str(path)])
        names=sorted({line.split('DLL Name:',1)[1].strip() for line in imports.splitlines() if 'DLL Name:' in line})
        result['binaries'][relative]={'sha256':sha(path),'bytes':path.stat().st_size,'pe_imports':names}
for mode in ('check','test'):
    path=ROOT/(mode+'.result.json')
    if path.is_file():result['checks'][mode]={'result':json.loads(path.read_text(encoding='utf-8')),'stdout_sha256':sha(ROOT/(mode+'.stdout.log')),'stderr_sha256':sha(ROOT/(mode+'.stderr.log'))}
result['entry_inspect']=json.loads(command([str(ROOT/'target/debug/craft-pi-executor.exe'),'--inspect']))
for name in ('offline-result.json','cancel-result.json'):
    path=ROOT/'test-artifacts'/name
    if path.is_file():
        artifact=json.loads(path.read_text(encoding='utf-8'))
        result[name]={'sha256':sha(path),'state':artifact['state'],'accepted':artifact['accepted'],'checks':[{'id':c['check'],'round':c['round'],'passed':c['passed']} for c in artifact['checks']], 'driver_exits':[t.get('driver_exit') for t in artifact['actual_turns']],'cleanup':artifact['cleanup']}
(ROOT/'SOURCE-MANIFEST.json').write_text(json.dumps({'schema':1,'source_tree_sha256':source_tree_sha256,'hash_rule':result['source_tree_hash_rule'],'files':files},indent=2),encoding='utf-8')
output=ROOT/'verification-identity.json'
output.write_text(json.dumps(result,indent=2),encoding='utf-8')
print(json.dumps({'output':str(output),'source_files':len(files),'checks':{k:v['result']['exit_code'] for k,v in result['checks'].items()},'entry':result['entry_inspect']}))
