"""One explicitly authorized NativeNotes P2 run; no credential reads/prints or oracle edits.
Called by the reviewed private provider helper with its minimal models path and private work.
"""
import os
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import uuid

ROOT=Path(__file__).resolve().parent.parent
WORKSPACE=Path(os.environ["CRAFT_NATIVE_WORKSPACE"])
FIXTURE=WORKSPACE/'fixtures/native-notes'
QUAL=WORKSPACE/'verification/craft-implementation-2026-11-09/runtime-qualification'
CSC=Path(os.environ["CRAFT_NATIVE_CSC"])
NODE=Path(os.environ["CRAFT_TEST_NODE"])
PI=Path(os.environ["CRAFT_PI_ENTRY"])

def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def ref(path):return {'path':str(Path(path).resolve()),'sha256':sha(path)}
def write(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('x',encoding='utf-8') as f:json.dump(value,f,indent=2)
    return ref(path)
def run(args,**kw):return subprocess.run([str(x) for x in args],capture_output=True,text=True,timeout=kw.pop('timeout',60),**kw)
def checked(args,**kw):
    p=run(args,**kw)
    if p.returncode:raise RuntimeError('owned-command-failed-'+str(p.returncode))
    return p

def launcher(source,output,script):
    text='''using System;using System.IO;using System.Diagnostics;using System.Security.Cryptography;
class Host {static string Hash(string p){using(var h=SHA256.Create())return BitConverter.ToString(h.ComputeHash(File.ReadAllBytes(p))).Replace("-","").ToLowerInvariant();}
static string Q(string s){return "\\\""+s.Replace("\\\"","\\\\\\\"")+"\\\"";}
static int Main(string[] a){try{if(a.Length!=2||Hash(a[0])!=a[1]||Hash(SCRIPT)!=SCRIPTHASH)return 2;
var p=new Process();p.StartInfo=new ProcessStartInfo(PYTHON,Q(SCRIPT)+" "+Q(a[0])+" "+Q(a[1]));p.StartInfo.UseShellExecute=false;p.StartInfo.RedirectStandardOutput=true;p.StartInfo.RedirectStandardError=true;
p.Start();var so=p.StandardOutput.ReadToEndAsync();var se=p.StandardError.ReadToEndAsync();if(!p.WaitForExit(55000)){p.Kill();return 2;}Console.Write(so.Result);Console.Error.Write(se.Result);return p.ExitCode;}catch{return 2;}}}
'''
    for key,value in [('SCRIPTHASH',sha(script)),('SCRIPT',str(script)),('PYTHON',sys.executable)]:text=text.replace(key,json.dumps(value))
    source.write_text(text,encoding='utf-8')
    checked([CSC,'/nologo','/target:exe','/platform:x64','/out:'+str(output),source])

def controls(private,frozen):
    sys.path.insert(0,str(FIXTURE));from build import compile_cs
    reports=[]
    for kind,expected in [('baseline',True),('candidate',False)]:
        root=private/('precontrol-'+kind);root.mkdir();source=root/'NativeNotes.cs';shutil.copy2(FIXTURE/kind/'NativeNotes.cs',source)
        build=compile_cs(source,root/'NativeNotes.exe');receipt=root/'compile.json';write(receipt,build)
        shutil.copy2(FIXTURE/'seed.json',root/'notes.json')
        config=dict(frozen,control=True,app_root=str(root),source_sha256=sha(source),executable_sha256=sha(root/'NativeNotes.exe'),control_build_receipt=str(receipt))
        m=root/'host-inputs.json';write(m,config)
        p=run([sys.executable,ROOT/'scripts/native_headless_host.py',m,sha(m)],cwd=root)
        observed=json.loads((root/'headless-observation.json').read_text(encoding='utf-8'))
        passed=p.returncode==0 and observed['status']=='passed'
        if passed!=expected:raise RuntimeError('pre-model-control-did-not-discriminate-'+kind)
        if (not expected and not (observed['status']=='functional-failure' and observed['failure_code']=='candidate-exit-protocol')):
            raise RuntimeError('known-control-did-not-fail-expected-io-stage')
        reports.append({'kind':kind,'expected_pass':expected,'observed':observed,'sha256':sha(root/'headless-observation.json')})
    return reports

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--models-json',type=Path,required=True);parser.add_argument('--private-work',type=Path,required=True);parser.add_argument('--output',type=Path,required=True);parser.add_argument('--controls-only',action='store_true')
    a=parser.parse_args();started=time.monotonic();private=a.private_work.resolve();a.output.mkdir(parents=True,exist_ok=False)
    reviewed=json.loads((QUAL/'workspace-compat-v3-8cf81597/verification.v3.json').read_text(encoding='utf-8'))
    if not reviewed['ok']:raise RuntimeError('fixture-review-not-passed')
    for item in reviewed['sources'].values():
        if sha(item['path'])!=item['sha256']:raise RuntimeError('reviewed-fixture-source-drift')
    if sha(FIXTURE/'candidate/NativeNotes.cs')!='303d6de1b6fd853ded6bfd81b4bcc8b5dd2c7355fd5c41cc86e07f4a8eea7727':raise RuntimeError('defective-candidate-source-drift')
    frozen={'fixture_root':str(FIXTURE),'seed_sha256':sha(FIXTURE/'seed.json'),'compiler_sha256':sha(CSC),'task_id':'T-native-persist',
        'frozen_inputs':[ref(FIXTURE/n) for n in ('oracle.py','owned_process.py','seed.json','contract.json')]+[ref(CSC),ref(ROOT/'scripts/native_headless_host.py')]}
    before=controls(private,frozen);write(a.output/'pre-model-controls.json',before)
    if a.controls_only:return 0
    ws=private/'workspace'
    prepare=ROOT/'target/debug/examples/prepare_native.exe'
    checked([prepare,ws,FIXTURE/'baseline/NativeNotes.cs',FIXTURE/'candidate/NativeNotes.cs'])
    app=ws/'app';control=private/'owner-control';control.mkdir()
    frozen['app_root']=str(app)
    inputs=control/'host-inputs.json';write(inputs,frozen)
    launcher(app/'NativeHost.cs',app/'NativeHost.exe',ROOT/'scripts/native_headless_host.py')
    task=write(ws/'reference/task.json',{'task_id':'T-native-persist','request':'Repair the no-persistence candidate. Preserve validation, errors, selection/list behavior and atomic save. Do not copy original source or change oracle/host/contract. Only edit app/NativeNotes.cs. Owner runs an explicit fresh build and external headless checks; final independent native UI follows.'})
    contract=ws/'reference/contract.json';shutil.copy2(FIXTURE/'contract.json',contract)
    build_command=subprocess.list2cmdline([str(CSC),'/nologo','/utf8output','/target:exe','/platform:x64','/out:NativeNotes.exe','/reference:System.dll','/reference:System.Core.dll','/reference:System.Web.Extensions.dll','/reference:System.Windows.Forms.dll','/reference:System.Drawing.dll','NativeNotes.cs'])
    baseline=private/'external-observations';baseline.mkdir()
    observed_bundle=write(control/'observations.json',{'kind':'external/observation','authority':'raw-observation','fixture_review':ref(QUAL/'workspace-compat-v3-8cf81597/verification.v3.json'),'baseline_controls':before[0],'known_defect_control':before[1],'limits':['Owned designed fixture; not official REA Evidence','No prototype visual equivalence claim']})
    checks=[{'id':'build','implementation':'bounded-command-build-v1','required':True,'baseline':None,'kind':None,'depends_on':[]},{'id':'external-scenario','implementation':'external-scenario-v2','required':True,'baseline':'native-headless','kind':'scenario','depends_on':['build']}]
    check_ref=write(control/'check-plan.json',checks)
    scenario={'version':2,'task_id':'T-native-persist','evidence_id':'native-owned-baseline-observation','harness':'direct-exec-v1','reset':'fresh-copy-v1','program':'NativeHost.exe','runtime_files':['NativeNotes.exe'],'seed_files':[{'relative_path':'notes.json','content':ref(FIXTURE/'seed.json')},{'relative_path':'result-status.txt','content':None}],
        'arguments':[str(inputs),sha(inputs)],'stdin':'','environment':{k:os.environ[k] for k in ('SystemRoot','WINDIR','TEMP','TMP') if k in os.environ},'timeout_secs':60,'exit_code':0,'stdout':'native-notes-headless-pass\n','stderr':'','state_files':[{'relative_path':'result-status.txt','sha256':hashlib.sha256(b'passed\n').hexdigest()}]}
    scenario_ref=write(baseline/'scenario.json',scenario)
    source_base=json.loads(checked([prepare,'--digest',app]).stdout)['source_base_sha256']
    owner=uuid.uuid4().hex
    p={'version':1,'mode':'buildcheck','identity':{'case_ref':observed_bundle,'scope_ref':ref(contract),'workitem_ref':task,'feature_ref':task,'acceptance_ref':ref(QUAL/'workspace-compat-v3-8cf81597/verification.v3.json'),'task_ids':['T-native-persist']},
        'original':{'target':{'kind':'local','path':str(FIXTURE/'baseline/NativeNotes.cs')},'target_identity':sha(FIXTURE/'baseline/NativeNotes.cs'),'bundle':observed_bundle,'traceability':observed_bundle,'scenarios':scenario_ref,'qualifications':ref(CSC),'environment':ref(inputs)},
        'baseline':{'version':1,'root':str(baseline),'bundle_sha256':observed_bundle['sha256'],'artifacts':[{'key':'native-headless','kind':'scenario','origin_kind':'external/observation','evidence_id':'native-owned-baseline-observation','operation':'owned-baseline-cli-and-disk-observation','provider':'reviewed-native-fixture','environment':'Windows .NET Framework owned Jobs','authority':'raw-observation','limitations':['Designed fixture only; native REA claims remain unknown'],'source':observed_bundle,'output':scenario_ref,'converter_version':'trusted-native-host-v1','parameters':{'slice':'persist/reopen/validation/io-error'},'field_mapping':{'ordered_streams':'exact','disk':'independent-existing-oracle'},'losses':['Prototype visual equivalence not evaluated']}]},
        'check_plan_ref':check_ref,'checks':checks,'source_base_sha256':source_base,'app_root':str(app),'writable_roots':[str(app)],'read_references':[task,ref(contract)],'commands':[{'command':build_command,'cwd':str(app),'timeout_secs':60}],'build':{'command_index':0,'artifacts':['NativeNotes.exe']},'protected_paths':[str(app/'NativeHost.cs'),str(app/'NativeHost.exe')],'kind_id':'app','stack':'C# .NET Framework WinForms','model':{'allowed':True,'expected':{'provider':'magpie','model':'gpt/gpt-6.1-sol','effort':'high'},'backend_id':'craft-pi-rpc-v1','permission_contract':'pi-rpc-bounded-v1'},'owner_id':owner,'max_wall_secs':1050,'failed_feedback':None}
    policy=control/'policy.json';write(policy,p)
    instructions=control/'builder-instructions.md';shutil.copy2(WORKSPACE/'dev/installer-craft-integration/adapters/craft-pi/builder-instructions.md',instructions)
    driver=ROOT/'target/bridge-driver/debug/pi-rpc-driver.exe'
    config={'contract_version':1,'policy':str(policy),'policy_sha256':sha(policy),'workspace':str(ws),'create_workspace':False,'run_root':str(private/'run'),'driver':str(driver),'driver_sha256':sha(driver),'credential_env_keys':['CRAFT_RPC_QUALIFICATION_API_KEY'],'provider_manifest':ref(a.models_json),'instructions':str(instructions),'instructions_sha256':sha(instructions),'max_refinements':2,'stop_marker':str(private/'stop'),'message':'Read reference/task.json and reference/contract.json. Repair only app/NativeNotes.cs so real saves persist atomically and new processes reopen saved data. Preserve validation and errors. Use only allowed tools. The frozen exact build command is '+build_command+'. Owner checks the actual fresh build, errors, disk state and reopen. Do not change NativeHost, oracle, policy or accepted inputs.'}
    config_path=control/'execution.json';write(config_path,config)
    env=os.environ.copy();env.update(CRAFT_PI_NODE=str(NODE),CRAFT_PI_ENTRY=str(PI),CRAFT_PI_VERSION='1.5.0')
    # Raw provider/driver output is discarded. The executor separately writes its sanitized result.
    proc=subprocess.Popen([str(ROOT/'target/debug/craft-pi-executor.exe'),'--run',str(config_path)],env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    remaining=max(5,1120-(time.monotonic()-started))
    try:code=proc.wait(timeout=remaining)
    except subprocess.TimeoutExpired:
        (private/'stop').write_text('owner timeout',encoding='utf-8')
        try:code=proc.wait(timeout=20)
        except subprocess.TimeoutExpired:
            subprocess.run(['taskkill','/PID',str(proc.pid),'/T','/F'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=10);proc.wait(timeout=5);code=124
    candidate=private/'run/candidate.json'
    summary={'kind':'real-provider-native-p2-experiment','executor_exit':code,'accepted':False,'actual_source':ref(app/'NativeNotes.cs'),'original_candidate_sha256':'303d6de1b6fd853ded6bfd81b4bcc8b5dd2c7355fd5c41cc86e07f4a8eea7727','policy_sha256':sha(policy),'driver':ref(driver),'runtime_helper_budget_seconds':1200,'max_refinements':2,'configured_response_maxTokens':8192,'wall_seconds':time.monotonic()-started,'private_execution_config':str(config_path),'private_workspace':str(ws)}
    if candidate.exists():summary['candidate']=json.loads(candidate.read_text(encoding='utf-8'))
    write(a.output/'model-run.json',summary)
    return 0 if summary.get('candidate',{}).get('state')=='candidate' else 1

if __name__=='__main__':
    try:raise SystemExit(main())
    except Exception as error:
        print(json.dumps({'ok':False,'error_type':type(error).__name__,'detail':'qualification setup failed; raw diagnostic suppressed'}));raise SystemExit(2)
