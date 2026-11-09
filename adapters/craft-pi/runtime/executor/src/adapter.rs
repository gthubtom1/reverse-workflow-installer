use craft_anything_ai::cli_agents::{AgentAdapter, ArgsCx, StreamParser};
use craft_anything_ai::{AgentEvent, BackendOptions, FailureKind, TurnFailure};
use craft_anything_engine::execution_policy::refusal;
use craft_anything_evidence::ToolError;
use craft_pi_bridge::parser::{AdapterEvent, BridgeParser};
use serde_json::Value;
use std::{
    collections::HashMap,
    path::{Path, PathBuf},
    sync::{
        Arc, Mutex,
        atomic::{AtomicBool, Ordering},
    },
};

/// Public Craft adapter; the policy runtime supplies one explicit owned config per turn.
#[derive(Clone, Debug)]
pub struct PiAdapter {
    pub config_path: PathBuf,
    pub sessions: Arc<Mutex<HashMap<String, (PathBuf, PathBuf)>>>,
    pub text_streamed: Arc<AtomicBool>,
}
impl PiAdapter {
    pub fn new(config_path: PathBuf) -> Self {
        Self {
            config_path,
            sessions: Default::default(),
            text_streamed: Arc::new(AtomicBool::new(false)),
        }
    }
}
impl AgentAdapter for PiAdapter {
    fn ids(&self) -> &'static [&'static str] {
        &["pi"]
    }
    fn args(&self, _: &ArgsCx) -> Vec<String> {
        vec!["--config".into(), self.config_path.display().to_string()]
    }
    fn plain_fallback(&self) -> bool {
        false
    }
    fn resumes(&self) -> bool {
        true
    }
    fn prompt_on_stdin(&self) -> bool {
        true
    }
    fn folder_var(&self) -> Option<&'static str> {
        Some("PI_CODING_AGENT_DIR")
    }
    fn check_native_options(
        &self,
        o: &BackendOptions,
        cwd: Option<&Path>,
    ) -> Result<(), ToolError> {
        if !o.args.is_empty() || o.acp == Some(true) || cwd.is_none() {
            return Err(refusal(
                "unsupported",
                "Pi requires local explicit driver/config without extra args or ACP.",
            ));
        }
        Ok(())
    }
    fn session_file(&self, id: &str) -> Option<PathBuf> {
        let (path, config_path) = self
            .sessions
            .lock()
            .unwrap_or_else(std::sync::PoisonError::into_inner)
            .get(id)
            .cloned()?;
        let config = craft_pi_bridge::config::Config::load(&config_path).ok()?;
        craft_pi_bridge::session::validate_file(&path, Some(id), &config).ok()?;
        Some(path)
    }
    fn parse(&self, p: &mut StreamParser, v: &Value) -> Vec<AgentEvent> {
        // BridgeParser validates event shapes; protocol/exit/completion conjunction is checked
        // independently by PiConversation at the process boundary, before Craft sees TurnDone.
        if v["type"] == "bridge_stderr" {
            let count = v["bytes"].as_array().map_or(0, Vec::len);
            return vec![AgentEvent::Output {
                text: format!("Pi diagnostic chunk: {count} bytes discarded."),
            }];
        }
        match BridgeParser::default().parse(v) {
            Ok(events) => events
                .into_iter()
                .filter_map(|event| match event {
                    AdapterEvent::Session {
                        session_id,
                        session_file,
                    } => {
                        p.session_id = Some(session_id.clone());
                        p.run_session = Some(session_id.clone());
                        self.sessions
                            .lock()
                            .unwrap_or_else(std::sync::PoisonError::into_inner)
                            .insert(session_id, (session_file.into(), self.config_path.clone()));
                        None
                    }
                    AdapterEvent::TextDelta(text) => {
                        self.text_streamed.store(true, Ordering::SeqCst);
                        Some(AgentEvent::TextDelta { text })
                    }
                    AdapterEvent::ToolStarted { id, name, args } => {
                        Some(p.started(&id, &name, args))
                    }
                    AdapterEvent::ToolFinished {
                        id,
                        result,
                        is_error,
                    } => Some(p.finished(&id, !is_error, &result.to_string())),
                    AdapterEvent::Failure(f) => {
                        p.failure = Some(TurnFailure::new(FailureKind::Configuration));
                        Some(AgentEvent::Error {
                            message: format!(
                                "Pi bridge failure code: {}",
                                f["code"].as_str().unwrap_or("unknown")
                            ),
                            remediation: None,
                            log: None,
                        })
                    }
                    AdapterEvent::Completed(c) => {
                        p.saw_result = true;
                        let usage = &c["usage"];
                        p.input_tokens = usage["input"].as_u64().unwrap_or(0)
                            + usage["cache_read"].as_u64().unwrap_or(0)
                            + usage["cache_write"].as_u64().unwrap_or(0);
                        p.output_tokens = usage["output"].as_u64().unwrap_or(0);
                        p.cost_usd = usage["estimated_cost"].as_f64();
                        if !self.text_streamed.load(Ordering::SeqCst) {
                            let text = c["finalMessage"]["content"]
                                .as_array()
                                .into_iter()
                                .flatten()
                                .filter(|b| b["type"] == "text")
                                .filter_map(|b| b["text"].as_str())
                                .collect::<Vec<_>>()
                                .join("\n");
                            if !text.is_empty() {
                                return Some(AgentEvent::TextDelta { text });
                            }
                        }
                        None
                    }
                })
                .collect(),
            Err(e) => {
                p.failure = Some(TurnFailure::new(FailureKind::Configuration));
                vec![AgentEvent::Error {
                    message: format!("{}: {}", e.code, e.detail),
                    remediation: None,
                    log: None,
                }]
            }
        }
    }
}
