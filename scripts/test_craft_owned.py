"""Offline owned-source regressions in the staged canonical sibling layout. No model calls."""
import argparse
from pathlib import Path
import json
import os
import sys

from craft_sources import validate
from packaging_process import run_owned
from versions import InstallError


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('source-layout','output','cargo','rustc','gcc','node','target-dir','cargo-home'):
        p.add_argument('--'+name,required=True)
    p.add_argument('--release',action='store_true')
    p.add_argument('--offline',action='store_true')
    p.add_argument('--deadline-seconds',type=int,default=1200)
    a=p.parse_args(argv)
    layout=Path(a.source_layout).absolute()
    output=Path(a.output).absolute()
    if output.exists():raise InstallError('test output must be fresh')
    output.mkdir(parents=True)
    from build_craft_bundle import isolated_env, TARGET, sha, write_json
    env=isolated_env()
    tools={k:Path(getattr(a,k)).absolute() for k in ('cargo','rustc','gcc','node')}
    if any(not t.is_file() for t in tools.values()):raise InstallError('explicit test tool missing')
    env.update({'PATH':str(tools['gcc'].parent)+os.pathsep+str(tools['cargo'].parent)+os.pathsep+env.get('PATH',''),
                'RUSTC':str(tools['rustc']),'CARGO_TARGET_X86_64_PC_WINDOWS_GNU_LINKER':str(tools['gcc']),
                'CARGO_HOME':str(Path(a.cargo_home).absolute()),'CARGO_BUILD_JOBS':'3','CRAFT_TEST_NODE':str(tools['node']),
                'CRAFT_TEST_CARGO':str(tools['cargo']),'TMP':str(output/'tmp'),'TEMP':str(output/'tmp')})
    (output/'tmp').mkdir()
    snapshots={name:validate(layout/name,kind) for name,kind in [('craft-pi-bridge','bridge'),('craft-pi-executor','executor')]}
    target=Path(a.target_dir).absolute()
    driver=target/TARGET/( 'release' if a.release else 'debug')/'pi-rpc-driver.exe'
    common=['--locked','--target',TARGET,'--target-dir',str(target)]
    if a.release:common.append('--release')
    if a.offline:common.append('--offline')
    results=[]
    commands=[('driver-build',[tools['cargo'],'build','--manifest-path',layout/'craft-pi-bridge/Cargo.toml','--bin','pi-rpc-driver',*common]),
              ('bridge',[tools['cargo'],'test','--manifest-path',layout/'craft-pi-bridge/Cargo.toml','--all-targets','--features','fixtures',*common,'--','--test-threads=4']),
              ('executor',[tools['cargo'],'test','--manifest-path',layout/'craft-pi-executor/Cargo.toml','--features','fixtures',*common,'--','--test-threads=1'])]
    import time
    deadline=time.monotonic()+min(max(a.deadline_seconds,1),1200)
    for name,cmd in commands:
        fixture_root=output/(name+'-fixtures');fixture_root.mkdir()
        env.update({'CRAFT_TEST_ROOT':str(fixture_root),'CRAFT_TEST_DRIVER':str(driver)})
        remaining=deadline-time.monotonic()
        if remaining<=0:raise InstallError('owned regression total deadline exhausted')
        observed=run_owned(cmd,cwd=layout,env=env,timeout=remaining,log_prefix=output/name)
        record={k:v for k,v in observed.items() if k not in ('stdout','stderr')}
        record.update({'name':name,'command':[str(x) for x in cmd]})
        results.append(record)
        write_json(output/'progress.json',{'results':results,'current':name,'model_invoked':False})
        if observed['returncode']!=0 or observed['cleanup']!='verified' or observed['timed_out']:
            raise InstallError('owned regression failed: '+name+'; see exact logs')
    for name,kind in [('craft-pi-bridge','bridge'),('craft-pi-executor','executor')]:
        if validate(layout/name,kind)!=snapshots[name]:raise InstallError('owned source changed during regression')
    write_json(output/'result.json',{'results':results,'source_unchanged':True,'driver_sha256':sha(driver),'model_invoked':False,
                                    'qualification':'offline owned protocol/integration only; not provider/native business acceptance'})
    return 0


if __name__=='__main__':
    try:sys.exit(main())
    except (InstallError,OSError,ValueError) as e:
        print(str(e),file=sys.stderr);sys.exit(2)
