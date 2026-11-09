use crate::{BACKEND_ID, ExecutionConfig, PERMISSION, adapter::PiAdapter, new_id, write_json};
use craft_anything_ai::cli_agents::{AgentAdapter, ArgsCx, CliSpec, McpCommand, StreamParser};
use craft_anything_ai::rebuild::policy::PolicyRuntime;
use craft_anything_ai::{AgentEvent, Conversation, FailureKind, TurnFailure};
use craft_anything_engine::{
    CancelToken,
    execution_policy::{ExecutionPolicy, refusal},
};
use craft_anything_evidence::ToolError;
use craft_anything_platform::Process;
use craft_pi_bridge::{
    config::{Cancel, CancelIdentity, Config, Deadlines, PiCommand, Selection},
    parser::BridgeParser,
};
use serde_json::{Value, json};
use std::{
    path::PathBuf,
    sync::{
        Arc, Mutex,
        atomic::{AtomicBool, Ordering},
        mpsc,
    },
    thread::JoinHandle,
    time::{Duration, Instant},
};

#[derive(Debug, Clone)]
pub struct PiRuntime {
    pub execution: ExecutionConfig,
    pub pi: PiCommand,
    pub executable: PathBuf,
    pub adapter: PiAdapter,
    pub receipts: Arc<Mutex<Vec<Value>>>,
    pub instructions: String,
}
impl PolicyRuntime for PiRuntime {
    fn backend_id(&self) -> &str {
        BACKEND_ID
    }
    fn permission_contract(&self) -> &str {
        PERMISSION
    }
    fn conversation(
        &self,
        policy: Arc<ExecutionPolicy>,
        spec: CliSpec,
        stop: CancelToken,
    ) -> Result<Box<dyn Conversation>, ToolError> {
        if spec.config.model != "pi"
            || spec.config.ssh_host.is_some()
            || spec.question
            || spec.resume.is_some()
            || spec.options.cli_model.as_deref() != Some(policy.model.expected.model.as_str())
        {
            return Err(refusal(
                "unsupported",
                "Only fresh local Pi Builder conversations are qualified; cross-run history and questions are unsupported.",
            ));
        }
        self.adapter
            .check_native_options(&spec.options, spec.project.as_deref())?;
        policy.revalidate_builder_inputs()?;
        if serde_json::to_value(self.execution.policy()?).ok()
            != serde_json::to_value(policy.as_ref()).ok()
        {
            return Err(refusal(
                "identity-mismatch",
                "Runtime policy differs from Craft owner policy.",
            ));
        }
        let (tx, rx) = mpsc::channel();
        Ok(Box::new(PiConversation {
            runtime: self.clone(),
            policy,
            spec,
            owner_stop: stop,
            local_stop: CancelToken::default(),
            tx,
            rx,
            worker: None,
            busy: Arc::new(AtomicBool::new(false)),
            session: Arc::new(Mutex::new(None)),
            failure: Arc::new(Mutex::new(None)),
            turn: 0,
        }))
    }
}
struct PiConversation {
    runtime: PiRuntime,
    policy: Arc<ExecutionPolicy>,
    spec: CliSpec,
    owner_stop: CancelToken,
    local_stop: CancelToken,
    tx: mpsc::Sender<AgentEvent>,
    rx: mpsc::Receiver<AgentEvent>,
    worker: Option<JoinHandle<()>>,
    busy: Arc<AtomicBool>,
    session: Arc<Mutex<Option<(String, PathBuf)>>>,
    failure: Arc<Mutex<Option<TurnFailure>>>,
    turn: u64,
}
fn completion_receipt(value: Option<&Value>) -> Value {
    let Some(v) = value else { return Value::Null };
    json!({"success": v["success"], "cleanup": v["cleanup"], "childExit": v["childExit"], "settled": v["settled"],
        "usage": v["usage"], "nestedUsage": v["nestedUsage"], "cancelAcknowledged": v["cancelAcknowledged"],
        "queueCleared": v["queueCleared"], "abortIdle": v["abortIdle"],
        "actual_model": {"provider": v["finalMessage"]["provider"], "model": v["finalMessage"]["model"],
            "thinkingLevel": v["finalMessage"]["thinkingLevel"], "providerThinkingLevel": v["finalMessage"]["providerThinkingLevel"],
            "responseModel": v["finalMessage"]["responseModel"], "stopReason": v["finalMessage"]["stopReason"]}})
}
/// Accept only the complete before-child failure envelope emitted by the owned driver.
/// Missing fields, any Pi activity, duplicate/out-of-order terminal records or nonzero usage
/// remain unknown; a cleanup status string alone is never sufficient.
fn proved_not_started(bridge: &BridgeParser, exit: Option<i32>, records: &[String]) -> bool {
    let (Some(completion), Some(failure)) = (&bridge.completion, &bridge.failure) else {
        return false;
    };
    let cleanup = &completion["cleanup"];
    let zero_usage = |usage: &Value| {
        [
            "input",
            "output",
            "cache_read",
            "cache_write",
            "total_tokens",
        ]
        .iter()
        .all(|key| usage[*key].as_u64() == Some(0))
            && usage["estimated_cost"].as_f64() == Some(0.0)
    };
    exit == Some(1)
        && records == ["bridge_failure", "bridge_complete"]
        && bridge.session.is_none()
        && failure["type"] == "bridge_failure"
        && failure["code"]
            .as_str()
            .is_some_and(|code| !code.is_empty())
        && failure["detail"].is_string()
        && completion["type"] == "bridge_complete"
        && completion["success"] == false
        && completion["settled"] == false
        && completion.get("childExit").is_some_and(Value::is_null)
        && completion.get("finalMessage").is_some_and(Value::is_null)
        && cleanup["status"] == "not_started"
        && cleanup["scope"] == "none"
        && cleanup["root_exited"] == true
        && cleanup["members_empty"] == true
        && cleanup["hard_terminated"] == false
        && cleanup["detail"].is_string()
        && zero_usage(&completion["usage"])
        && zero_usage(&completion["nestedUsage"])
        && ["cancelAcknowledged", "queueCleared", "abortIdle"]
            .iter()
            .all(|key| completion[*key] == false)
}

/// The owner also requires its worker join and descendant observation before releasing a lease.
pub(crate) fn turn_cleanup_closed(turn: &Value) -> bool {
    if !turn["driver_exit"].is_i64() {
        return false;
    }
    let cleanup = &turn["completion"]["cleanup"];
    if cleanup["status"] == "verified" {
        return matches!(
            cleanup["scope"].as_str(),
            Some("windows_job" | "windows_suspended_child" | "unix_process_group")
        ) && cleanup["root_exited"] == true
            && cleanup["members_empty"] == true;
    }
    turn["not_started_proved"] == true
        && turn["driver_exit"] == 1
        && turn["successful"] == false
        && turn["failure_code"]
            .as_str()
            .is_some_and(|code| !code.is_empty())
        && cleanup["status"] == "not_started"
        && cleanup["scope"] == "none"
        && cleanup["root_exited"] == true
        && cleanup["members_empty"] == true
        && cleanup["hard_terminated"] == false
}

fn event_error(message: impl ToString) -> AgentEvent {
    AgentEvent::Error {
        message: message.to_string(),
        remediation: None,
        log: None,
    }
}
impl PiConversation {
    /// Preserve a driver/config hash without recording credentials.
    pub fn config_hash(path: &std::path::Path) -> Option<String> {
        craft_anything_engine::execution_policy::hash_file(path).ok()
    }
    fn launch(&mut self, text: &str) -> Result<(), ToolError> {
        if self.is_busy() {
            return Err(refusal("owner-conflict", "A Pi turn is already running."));
        }
        if let Some(w) = self.worker.take() {
            w.join()
                .map_err(|_| ToolError::internal("Pi transport panicked."))?;
        }
        self.owner_stop.check()?;
        self.policy.revalidate_builder_inputs()?;
        // The original config and instructions stay immutable through all refinement turns.
        self.runtime.execution.policy()?;
        if craft_anything_engine::execution_policy::hash_file(&self.runtime.execution.driver)?
            != self.runtime.execution.driver_sha256
        {
            return Err(refusal("identity-mismatch", "Built RPC driver changed."));
        }
        crate::read_instructions(&self.runtime.execution)?;
        self.turn += 1;
        let root = self
            .runtime
            .execution
            .run_root
            .join(format!("turn-{}", self.turn));
        std::fs::create_dir(&root).map_err(|e| ToolError::io(root.display(), e))?;
        for name in ["agent", "control", "craft"] {
            std::fs::create_dir(root.join(name)).map_err(|e| ToolError::io(root.display(), e))?;
        }
        if let Some(reference) = &self.runtime.execution.provider_manifest {
            let definition = crate::provider::validate(
                reference,
                &self.policy,
                &self.runtime.execution.credential_env_keys,
            )?;
            write_json(&root.join("agent/models.json"), &definition)?;
        }
        let session_dir = self.runtime.execution.run_root.join("sessions");
        let marker = root.join("control/cancel.json");
        let identity = CancelIdentity {
            run_id: self.policy.owner_id.clone(),
            turn_id: new_id(),
            generation: self.turn,
            token: new_id(),
        };
        // Replace Craft's generic MCP command with the same executable's bounded entry. Never
        // pass a policy flag to the generic upstream CLI: its process has no policy loader.
        let mcp = McpCommand {
            command: self.runtime.executable.display().to_string(),
            args: vec![
                "mcp".into(),
                "--policy".into(),
                self.runtime.execution.policy.display().to_string(),
                "--sha256".into(),
                self.runtime.execution.policy_sha256.clone(),
                "--workspace".into(),
                self.runtime.execution.workspace.display().to_string(),
                "--config-root".into(),
                root.join("craft").display().to_string(),
            ],
            notes: None,
        };
        write_json(
            &root.join("agent/mcp.json"),
            &json!({"autoEnableCodemode": false, "mcpServers": {"craft": {
                "command": mcp.command, "args": mcp.args, "exposure": "direct", "enabled": true
            }}}),
        )?;
        let session = self
            .session
            .lock()
            .unwrap_or_else(std::sync::PoisonError::into_inner)
            .clone();
        let expected = &self.policy.model.expected;
        let mut config = Config {
            provider: expected.provider.clone(),
            model: expected.model.clone(),
            thinking: expected.effort.clone(),
            public_selection: Some(Selection {
                provider: expected.provider.clone(),
                model: expected.model.clone(),
                thinking: expected.effort.clone(),
            }),
            pi: self.runtime.pi.clone(),
            task_cwd: self.policy.app_root.clone(),
            agent_dir: root.join("agent"),
            session_dir,
            session_path: session.map(|(_, p)| p),
            instructions: self.policy.prompt(&format!(
                "{}\n{}",
                self.runtime.instructions,
                self.spec.preamble.as_deref().unwrap_or("")
            )),
            selected_mcp_tools: craft_anything_engine::execution_policy::BUILDER_TOOLS
                .iter()
                .map(|id| format!("mcp__craft__{id}"))
                .collect(),
            credential_env_keys: self.runtime.execution.credential_env_keys.clone(),
            cancel: Cancel {
                marker: marker.clone(),
                identity: identity.clone(),
            },
            deadlines: Deadlines {
                input_ms: 5000,
                command_ms: 10000,
                turn_ms: self.policy.max_wall_secs * 1000,
                grace_ms: 3000,
                shutdown_ms: 3000,
                hard_kill_ms: 3000,
            },
        };
        config
            .validate()
            .map_err(|e| refusal("driver-config", format!("{}: {}", e.code, e.detail)))?;
        let config_path = root.join("driver.json");
        write_json(&config_path, &config)?;
        let mut adapter = self.runtime.adapter.clone();
        adapter.config_path = config_path;
        adapter.text_streamed.store(false, Ordering::SeqCst);
        let args = adapter.args(&ArgsCx {
            options: &self.spec.options,
            prompt: text,
            preamble: "",
            mcp: &mcp,
            resume: None,
            builder: true,
            reads_checked: true,
            question: false,
        });
        let (tx, failure, saved_session, receipts) = (
            self.tx.clone(),
            self.failure.clone(),
            self.session.clone(),
            self.runtime.receipts.clone(),
        );
        *failure
            .lock()
            .unwrap_or_else(std::sync::PoisonError::into_inner) = None;
        let (owner_stop, local_stop) = (self.owner_stop.clone(), self.local_stop.clone());
        let driver = self.runtime.execution.driver.clone();
        let cwd = self.policy.app_root.clone();
        let prompt = self.policy.prompt(text);
        let timeout = Duration::from_secs(self.policy.max_wall_secs + 25);
        let policy_hash = self.runtime.execution.policy_sha256.clone();
        let busy = self.busy.clone();
        busy.store(true, Ordering::SeqCst);
        let spawned = std::thread::Builder::new().name("pi-rpc-turn".into()).spawn(move || {
            let parser = Arc::new(Mutex::new(StreamParser::new(Arc::new(adapter))));
            let bridge = Arc::new(Mutex::new(BridgeParser::default()));
            let malformed = Arc::new(Mutex::new(false));
            // Only retain bounded type names; never duplicate model/tool payloads here.
            let records: Arc<Mutex<Vec<String>>> = Default::default();
            let records2 = records.clone();
            let (p2, b2, bad2, tx2) = (parser.clone(), bridge.clone(), malformed.clone(), tx.clone());
            let cancel_at: Arc<Mutex<Option<Instant>>> = Default::default(); let at2 = cancel_at.clone();
            let cancel_error: Arc<Mutex<Option<String>>> = Default::default(); let ce2 = cancel_error.clone();
            let txerr = tx.clone();
            let result = Process::new(&driver).args(args).cwd(cwd).stdin_bytes(prompt).timeout(timeout)
                .stdout_cap(20 * 1024 * 1024).stderr_cap(1024 * 1024)
                .cancel_when(move || {
                    if owner_stop.is_cancelled() || local_stop.is_cancelled() {
                        let mut at = at2.lock().unwrap_or_else(std::sync::PoisonError::into_inner);
                        if at.is_none() {
                            if let Err(e) = write_json(&marker, &identity) { *ce2.lock().unwrap_or_else(std::sync::PoisonError::into_inner) = Some(e.to_string()); }
                            *at = Some(Instant::now());
                        }
                        return at.as_ref().is_some_and(|t| t.elapsed() >= Duration::from_secs(12));
                    }
                    false
                })
                .on_stdout_line(move |line| {
                    match serde_json::from_str::<Value>(line) {
                        Ok(v) => {
                            let mut types = records2.lock().unwrap_or_else(std::sync::PoisonError::into_inner);
                            if types.len() < 3 { types.push(v["type"].as_str().unwrap_or("").to_owned()); }
                            drop(types);
                            if b2.lock().unwrap_or_else(std::sync::PoisonError::into_inner).parse(&v).is_err() { *bad2.lock().unwrap_or_else(std::sync::PoisonError::into_inner) = true; }
                            for e in p2.lock().unwrap_or_else(std::sync::PoisonError::into_inner).line(line) { let _ = tx2.send(e); }
                        }
                        Err(_) => { *bad2.lock().unwrap_or_else(std::sync::PoisonError::into_inner) = true; }
                    }
                })
                .on_stderr_line(move |line| { let _ = txerr.send(AgentEvent::Output { text: format!("Driver diagnostic: {} bytes discarded.", line.len()) }); }).run();
            let p = parser.lock().unwrap_or_else(std::sync::PoisonError::into_inner); let b = bridge.lock().unwrap_or_else(std::sync::PoisonError::into_inner);
            let exit = result.as_ref().ok().and_then(|o| o.code);
            let valid = b.successful(exit) && !*malformed.lock().unwrap_or_else(std::sync::PoisonError::into_inner) && p.failure.is_none() && cancel_error.lock().unwrap_or_else(std::sync::PoisonError::into_inner).is_none()
                && result.as_ref().is_ok_and(|o| !o.stdout_truncated && !o.stderr_truncated);
            if valid { if let Some((id, path)) = &b.session { *saved_session.lock().unwrap_or_else(std::sync::PoisonError::into_inner) = Some((id.clone(), path.into())); } }
            if !valid {
                *failure.lock().unwrap_or_else(std::sync::PoisonError::into_inner) = Some(TurnFailure::new(FailureKind::Configuration));
                let _ = tx.send(event_error(format!("Pi turn failed protocol/exit/cleanup verification; exit {exit:?}; {:?}", result.as_ref().err())));
            }
            let output_intact = !*malformed.lock().unwrap_or_else(std::sync::PoisonError::into_inner)
                && cancel_error.lock().unwrap_or_else(std::sync::PoisonError::into_inner).is_none()
                && result.as_ref().is_ok_and(|out| !out.stdout_truncated && !out.stderr_truncated);
            let not_started_proved = output_intact && proved_not_started(&b, exit, &records.lock().unwrap_or_else(std::sync::PoisonError::into_inner));
            let receipt = json!({"turn": config.cancel.identity.generation, "driver_exit": exit, "successful": valid, "not_started_proved": not_started_proved,
                "policy_sha256": policy_hash, "completion": completion_receipt(b.completion.as_ref()), "failure_code": b.failure.as_ref().and_then(|v|v["code"].as_str()), "malformed_output": *malformed.lock().unwrap_or_else(std::sync::PoisonError::into_inner),
                "cancel_write_failed": cancel_error.lock().unwrap_or_else(std::sync::PoisonError::into_inner).is_some(),
                "process_error_code": result.as_ref().err().map(|e|format!("{:?}",e.code)),
                "driver_config_sha256": Self::config_hash(&root.join("driver.json")), "transport_config": root.join("driver.json")});
            // Policy identity is separately frozen in the MCP command; preserve raw bridge facts.
            let receipt = match write_json(&root.join("receipt.json"), &receipt) {
                Ok(()) => receipt,
                Err(e) => { *failure.lock().unwrap_or_else(std::sync::PoisonError::into_inner) = Some(TurnFailure::new(FailureKind::Configuration)); let _ = tx.send(event_error(e)); json!({"successful": false, "receipt_write_failed": true}) }
            };
            receipts.lock().unwrap_or_else(std::sync::PoisonError::into_inner).push(receipt);
            busy.store(false, Ordering::SeqCst);
            let _ = tx.send(AgentEvent::TurnDone { backend: BACKEND_ID.into(), input_tokens: p.input_tokens,
                output_tokens: p.output_tokens, cost_usd: p.cost_usd, cost_is_estimate: true });
        });
        match spawned {
            Ok(worker) => self.worker = Some(worker),
            Err(e) => {
                self.busy.store(false, Ordering::SeqCst);
                return Err(ToolError::internal(format!(
                    "Cannot start Pi transport worker: {e}"
                )));
            }
        }
        Ok(())
    }
}
impl Conversation for PiConversation {
    fn send(&mut self, text: &str) {
        if let Err(e) = self.launch(text) {
            *self
                .failure
                .lock()
                .unwrap_or_else(std::sync::PoisonError::into_inner) =
                Some(TurnFailure::new(FailureKind::Configuration));
            let _ = self.tx.send(event_error(e));
            let _ = self.tx.send(AgentEvent::TurnDone {
                backend: BACKEND_ID.into(),
                input_tokens: 0,
                output_tokens: 0,
                cost_usd: None,
                cost_is_estimate: true,
            });
        }
    }
    fn poll(&mut self) -> Vec<AgentEvent> {
        self.rx.try_iter().collect()
    }
    fn session_id(&self) -> Option<String> {
        self.session
            .lock()
            .unwrap_or_else(std::sync::PoisonError::into_inner)
            .as_ref()
            .map(|(id, _)| id.clone())
    }
    fn last_failure(&self) -> Option<TurnFailure> {
        *self
            .failure
            .lock()
            .unwrap_or_else(std::sync::PoisonError::into_inner)
    }
    fn answer_consent(&mut self, _: &str, _: bool) {
        self.local_stop.cancel();
    }
    fn stop(&mut self) {
        self.local_stop.cancel();
    }
    fn is_busy(&self) -> bool {
        self.busy.load(Ordering::SeqCst)
    }
}
impl Drop for PiConversation {
    fn drop(&mut self) {
        self.local_stop.cancel();
        let started = Instant::now();
        while self.is_busy() && started.elapsed() < Duration::from_secs(18) {
            std::thread::sleep(Duration::from_millis(10));
        }
        if self.worker.as_ref().is_some_and(|w| w.is_finished()) {
            if let Some(w) = self.worker.take() {
                let _ = w.join();
            }
        }
        // A detached worker cannot admit replacement: execution keeps its external source lease
        // whenever any receipt/cleanup fact is absent or unverified.
    }
}
