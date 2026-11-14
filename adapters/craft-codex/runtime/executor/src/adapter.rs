use craft_anything_ai::cli_agents::{AgentAdapter, ArgsCx, StreamParser};
use craft_anything_ai::{AgentEvent, BackendOptions, FailureKind, TurnFailure};
use craft_anything_engine::execution_policy::refusal;
use craft_anything_evidence::ToolError;
use craft_codex_bridge::{config::Config, parser::{AdapterEvent, BridgeParser}};
use serde_json::Value;
use std::{path::{Path, PathBuf}, sync::{Arc, Mutex}};

/// Public Craft adapter for one explicit Codex app-server driver config per turn.
#[derive(Clone, Debug)]
pub struct CodexAdapter {
    pub config_path: PathBuf,
    pub configs: Arc<Mutex<std::collections::HashMap<String, (PathBuf, PathBuf)>>>,
}
impl CodexAdapter { pub fn new(path: PathBuf) -> Self { Self { config_path:path, configs:Default::default() } } }
impl AgentAdapter for CodexAdapter {
    fn ids(&self) -> &'static [&'static str] { &["codex"] }
    fn args(&self, _: &ArgsCx) -> Vec<String> { vec!["--config".into(), self.config_path.display().to_string()] }
    fn plain_fallback(&self) -> bool { false }
    fn resumes(&self) -> bool { false }
    fn prompt_on_stdin(&self) -> bool { true }
    fn folder_var(&self) -> Option<&'static str> { Some("CODEX_HOME") }
    fn check_native_options(&self, o: &BackendOptions, cwd: Option<&Path>) -> Result<(), ToolError> {
        if !o.args.is_empty() || o.acp == Some(true) || cwd.is_none() { return Err(refusal("unsupported", "Codex requires local explicit app-server driver without extra args or ACP.")); }
        Ok(())
    }
    fn session_file(&self, id: &str) -> Option<PathBuf> {
        self.configs.lock().ok()?.get(id).and_then(|(path, config)| {
            let c = Config::load(config).ok()?; let _ = c;
            let receipt = craft_codex_bridge::session::read(path).ok()?;
            (receipt.thread_id == id && receipt.host_created).then_some(path.clone())
        })
    }
    fn parse(&self, p: &mut StreamParser, v: &Value) -> Vec<AgentEvent> {
        let mut bridge = BridgeParser::default();
        let events = match bridge.parse(v) { Ok(e) => e, Err(e) => { p.failure=Some(TurnFailure::new(FailureKind::Configuration)); return vec![AgentEvent::Error{message:format!("{}: {}",e.code,e.detail), remediation:None, log:None}]; } };
        events.into_iter().filter_map(|event| match event {
            AdapterEvent::Thread{id, receipt} => { p.session_id=Some(id.clone()); p.run_session=Some(id.clone()); if let Some(path)=receipt["receiptPath"].as_str() { self.configs.lock().ok()?.insert(id,(PathBuf::from(path),self.config_path.clone())); } None }
            AdapterEvent::TextDelta{bytes} => Some(AgentEvent::Output{text:format!("Codex progress: {bytes} bytes discarded.")}),
            AdapterEvent::ToolStarted{id,name} => Some(p.started(&id,&name,Value::Null)),
            AdapterEvent::ToolFinished{id,ok} => Some(p.finished(&id,ok,"Codex bounded tool completed")),
            AdapterEvent::Failure(f) => { p.failure=Some(TurnFailure::new(FailureKind::Configuration)); Some(AgentEvent::Error{message:format!("Codex bridge failure code: {}",f["code"].as_str().unwrap_or("unknown")),remediation:None,log:None}) }
            AdapterEvent::Completed(c) => { p.saw_result=true; let u=&c["usage"]; p.input_tokens=u["input"].as_u64().unwrap_or(0); p.output_tokens=u["output"].as_u64().unwrap_or(0); p.cost_usd=u["estimated_cost"].as_f64(); None }
        }).collect()
    }
}
