//! Craft-free launch and event adapter for the Codex driver.
use crate::{Failure, Result, config::Config, parser::{AdapterEvent, BridgeParser}};
use std::path::{Path, PathBuf};
#[derive(Debug, Clone)]
pub struct Launch { pub program: PathBuf, pub args: Vec<String>, pub stdin_text: String, pub cwd: PathBuf, pub agent_dir: PathBuf }
#[derive(Debug, Clone)]
pub struct CodexAppServerAdapter { pub driver: PathBuf, pub config_path: PathBuf, pub config: Config }
impl CodexAppServerAdapter {
    pub fn load(driver: &Path, config_path: &Path) -> Result<Self> { Ok(Self { driver: crate::config::canonical(driver)?, config_path: crate::config::canonical(config_path)?, config: Config::load(config_path)? }) }
    pub fn invocation(&self, task: &str, ssh: Option<&str>, extra_args: &[String], question: bool) -> Result<Launch> {
        if ssh.is_some() || !extra_args.is_empty() || question { return Err(Failure::new("unsupported_options", "SSH, extra args and question mode are unsupported")); }
        Ok(Launch { program: self.driver.clone(), args: vec!["--config".into(), self.config_path.to_string_lossy().into()], stdin_text: task.into(), cwd: self.config.task_cwd.clone(), agent_dir: self.config.agent_dir.clone() })
    }
    pub fn plain_fallback(&self) -> bool { false }
    pub fn prompt_on_stdin(&self) -> bool { true }
    pub fn folder_var(&self) -> &'static str { "CODEX_HOME" }
    pub fn session_file(&self, parser: &BridgeParser) -> Result<PathBuf> {
        let Some((id, receipt)) = &parser.thread else { return Err(Failure::new("thread_missing", "no verified bridge_thread")); };
        if receipt["hostCreated"] != true || receipt["threadId"] != *id { return Err(Failure::new("thread_mismatch", "thread receipt is not host-created")); }
        Ok(PathBuf::from(receipt["receiptPath"].as_str().ok_or_else(|| Failure::new("thread_missing", "receipt path missing"))?))
    }
    pub fn map(&self, parser: &mut crate::parser::BridgeParser, value: &serde_json::Value) -> Result<Vec<AdapterEvent>> { parser.parse(value) }
}
