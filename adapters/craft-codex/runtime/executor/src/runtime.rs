use crate::{adapter::CodexAdapter, new_id, provider, write_json, BACKEND_ID, ExecutionConfig, PERMISSION};
use craft_anything_ai::cli_agents::{AgentAdapter, ArgsCx, CliSpec, McpCommand, StreamParser};
use craft_anything_ai::rebuild::policy::PolicyRuntime;
use craft_anything_ai::{AgentEvent, Conversation, FailureKind, TurnFailure};
use craft_anything_engine::{CancelToken, execution_policy::{ExecutionPolicy, refusal}};
use craft_anything_evidence::ToolError;
use craft_anything_platform::Process;
use craft_codex_bridge::{config::{Cancel, CancelIdentity, CodexCommand, Config, Deadlines, DynamicTool, DynamicToolFunction, McpCommand as BridgeMcp, BUILDER_NAMESPACE, BUILDER_TOOLS}, parser::BridgeParser};
use serde_json::{Value, json};
use std::{path::PathBuf, sync::{Arc, Mutex, atomic::{AtomicBool, Ordering}, mpsc}, thread, time::{Duration, Instant}};

#[derive(Debug, Clone)]
pub struct CodexRuntime { pub execution: ExecutionConfig, pub codex: CodexCommand, pub executable: PathBuf, pub adapter: CodexAdapter, pub receipts: Arc<Mutex<Vec<Value>>>, pub instructions: String }
impl PolicyRuntime for CodexRuntime {
    fn backend_id(&self) -> &str { BACKEND_ID }
    fn permission_contract(&self) -> &str { PERMISSION }
    fn conversation(&self, policy: Arc<ExecutionPolicy>, spec: CliSpec, stop: CancelToken) -> Result<Box<dyn Conversation>, ToolError> {
        if spec.config.model != "codex" || spec.config.ssh_host.is_some() || spec.question || spec.resume.is_some() || spec.options.cli_model.as_deref() != Some(policy.model.expected.model.as_str()) { return Err(refusal("unsupported", "Only fresh local Codex app-server Builder conversations are qualified.")); }
        self.adapter.check_native_options(&spec.options, spec.project.as_deref())?;
        policy.revalidate_builder_inputs()?;
        if serde_json::to_value(self.execution.policy()?).ok() != serde_json::to_value(policy.as_ref()).ok() { return Err(refusal("identity-mismatch", "Runtime policy differs from Craft owner policy.")); }
        let (tx, rx) = mpsc::channel();
        Ok(Box::new(CodexConversation { runtime:self.clone(), policy, spec, owner_stop:stop, local_stop:CancelToken::default(), tx, rx, worker:None, busy:Arc::new(AtomicBool::new(false)), thread:Arc::new(Mutex::new(None)), failure:Arc::new(Mutex::new(None)), turn:0 }))
    }
}
struct CodexConversation { runtime:CodexRuntime, policy:Arc<ExecutionPolicy>, spec:CliSpec, owner_stop:CancelToken, local_stop:CancelToken, tx:mpsc::Sender<AgentEvent>, rx:mpsc::Receiver<AgentEvent>, worker:Option<thread::JoinHandle<()>>, busy:Arc<AtomicBool>, thread:Arc<Mutex<Option<(String,PathBuf)>>>, failure:Arc<Mutex<Option<TurnFailure>>>, turn:u64 }
fn completion_receipt(value: Option<&Value>) -> Value {
    let Some(v)=value else { return Value::Null };
    json!({"success":v["success"],"cleanup":v["cleanup"],"childExit":v["childExit"],"settled":v["settled"],"usage":v["usage"],"nestedUsage":v["nestedUsage"],"cancelAcknowledged":v["cancelAcknowledged"],"terminalAcknowledged":v["terminalAcknowledged"],"actual_model":v["actualModel"],"thread":v["thread"]})
}
pub(crate) fn turn_cleanup_closed(turn:&Value)->bool {
    if !turn["driver_exit"].is_i64() { return false; }
    let c=&turn["completion"]["cleanup"];
    c["status"]=="verified" && c["root_exited"]==true && c["members_empty"]==true && turn["completion"]["terminalAcknowledged"]==true
}
fn event_error(e:impl ToString)->AgentEvent { AgentEvent::Error{message:e.to_string(),remediation:None,log:None} }
fn tools()->Vec<DynamicTool>{vec![DynamicTool{kind:"namespace".into(),name:BUILDER_NAMESPACE.into(),description:"Craft bounded Builder tools; schemas are loaded from the MCP tools/list response by the bridge".into(),tools:BUILDER_TOOLS.iter().map(|full|DynamicToolFunction{kind:"function".into(),name:full.strip_prefix("mcp__craft__").unwrap().into(),description:"Craft bounded Builder tool".into(),input_schema:Value::Null}).collect()}]}
impl CodexConversation {
    fn launch(&mut self, text:&str)->Result<(),ToolError> {
        if self.is_busy(){return Err(refusal("owner-conflict","A Codex turn is already running."));}
        if let Some(w)=self.worker.take(){w.join().map_err(|_|ToolError::internal("Codex transport panicked."))?;}
        self.owner_stop.check()?; self.policy.revalidate_builder_inputs()?; self.runtime.execution.policy()?; crate::read_instructions(&self.runtime.execution)?;
        self.turn+=1; let root=self.runtime.execution.run_root.join(format!("turn-{}",self.turn)); std::fs::create_dir(&root).map_err(|e|ToolError::io(root.display(),e))?;
        for n in ["agent","control","craft"] { std::fs::create_dir(root.join(n)).map_err(|e|ToolError::io(root.display(),e))?; }
        let profile=provider::load(self.runtime.execution.provider_manifest.as_ref().ok_or_else(||refusal("provider-manifest","Codex profile required"))?,&self.policy,&self.runtime.execution.credential_env_keys,false,0)?;
        let session_dir=self.runtime.execution.run_root.join("threads"); std::fs::create_dir_all(&session_dir).map_err(|e|ToolError::io(session_dir.display(),e))?;
        let receipt_path=session_dir.join(format!("turn-{}.json",self.turn)); let marker=root.join("control/cancel.json");
        let identity=CancelIdentity{run_id:self.policy.owner_id.clone(),turn_id:new_id(),generation:self.turn,token:new_id()};
        let generation = identity.generation;
        let mcp=McpCommand{command:self.runtime.executable.display().to_string(),args:vec!["mcp".into(),"--policy".into(),self.runtime.execution.policy.display().to_string(),"--sha256".into(),self.runtime.execution.policy_sha256.clone(),"--workspace".into(),self.runtime.execution.workspace.display().to_string(),"--config-root".into(),root.join("craft").display().to_string()],notes:None};
        write_json(&root.join("agent/mcp.json"),&json!({"mcpServers":{"craft":{"command":mcp.command,"args":mcp.args,"exposure":"direct","enabled":true}},"native_tools":[]}))?;
        let codex_home = provider::codex_home()?;
        let config_inputs = provider::freeze_config_inputs(&self.policy.app_root, &codex_home)?;
        let disabled_mcp_names = provider::ambient_mcp_names(&self.policy.app_root, &codex_home)?;
        let mut codex = self.runtime.codex.clone();
        codex.program = provider::cli_path()?;
        codex.argv = provider::build_startup_argv(&profile, &disabled_mcp_names)?;
        codex.sha256 = profile.runtime.cli_sha256.clone();
        codex.version = profile.runtime.version.clone();
        codex.mode = craft_codex_bridge::config::CODEX_MODE.into();
        let mut config=Config{contract_version:1,model_provider:None,expected_provider:self.policy.model.expected.provider.clone(),model:self.policy.model.expected.model.clone(),effort:self.policy.model.expected.effort.clone(),codex,task_cwd:self.policy.app_root.clone(),agent_dir:root.join("agent"),codex_home:codex_home.clone(),bundle_root:self.runtime.execution.run_root.clone(),thread_receipt:receipt_path.clone(),instructions:self.policy.prompt(&format!("{}\n{}",self.runtime.instructions,self.spec.preamble.as_deref().unwrap_or(""))),dynamic_tools:tools(),mcp:BridgeMcp{program:self.runtime.executable.clone(),argv:mcp.args.clone(),expected_tools:craft_codex_bridge::config::BUILDER_TOOLS.iter().map(|s|s.to_string()).collect()},environments:vec![],denied_native_tools:vec!["request_user_input".into()],disabled_mcp_names:disabled_mcp_names.clone(),runtime_profile_id:profile.id.clone(),runtime_profile_sha256:self.runtime.execution.provider_manifest.as_ref().unwrap().sha256.clone(),config_inputs,cancel:Cancel{marker:marker.clone(),identity:identity.clone()},deadlines:Deadlines{input_ms:5000,command_ms:10000,turn_ms:self.policy.max_wall_secs*1000,grace_ms:3000,shutdown_ms:3000,hard_kill_ms:3000}};
        config.validate().map_err(|e|refusal("driver-config",format!("{}: {}",e.code,e.detail)))?; let config_path=root.join("driver.json"); write_json(&config_path,&config)?;
        let mut adapter=self.runtime.adapter.clone(); adapter.config_path=config_path.clone(); let args=adapter.args(&ArgsCx{options:&self.spec.options,prompt:text,preamble:"",mcp:&mcp,resume:None,builder:true,reads_checked:true,question:false});
        let (tx,failure,saved,receipts)=(self.tx.clone(),self.failure.clone(),self.thread.clone(),self.runtime.receipts.clone()); *failure.lock().unwrap_or_else(std::sync::PoisonError::into_inner)=None;
        let (owner_stop,local_stop)=(self.owner_stop.clone(),self.local_stop.clone()); let driver=self.runtime.execution.driver.clone(); let cwd=self.policy.app_root.clone(); let prompt=self.policy.prompt(text); let timeout=Duration::from_secs(self.policy.max_wall_secs+25); let policy_hash=self.runtime.execution.policy_sha256.clone(); let busy=self.busy.clone(); busy.store(true,Ordering::SeqCst);
        let spawned=thread::Builder::new().name("codex-app-server-turn".into()).spawn(move||{
            let parser=Arc::new(Mutex::new(StreamParser::new(Arc::new(adapter)))); let bridge=Arc::new(Mutex::new(BridgeParser::default())); let malformed=Arc::new(AtomicBool::new(false)); let (p2,b2,bad2,tx2)=(parser.clone(),bridge.clone(),malformed.clone(),tx.clone()); let cancel_at=Arc::new(Mutex::new(None::<Instant>)); let at2=cancel_at.clone(); let cancel_error=Arc::new(Mutex::new(None::<String>)); let ce2=cancel_error.clone(); let txerr=tx.clone();
            let result=Process::new(&driver).args(args).cwd(cwd).stdin_bytes(prompt).timeout(timeout).stdout_cap(20*1024*1024).stderr_cap(1024*1024).cancel_when(move||{if owner_stop.is_cancelled()||local_stop.is_cancelled(){let mut at=at2.lock().unwrap_or_else(std::sync::PoisonError::into_inner);if at.is_none(){if let Err(e)=std::fs::write(&marker,serde_json::to_vec(&identity).unwrap_or_default()){*ce2.lock().unwrap_or_else(std::sync::PoisonError::into_inner)=Some(e.to_string());}*at=Some(Instant::now());}return at.as_ref().is_some_and(|t|t.elapsed()>=Duration::from_secs(12));}false}).on_stdout_line(move|line|{match serde_json::from_str::<Value>(line){Ok(v)=>{if b2.lock().unwrap_or_else(std::sync::PoisonError::into_inner).parse(&v).is_err(){bad2.store(true,Ordering::SeqCst);}for e in p2.lock().unwrap_or_else(std::sync::PoisonError::into_inner).line(line){let _=tx2.send(e);}},Err(_)=>bad2.store(true,Ordering::SeqCst)}}).on_stderr_line(move|line|{let _=txerr.send(AgentEvent::Output{text:format!("Codex diagnostic: {} bytes discarded.",line.len())});}).run();
            let p=parser.lock().unwrap_or_else(std::sync::PoisonError::into_inner); let b=bridge.lock().unwrap_or_else(std::sync::PoisonError::into_inner); let exit=result.as_ref().ok().and_then(|o|o.code); let valid=b.successful(exit)&&!malformed.load(Ordering::SeqCst)&&p.failure.is_none()&&result.as_ref().is_ok_and(|o|!o.stdout_truncated&&!o.stderr_truncated)&&cancel_error.lock().unwrap_or_else(std::sync::PoisonError::into_inner).is_none(); if valid{if let Some((id,receipt))=&b.thread{*saved.lock().unwrap_or_else(std::sync::PoisonError::into_inner)=Some((id.clone(),PathBuf::from(receipt["receiptPath"].as_str().unwrap_or(""))))}} if !valid{*failure.lock().unwrap_or_else(std::sync::PoisonError::into_inner)=Some(TurnFailure::new(FailureKind::Configuration));let _=tx.send(event_error(format!("Codex turn failed protocol/exit/cleanup verification; exit {exit:?}")));}
            let completion=b.completion.as_ref(); let receipt=json!({"turn":generation,"driver_exit":exit,"successful":valid,"policy_sha256":policy_hash,"completion":completion_receipt(completion),"malformed_output":malformed.load(Ordering::SeqCst),"cancel_write_failed":cancel_error.lock().unwrap_or_else(std::sync::PoisonError::into_inner).is_some(),"driver_config_sha256":craft_anything_engine::execution_policy::hash_file(&config_path).ok(),"transport_config":config_path}); let receipt=match write_json(&root.join("receipt.json"),&receipt){Ok(())=>receipt,Err(e)=>{*failure.lock().unwrap_or_else(std::sync::PoisonError::into_inner)=Some(TurnFailure::new(FailureKind::Configuration));let _=tx.send(event_error(e));json!({"successful":false,"receipt_write_failed":true})}}; receipts.lock().unwrap_or_else(std::sync::PoisonError::into_inner).push(receipt); busy.store(false,Ordering::SeqCst); let _=tx.send(AgentEvent::TurnDone{backend:BACKEND_ID.into(),input_tokens:p.input_tokens,output_tokens:p.output_tokens,cost_usd:p.cost_usd,cost_is_estimate:true});
        });
        match spawned{Ok(w)=>{self.worker=Some(w);Ok(())},Err(e)=>{self.busy.store(false,Ordering::SeqCst);Err(ToolError::internal(format!("Cannot start Codex transport worker: {e}")))}}
    }
}
impl Conversation for CodexConversation {
    fn send(&mut self,text:&str){if let Err(e)=self.launch(text){*self.failure.lock().unwrap_or_else(std::sync::PoisonError::into_inner)=Some(TurnFailure::new(FailureKind::Configuration));let _=self.tx.send(event_error(e));let _=self.tx.send(AgentEvent::TurnDone{backend:BACKEND_ID.into(),input_tokens:0,output_tokens:0,cost_usd:None,cost_is_estimate:true});}}
    fn poll(&mut self)->Vec<AgentEvent>{self.rx.try_iter().collect()}
    fn session_id(&self)->Option<String>{self.thread.lock().unwrap_or_else(std::sync::PoisonError::into_inner).as_ref().map(|(id,_)|id.clone())}
    fn last_failure(&self)->Option<TurnFailure>{*self.failure.lock().unwrap_or_else(std::sync::PoisonError::into_inner)}
    fn answer_consent(&mut self,_:&str,_:bool){self.local_stop.cancel()}
    fn stop(&mut self){self.local_stop.cancel()}
    fn is_busy(&self)->bool{self.busy.load(Ordering::SeqCst)}
}
impl Drop for CodexConversation { fn drop(&mut self){self.local_stop.cancel();let started=Instant::now();while self.is_busy()&&started.elapsed()<Duration::from_secs(18){thread::sleep(Duration::from_millis(10));}if self.worker.as_ref().is_some_and(|w|w.is_finished()){if let Some(w)=self.worker.take(){let _=w.join();}}} }
