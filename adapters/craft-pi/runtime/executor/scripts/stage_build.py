"""Build an isolated portable bundle from exact upstream + ordered reviewed patches.
No deployment, registration, active configuration, provider resources or credentials are copied.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess

BASE = '0326b4de8051f85a0f3139cd82f88f76911e6a35'
CONTRACT = {'name':'craft-pi-execution','version':1,'min_reader':1,'required_capabilities':['craft-bundle-integrity-v1','craft-resource-ownership-v1','craft-entry-gate-v1']}

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def run(args, **kwargs):
    return subprocess.run([str(x) for x in args], check=True, timeout=1800, **kwargs)

def copy_source(source, destination):
    destination.mkdir()
    for name in ('Cargo.toml', 'Cargo.lock', 'src'):
        item = source / name
        if item.is_symlink() or not item.exists():
            raise ValueError('owned source missing or linked: '+name)
        if item.is_dir():
            for p in item.rglob('*'):
                if p.is_symlink():
                    raise ValueError('linked owned source refused')
            shutil.copytree(item, destination / name)
        else:
            shutil.copy2(item, destination / name)
    # Driver manifests declare a fixtures-only target; Cargo still requires its path to exist.
    if (source/'tests').is_dir():
        shutil.copytree(source/'tests',destination/'tests')

def pe_imports(executable, objdump):
    out = run([objdump,'-p',executable], capture_output=True, text=True).stdout
    return sorted(set(re.findall(r'DLL Name:\s*([^\s]+)',out)))

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--stage', required=True, type=Path)
    p.add_argument('--bundle', required=True, type=Path)
    p.add_argument('--executor-source', required=True, type=Path)
    p.add_argument('--bridge-source', required=True, type=Path)
    p.add_argument('--craft-source', type=Path, help='optional local Git object source; dirty files are not copied')
    p.add_argument('--patch-manifest', required=True, type=Path, help='base_commit and ordered patches[{path,sha256}], relative to manifest')
    p.add_argument('--gnu-bin', required=True, type=Path)
    p.add_argument('--source-description', required=True)
    p.add_argument('--release', action='store_true')
    a = p.parse_args()
    if not a.stage.is_absolute() or not a.bundle.is_absolute() or a.stage.exists() or a.bundle.exists():
        raise ValueError('fresh absolute stage and bundle directories required')
    patches = json.loads(a.patch_manifest.read_text(encoding='utf-8'))
    # Consume policy worker's actual series.json shape; retain declared order.
    if 'series' in patches:
        patches['patches'] = [{'path':item['file'],'sha256':item['sha256']} for item in patches['series']]
    if patches.get('base_commit') != BASE or not patches.get('patches'):
        raise ValueError('reviewed exact upstream base and ordered patches required')
    for record in patches['patches']:
        patch = a.patch_manifest.parent / record['path']
        if not patch.is_file() or sha(patch) != record['sha256']:
            raise ValueError('reviewed patch identity mismatch')
    a.stage.mkdir(parents=True)
    executor = a.stage/'craft-pi-executor'
    bridge = a.stage/'craft-pi-bridge'
    craft = a.stage/'craft-anything-adapted'
    copy_source(a.executor_source, executor)
    copy_source(a.bridge_source, bridge)
    origin = a.craft_source.resolve() if a.craft_source else 'https://github.com/storytold/craft-anything.git'
    run(['git','clone','--no-checkout','--no-hardlinks',origin,craft])
    run(['git','-C',craft,'checkout','--detach',BASE])
    for record in patches['patches']:
        patch = (a.patch_manifest.parent / record['path']).resolve()
        run(['git','-C',craft,'apply','--check',patch])
        run(['git','-C',craft,'apply',patch])
    actual = run(['git','-C',craft,'rev-parse','HEAD'],capture_output=True,text=True).stdout.strip()
    if actual != BASE:
        raise ValueError('upstream identity mismatch')
    env = os.environ.copy()
    env['PATH'] = str(a.gnu_bin) + os.pathsep + env['PATH']
    env['CARGO_TARGET_X86_64_PC_WINDOWS_GNU_LINKER'] = str(a.gnu_bin/'gcc.exe')
    env['CARGO_BUILD_JOBS'] = '3'
    target = a.stage/'target'
    for manifest, binary in ((executor/'Cargo.toml','craft-pi-executor'),(bridge/'Cargo.toml','pi-rpc-driver')):
        command = ['cargo','+stable-x86_64-pc-windows-gnu','build','--locked','--manifest-path',manifest,'--bin',binary,'--target-dir',target]
        if a.release:
            command += ['--release']
        run(command,env=env)
    a.bundle.mkdir()
    binary_dir = a.bundle/'bin'
    binary_dir.mkdir()
    profile = 'release' if a.release else 'debug'
    pending=[]
    for name in ('craft-pi-executor.exe','pi-rpc-driver.exe'):
        source = target/profile/name
        shutil.copy2(source,binary_dir/name)
        pending.append(binary_dir/name)
    imports={}
    while pending:
        source=pending.pop()
        names=pe_imports(source,a.gnu_bin/'objdump.exe')
        imports[source.name]=names
        for name in names:
            # Copy only actually imported non-system GNU DLLs. Unknown imports block packaging.
            system = Path(os.environ['SystemRoot'])/'System32'/name
            if system.is_file() or name.lower().startswith(('api-ms-win-','ext-ms-win-')):
                continue
            destination = binary_dir/name
            if destination.exists():
                continue
            candidates=list(a.gnu_bin.rglob(name))
            if len(candidates)!=1:
                raise ValueError('unresolved/ambiguous PE runtime import '+name)
            shutil.copy2(candidates[0],destination)
            pending.append(destination)
    shutil.copy2(executor/'Cargo.lock',a.bundle/'Cargo.lock')
    for name in ('LICENSE-MIT','LICENSE-APACHE'):
        shutil.copy2(craft/name,a.bundle/name)
    for name in ('entry-protocol.json','ATTRIBUTION.md','THIRD_PARTY_NOTICES.md'):
        shutil.copy2(a.executor_source/name,a.bundle/name)
    patch_output=a.bundle/'patches'
    patch_output.mkdir()
    ordered=[]
    for index,record in enumerate(patches['patches']):
        name=f'{index+1:03d}.patch'
        shutil.copy2(a.patch_manifest.parent/record['path'],patch_output/name)
        ordered.append({'path':'patches/'+name,'sha256':record['sha256']})
    source_inventory = {}
    for label, source in (('executor',executor),('bridge',bridge)):
        source_inventory[label] = {x.relative_to(source).as_posix():sha(x) for x in sorted(source.rglob('*')) if x.is_file()}
    source_inventory['upstream'] = {'commit':BASE,'lock_sha256':sha(craft/'Cargo.lock'),'patches':patches['patches']}
    source_inventory['toolchain'] = run(['rustc','+stable-x86_64-pc-windows-gnu','--version'],capture_output=True,text=True).stdout.strip()
    (a.bundle/'source-identity.json').write_text(json.dumps(source_inventory,indent=2),encoding='utf-8')
    (a.bundle/'pe-imports.json').write_text(json.dumps(imports,indent=2),encoding='utf-8')
    files={x.relative_to(a.bundle).as_posix():sha(x) for x in sorted(a.bundle.rglob('*')) if x.is_file()}
    manifest={'name':'craft-pi-bundle','version':'0.1.0','contract':CONTRACT,'base_commit':BASE,'pi':{'version':'1.5.0','protocol':'rpc'},
      'artifact':{'os':'windows','arch':'x86_64','source_commit':BASE,'build_source':a.source_description},'patches':ordered,'files':files,
      'runtime':{'entry':'bin/craft-pi-executor.exe','entry_kind':'native','driver':'bin/pi-rpc-driver.exe','driver_kind':'native','entry_protocol':'entry-protocol.json','required_files':['bin/'+x.name for x in sorted(binary_dir.iterdir())]},
      'qualification':'development candidate; no install/activate/model/acceptance claim'}
    (a.bundle/'craft-bundle.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    # Probe a copied standalone entry, not the development target binary.
    probe=run([binary_dir/'craft-pi-executor.exe','--inspect'],cwd=a.bundle,capture_output=True,text=True)
    inspected=json.loads(probe.stdout)
    if inspected.get('contract_version')!=1:
        raise ValueError('packaged entry contract probe failed')
    print(json.dumps({'bundle':str(a.bundle),'files':len(files),'entry_probe':inspected,'pe_imports':imports}))

if __name__ == '__main__':
    main()
