//! Craft-free adapter core. Integration supplies the actual Craft AgentAdapter impl.
use crate::{
    Failure, Result,
    config::{Config, canonical},
    parser::BridgeParser,
};
use std::path::{Path, PathBuf};
#[derive(Debug)]
pub struct Launch {
    pub program: PathBuf,
    pub args: Vec<String>,
    pub stdin_text: String,
    pub cwd: PathBuf,
    pub agent_dir: PathBuf,
}
pub struct PiRpcAdapter {
    pub driver: PathBuf,
    pub config_path: PathBuf,
    pub config: Config,
}
impl PiRpcAdapter {
    pub fn load(driver: &Path, config_path: &Path) -> Result<Self> {
        Ok(Self {
            driver: canonical(driver)?,
            config_path: canonical(config_path)?,
            config: Config::load(config_path)?,
        })
    }
    pub fn invocation(
        &self,
        task: &str,
        ssh: Option<&str>,
        extra_args: &[String],
        question: bool,
    ) -> Result<Launch> {
        if ssh.is_some() || !extra_args.is_empty() || question {
            return Err(Failure::new(
                "unsupported_options",
                "SSH, extra args and question mode are unsupported",
            ));
        }
        Ok(Launch {
            program: self.driver.clone(),
            args: vec!["--config".into(), self.config_path.to_string_lossy().into()],
            stdin_text: task.into(),
            cwd: self.config.task_cwd.clone(),
            agent_dir: self.config.agent_dir.clone(),
        })
    }
    pub fn plain_fallback(&self) -> bool {
        false
    }
    pub fn prompt_on_stdin(&self) -> bool {
        true
    }
    pub fn folder_var(&self) -> &'static str {
        "PI_CODING_AGENT_DIR"
    }
    /// Exact verified file, never a UUID-derived or latest-session lookup.
    pub fn session_file(&self, parser: &BridgeParser) -> Result<PathBuf> {
        let (id, path) = parser
            .session
            .as_ref()
            .ok_or_else(|| Failure::new("session_missing", "no verified bridge_session"))?;
        let path = canonical(Path::new(path))?;
        if !path.starts_with(&self.config.session_dir) {
            return Err(Failure::new(
                "session_mismatch",
                "outside owned session root",
            ));
        }
        crate::session::validate_file(&path, Some(id), &self.config)?;
        Ok(path)
    }
}
