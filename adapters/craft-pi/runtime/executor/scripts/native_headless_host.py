"""Trusted, hash-frozen NativeNotes inline headless slice; never a model/provider.
Runs actual candidate processes and the separately reviewed disk oracle in the real policy
fresh-copy directory. Public stdout is a fixed success marker only after observed checks.
"""
import hashlib
import json
import os
from pathlib import Path
import sys
import time


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def source_digest(app, excluded):
    files=[]
    for directory,dirs,names in os.walk(app):
        dirs[:]=[d for d in dirs if d not in ('target','node_modules','.git','.craft-owner.lock')]
        for name in names:
            path=Path(directory)/name
            if name=='.craft-owner.lock' or path.relative_to(app).as_posix() in excluded:continue
            if path.is_symlink():raise RuntimeError('source-link')
            files.append(path)
    h=hashlib.sha256()
    for path in sorted(files):
        h.update(path.relative_to(app).as_posix().encode());h.update(b'\0');h.update(sha(path).encode());h.update(b'\0')
    return h.hexdigest()

def main():
    manifest_path=Path(sys.argv[1]).resolve(); expected=sys.argv[2]
    if sha(manifest_path)!=expected:raise RuntimeError('host-manifest-drift')
    manifest=json.loads(manifest_path.read_text(encoding='utf-8'))
    for entry in manifest['frozen_inputs']:
        if sha(entry['path'])!=entry['sha256']:raise RuntimeError('reviewed-harness-input-drift')
    root=Path.cwd().resolve();exe=root/'NativeNotes.exe';data=root/'notes.json'
    app=Path(manifest['app_root'])
    if manifest.get('control'):
        runtime={'NativeNotes.exe':manifest['executable_sha256']}
        if sha(exe)!=runtime['NativeNotes.exe'] or sha(app/'NativeNotes.cs')!=manifest['source_sha256']:raise RuntimeError('control-source-exe-drift')
        build_path=Path(manifest['control_build_receipt']);build=json.loads(build_path.read_text(encoding='utf-8'))
        if build['artifact']['sha256']!=sha(exe) or build['source']['sha256']!=manifest['source_sha256']:raise RuntimeError('control-build-binding')
    else:
        seed=json.loads((root/'initial-seed-receipt.json').read_text(encoding='utf-8'))
        if seed['version']!=2 or seed['harness']!='direct-exec-v1' or seed['reset']!='fresh-copy-v1':raise RuntimeError('not-real-policy-v2-attempt')
        runtime={r['path']:r['sha256'] for r in seed['runtime']}
        if runtime.get('NativeNotes.exe')!=sha(exe) or runtime.get('NativeHost.exe')!=sha(root/'NativeHost.exe'):raise RuntimeError('fresh-runtime-drift')
        matches=[]
        for path in root.parent.glob('build-*/build-receipt.json'):
            build=json.loads(path.read_text(encoding='utf-8'))
            if any(o['path']=='NativeNotes.exe' and o['sha256']==sha(exe) and o['nonempty'] for o in build['outputs']):matches.append((path,build))
        if len(matches)!=1:raise RuntimeError('fresh-exe-has-no-unique-build-receipt')
        build_path,build=matches[0]
        if build['exit_code']!=0 or build['source_before_sha256']!=build['source_after_sha256'] or source_digest(app,['NativeNotes.exe'])!=build['source_after_sha256']:raise RuntimeError('compiled-source-binding-failed')
    if sha(data)!=manifest['seed_sha256']:raise RuntimeError('seed-mismatch')
    sys.path.insert(0,manifest['fixture_root'])
    from oracle import expected_seed,expected_saved,assert_disk
    from owned_process import execute
    actual=[];checks=[];started=time.monotonic()
    def invoke(*args,code=0,error=None):
        if time.monotonic()-started>45:raise RuntimeError('headless-deadline')
        if sha(exe)!=runtime['NativeNotes.exe']:raise RuntimeError('candidate-executable-drift')
        out=execute([str(exe),*map(str,args)],timeout=5)
        actual.append({k:v for k,v in out.items() if k not in ('stdout','stderr')})
        if out['status']!='completed' or not out['cleanup']['verified'] or out['cleanup'].get('members_after')!=[]:raise RuntimeError('candidate-cleanup-unknown')
        payload=json.loads(out['stdout'] if out['exit_code']==0 else out['stderr'])
        if out['exit_code']!=code or payload.get('ok') is not (code==0) or (error and payload.get('code')!=error):raise AssertionError('candidate-exit-protocol')
        return payload
    report={'schema':1,'kind':'trusted-inline-headless-observation','accepted':False,'task_id':manifest['task_id'],
        'actual_executable_sha256':sha(exe),'actual_source_sha256':sha(app/'NativeNotes.cs'),'compiler_sha256':manifest['compiler_sha256'],
        'policy_initial_receipt_sha256':sha(root/'initial-seed-receipt.json') if not manifest.get('control') else None,'build_receipt':str(build_path),'build_receipt_sha256':sha(build_path),'checks':checks,'invocations':actual}
    try:
        if invoke('list',data).get('state')!=expected_seed():raise AssertionError('initial-list')
        checks.append('initial-list')
        before=data.read_bytes()
        for title,body in [(' ','body'),('x'*61,'body'),('<bad>','body'),('Valid','x'*501)]:
            invoke('save',data,'note-1',title,body,code=2,error='invalid-input')
            if data.read_bytes()!=before:raise AssertionError('invalid-input-wrote-state')
        checks.append('validation-no-write')
        os.chmod(data,0o444)
        try:invoke('save',data,'note-1','Saved title','Persisted body 42',code=5,error='save-failed')
        finally:os.chmod(data,0o666)
        if data.read_bytes()!=before:raise AssertionError('failed-save-wrote-state')
        checks.append('io-error-no-write')
        invoke('save',data,'note-1','  Saved title  ','Persisted body 42')
        assert_disk(data,expected_saved())
        if invoke('list',data).get('state')!=expected_saved():raise AssertionError('restart-lost-state')
        checks+=['saved-disk-oracle','new-process-reopen','unchanged-second-note']
        report['status']='passed';(root/'result-status.txt').write_bytes(b'passed\n')
        print('native-notes-headless-pass')
        return 0
    except (AssertionError,RuntimeError,ValueError) as error:
        report['status']='functional-failure' if isinstance(error,AssertionError) else 'blocked-unknown'
        report['failure_type']=type(error).__name__;report['failure_code']=str(error)[:160]
        print('native-notes-headless-failed',file=sys.stderr)
        return 1
    finally:
        (root/'headless-observation.json').write_text(json.dumps(report,indent=2),encoding='utf-8')

if __name__=='__main__':
    try:raise SystemExit(main())
    except Exception:
        print('native-notes-headless-infrastructure-blocked',file=sys.stderr);raise SystemExit(2)
