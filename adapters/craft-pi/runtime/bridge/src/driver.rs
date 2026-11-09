use crate::{
    Failure, Result,
    config::{Config, MAX_RECORD, MAX_STREAM, MAX_TASK, native_path},
    framing::Framer,
    parser::{TurnParser, Usage, failure_event},
    process::{Cleanup, Owned, SpawnFailure},
    redaction::{Redactions, StreamRedactor},
    session::{Session, validate_file},
};
use serde::Serialize;
use serde_json::{Value, json};
use std::{
    collections::HashMap,
    io::{Read, Write},
    process::{Command, Stdio},
    sync::mpsc::{self, Receiver, SyncSender},
    thread,
    time::{Duration, Instant},
};
fn ms(n: u64) -> Duration {
    Duration::from_millis(n)
}

#[derive(Debug, Clone, Serialize)]
pub struct Report {
    pub success: bool,
    pub failure: Option<Failure>,
    pub cleanup: Cleanup,
    pub child_exit: Option<i32>,
    pub settled: bool,
    pub final_message: Option<Value>,
    pub usage: Usage,
    pub nested_usage: Usage,
    pub cancel_acknowledged: bool,
    pub queue_cleared: bool,
    pub abort_idle: bool,
}
impl Report {
    fn redact(&mut self, redactions: &Redactions) {
        if let Some(failure) = &mut self.failure {
            // Stable failure codes and protocol fields are never rewritten.
            failure.detail = redactions.failure_detail(failure);
        }
        self.cleanup.detail = redactions.text(&self.cleanup.detail);
        if let Some(message) = &self.final_message {
            match redactions.message(message) {
                Ok(safe) => self.final_message = Some(safe),
                Err(failure) => {
                    self.final_message = None;
                    self.failure = Some(failure);
                    self.success = false;
                }
            }
        }
    }
    fn empty() -> Self {
        Self {
            success: false,
            failure: None,
            cleanup: Cleanup {
                status: "not_started",
                scope: "none",
                root_exited: true,
                members_empty: true,
                hard_terminated: false,
                detail: "child not started".into(),
            },
            child_exit: None,
            settled: false,
            final_message: None,
            usage: Usage::default(),
            nested_usage: Usage::default(),
            cancel_acknowledged: false,
            queue_cleared: false,
            abort_idle: false,
        }
    }
}
// The sink is also bounded: a blocked consumer cannot prevent child teardown.
// A permanently blocked user-provided Write may retain its writer thread. The CLI
// exits the process after run(), while library callers must supply a finite sink.
struct Output {
    tx: SyncSender<(Value, mpsc::Sender<Result<()>>)>,
    timeout: Duration,
    redactions: std::sync::Mutex<Redactions>,
}
impl Output {
    fn new(mut writer: impl Write + Send + 'static, timeout: Duration) -> Self {
        let (tx, rx) = mpsc::sync_channel::<(Value, mpsc::Sender<Result<()>>)>(1);
        thread::spawn(move || {
            while let Ok((v, ack)) = rx.recv() {
                let result = (|| {
                    serde_json::to_writer(&mut writer, &v)?;
                    writer.write_all(b"\n")?;
                    writer.flush()
                })()
                .map_err(|e| Failure::new("output_write_failed", e));
                let failed = result.is_err();
                let _ = ack.send(result);
                if failed {
                    break;
                }
            }
        });
        Self {
            tx,
            timeout,
            redactions: std::sync::Mutex::new(Redactions::default()),
        }
    }
    fn set_redactions(&self, redactions: Redactions) {
        *self.redactions.lock().unwrap() = redactions;
    }
    fn emit(&self, v: Value) -> Result<()> {
        let v = self.redactions.lock().unwrap().outgoing(v)?;
        let (tx, rx) = mpsc::channel();
        self.tx
            .try_send((v, tx))
            .map_err(|e| Failure::new("output_write_failed", e))?;
        rx.recv_timeout(self.timeout)
            .map_err(|e| Failure::new("output_write_failed", e))?
    }
}
enum Input {
    Record(Value),
    Error(Failure),
    Stderr(Vec<u8>),
    Eof(bool),
}
fn readers(
    stdout: impl Read + Send + 'static,
    stderr: impl Read + Send + 'static,
    redactions: Redactions,
) -> Receiver<Input> {
    let (tx, rx) = mpsc::sync_channel(32);
    for (mut stream, is_stdout) in [
        (Box::new(stdout) as Box<dyn Read + Send>, true),
        (Box::new(stderr) as Box<dyn Read + Send>, false),
    ] {
        let tx = tx.clone();
        let redactions = redactions.clone();
        thread::spawn(move || {
            let mut stderr_redactor = StreamRedactor::new(redactions);
            let mut framer = Framer::new(MAX_RECORD, MAX_STREAM);
            let mut buf = [0; 8192];
            let mut total = 0;
            let mut failed = false;
            loop {
                let n = match stream.read(&mut buf) {
                    Ok(0) => break,
                    Ok(n) => n,
                    Err(e) => {
                        let _ = tx.send(Input::Error(Failure::new("pipe_read_failed", e)));
                        break;
                    }
                };
                if failed {
                    continue;
                } // Continue draining after the first limit/protocol failure.
                if is_stdout {
                    match framer.feed(&buf[..n]) {
                        Ok(records) => {
                            for v in records {
                                if tx.send(Input::Record(v)).is_err() {
                                    return;
                                }
                            }
                        }
                        Err(e) => {
                            failed = true;
                            if tx.send(Input::Error(e)).is_err() {
                                return;
                            }
                        }
                    }
                } else {
                    total += n;
                    if total > MAX_STREAM {
                        failed = true;
                        if tx
                            .send(Input::Error(Failure::new(
                                "output_limit",
                                "stderr total exceeded",
                            )))
                            .is_err()
                        {
                            return;
                        }
                    } else {
                        let safe = stderr_redactor.feed(&buf[..n], false);
                        if !safe.is_empty() && tx.send(Input::Stderr(safe)).is_err() {
                            return;
                        }
                    }
                }
            }
            if !is_stdout && !failed {
                let safe = stderr_redactor.feed(&[], true);
                if !safe.is_empty() && tx.send(Input::Stderr(safe)).is_err() {
                    return;
                }
            }
            if is_stdout && !failed {
                if let Err(e) = framer.finish() {
                    let _ = tx.send(Input::Error(e));
                }
            }
            let _ = tx.send(Input::Eof(is_stdout));
        });
    }
    rx
}
enum WriteRequest {
    Record(Value, mpsc::Sender<Result<()>>),
    Close(mpsc::Sender<Result<()>>),
}
struct PipeWriter {
    tx: SyncSender<WriteRequest>,
    closed: bool,
}
impl PipeWriter {
    fn new(mut pipe: impl Write + Send + 'static) -> Self {
        let (tx, rx) = mpsc::sync_channel(1);
        thread::spawn(move || {
            while let Ok(req) = rx.recv() {
                match req {
                    WriteRequest::Record(v, ack) => {
                        let result = (|| {
                            serde_json::to_writer(&mut pipe, &v)?;
                            pipe.write_all(b"\n")?;
                            pipe.flush()
                        })()
                        .map_err(|e| Failure::new("command_write_failed", e));
                        let failed = result.is_err();
                        let _ = ack.send(result);
                        if failed {
                            break;
                        }
                    }
                    WriteRequest::Close(ack) => {
                        drop(pipe);
                        let _ = ack.send(Ok(()));
                        return;
                    }
                }
            }
        });
        Self { tx, closed: false }
    }
    fn write(&self, v: Value, timeout: Duration) -> Result<()> {
        let (tx, rx) = mpsc::channel();
        self.tx
            .try_send(WriteRequest::Record(v, tx))
            .map_err(|e| Failure::new("command_write_failed", e))?;
        rx.recv_timeout(timeout)
            .map_err(|e| Failure::new("command_write_failed", e))?
    }
    fn close(&mut self, timeout: Duration) -> Result<()> {
        if self.closed {
            return Ok(());
        }
        self.closed = true;
        let (tx, rx) = mpsc::channel();
        self.tx
            .try_send(WriteRequest::Close(tx))
            .map_err(|e| Failure::new("command_write_failed", e))?;
        rx.recv_timeout(timeout)
            .map_err(|e| Failure::new("command_write_failed", e))?
    }
}
struct Rpc<'a> {
    c: &'a Config,
    out: &'a Output,
    owned: Owned,
    writer: PipeWriter,
    rx: Receiver<Input>,
    pending: HashMap<String, String>,
    responses: HashMap<String, Value>,
    seq: u64,
    parser: TurnParser,
    session: Option<Session>,
    session_emitted: bool,
    prompt_sent: bool,
    cancelling: bool,
    accepting_events: bool,
    stdout_eof: bool,
    stderr_eof: bool,
    total_deadline: Instant,
}
impl Rpc<'_> {
    fn remaining(&self, deadline: Instant) -> Result<Duration> {
        deadline
            .checked_duration_since(Instant::now())
            .ok_or_else(|| Failure::new("deadline_exceeded", "operation deadline expired"))
    }
    fn send(&mut self, mut v: Value, deadline: Instant) -> Result<String> {
        self.seq += 1;
        let id = format!("{}-{}", self.c.cancel.identity.turn_id, self.seq);
        v["id"] = json!(id);
        let command = v["type"]
            .as_str()
            .ok_or_else(|| Failure::new("internal", "command type"))?
            .to_owned();
        self.writer.write(
            v,
            self.remaining(deadline)?
                .min(ms(self.c.deadlines.command_ms)),
        )?;
        self.pending.insert(id.clone(), command);
        Ok(id)
    }
    fn check_control(&self) -> Result<()> {
        if !self.cancelling {
            if self.c.cancelled()? {
                return Err(Failure::new(
                    "cancelled",
                    "owned cancel marker matched run/turn/token/generation",
                ));
            }
            if Instant::now() >= self.total_deadline {
                return Err(Failure::new("turn_deadline", "total turn deadline expired"));
            }
        }
        Ok(())
    }
    fn pump(&mut self, deadline: Instant) -> Result<()> {
        self.check_control()?;
        let wait = self.remaining(deadline)?.min(ms(10));
        match self.rx.recv_timeout(wait) {
            Ok(Input::Record(v)) => {
                if v["type"].as_str().is_some_and(|s| s.starts_with("bridge_")) {
                    return Err(Failure::new(
                        "bad_protocol",
                        "child cannot emit bridge-owned records",
                    ));
                }
                self.out.emit(v.clone())?;
                if v["type"] == "response" {
                    let id = v["id"]
                        .as_str()
                        .ok_or_else(|| Failure::new("bad_response", "response id missing"))?;
                    let expected = self.pending.remove(id).ok_or_else(|| {
                        Failure::new("bad_response", "unknown or duplicate response id")
                    })?;
                    if v["command"] != expected {
                        return Err(Failure::new(
                            "bad_response",
                            "response command differs from request",
                        ));
                    }
                    if v["success"] != true {
                        return Err(Failure::new(
                            "command_failed",
                            format!("{expected}: {}", v["error"]),
                        ));
                    }
                    self.responses.insert(id.into(), v["data"].clone());
                } else if v["type"] == "extension_ui_request" {
                    let method = v["method"].as_str().unwrap_or("");
                    if ["select", "confirm", "input", "editor"].contains(&method) {
                        let id = v["id"]
                            .as_str()
                            .ok_or_else(|| Failure::new("bad_protocol", "UI id absent"))?;
                        self.writer.write(
                            json!({"type":"extension_ui_response","id":id,"cancelled":true}),
                            self.remaining(deadline)?
                                .min(ms(self.c.deadlines.command_ms)),
                        )?;
                        self.out.emit(json!({"type":"bridge_ui_denied","id":id,"method":method,"reason":"unattended builder cannot answer dialogs"}))?;
                        return Err(Failure::new("extension_ui_denied", method));
                    } else if ![
                        "notify",
                        "setStatus",
                        "setWidget",
                        "setTitle",
                        "set_editor_text",
                    ]
                    .contains(&method)
                    {
                        return Err(Failure::new("unsupported_ui", method));
                    }
                } else if self.accepting_events {
                    let kind = v["type"].as_str().unwrap_or("");
                    if !self.prompt_sent
                        && [
                            "agent_start",
                            "message_start",
                            "message_update",
                            "message_end",
                            "agent_end",
                            "agent_settled",
                            "tool_execution_start",
                        ]
                        .contains(&kind)
                    {
                        return Err(Failure::new(
                            "unexpected_run",
                            "run event before owned prompt",
                        ));
                    }
                    self.parser.accept(&v, self.c)?;
                    // Persistence may still be creating a header or appending a record.
                    // New-session history is checked only after disposal/exit, below.
                }
            }
            Ok(Input::Stderr(bytes)) => self
                .out
                .emit(json!({"type":"bridge_stderr","bytes":bytes}))?,
            Ok(Input::Error(e)) => return Err(e),
            Ok(Input::Eof(stdout)) => {
                if stdout {
                    self.stdout_eof = true;
                } else {
                    self.stderr_eof = true;
                }
            }
            Err(mpsc::RecvTimeoutError::Timeout) => {}
            Err(mpsc::RecvTimeoutError::Disconnected) => {
                self.stdout_eof = true;
                self.stderr_eof = true;
            }
        }
        Ok(())
    }
    fn wait_response(&mut self, id: &str, deadline: Instant) -> Result<Value> {
        loop {
            self.check_control()?;
            if let Some(v) = self.responses.remove(id) {
                return Ok(v);
            }
            if self.stdout_eof {
                return Err(Failure::new(
                    "unexpected_eof",
                    "Pi stdout closed before response",
                ));
            }
            self.pump(deadline)?;
        }
    }
    fn request(&mut self, v: Value, deadline: Instant) -> Result<Value> {
        let id = self.send(v, deadline)?;
        self.wait_response(&id, deadline)
    }
    fn command_deadline(&self) -> Instant {
        (Instant::now() + ms(self.c.deadlines.command_ms)).min(self.total_deadline)
    }
    fn turn(&mut self, task: &str) -> Result<()> {
        self.check_control()?;
        self.request(
            json!({"type":"set_model","provider":self.c.provider,"modelId":self.c.model}),
            self.command_deadline(),
        )?;
        self.request(
            json!({"type":"set_thinking_level","level":self.c.thinking}),
            self.command_deadline(),
        )?;
        let state = self.request(json!({"type":"get_state"}), self.command_deadline())?;
        self.session = Some(Session::from_state(self.c, &state)?);
        if self.session.as_ref().unwrap().verified {
            self.out
                .emit(self.session.as_ref().unwrap().event(self.c))?;
            self.session_emitted = true;
        }
        self.prompt_sent = true;
        let disposition = self.request(
            json!({"type":"prompt","message":task}),
            self.command_deadline(),
        )?;
        if disposition["disposition"] != "started" {
            return Err(Failure::new(
                "prompt_not_started",
                format!("disposition: {}", disposition["disposition"]),
            ));
        }
        while !self.parser.settled {
            if self.stdout_eof {
                return Err(Failure::new(
                    "missing_settled",
                    "Pi closed stdout before agent_settled",
                ));
            }
            self.pump(self.total_deadline)?;
        }
        // agent_settled ends automatic work; stdin closure/disposal must complete
        // before strictly reading a newly-created JSONL that may be mid-write.
        Ok(())
    }
    fn stop(&mut self, report: &mut Report) {
        self.cancelling = true;
        self.accepting_events = false;
        let deadline = Instant::now() + ms(self.c.deadlines.grace_ms);
        if report
            .failure
            .as_ref()
            .is_some_and(|f| f.code == "cancelled")
        {
            report.cancel_acknowledged = true;
            let _=self.out.emit(json!({"type":"bridge_cancel_ack","runId":self.c.cancel.identity.run_id,"turnId":self.c.cancel.identity.turn_id,"generation":self.c.cancel.identity.generation}));
        }
        // Wait for clear_queue's correlated success before sending abort. A successful
        // abort response is Pi's documented idle acknowledgement.
        if self
            .request(json!({"type":"clear_queue"}), deadline)
            .is_ok()
        {
            report.queue_cleared = true;
            if self.request(json!({"type":"abort"}), deadline).is_ok() {
                report.abort_idle = true;
            }
        }
    }
    fn shutdown(&mut self, report: &mut Report) {
        self.cancelling = true;
        let shutdown = Instant::now() + ms(self.c.deadlines.shutdown_ms);
        if let Err(e) = self
            .writer
            .close(ms(self.c.deadlines.command_ms).min(ms(self.c.deadlines.shutdown_ms)))
        {
            if report.failure.is_none() {
                report.failure = Some(e);
            }
        }
        loop {
            let cleanup = self.owned.cleanup();
            if cleanup.root_exited && cleanup.members_empty && self.stdout_eof && self.stderr_eof {
                break;
            }
            if Instant::now() >= shutdown {
                if report.failure.is_none() {
                    report.failure = Some(Failure::new(
                        "shutdown_deadline",
                        "owned child/pipes/members did not finish orderly shutdown",
                    ));
                }
                self.owned.terminate();
                break;
            }
            if let Err(e) = self.pump(shutdown) {
                if report.failure.is_none() {
                    report.failure = Some(e);
                }
            }
        }
        let hard_deadline = Instant::now() + ms(self.c.deadlines.hard_kill_ms);
        while Instant::now() < hard_deadline {
            let cleanup = self.owned.cleanup();
            if cleanup.root_exited && cleanup.members_empty && self.stdout_eof && self.stderr_eof {
                break;
            }
            let _ = self.pump(hard_deadline);
        }
        report.child_exit = self
            .owned
            .child
            .try_wait()
            .ok()
            .flatten()
            .and_then(|s| s.code());
        report.cleanup = self.owned.cleanup();
        if !self.stdout_eof || !self.stderr_eof {
            report.cleanup.status = "unknown";
            report
                .cleanup
                .detail
                .push_str("; pipes not confirmed closed");
        }
    }
}
/// Owns one Pi child and one task. Caller supplies already-owned resource roots;
/// no personal config, credentials or MCP file is read/copied by this crate.
pub fn emit_preflight_failure(
    mut failure: Failure,
    writer: impl Write + Send + 'static,
) -> Result<()> {
    failure.detail = failure.detail.chars().take(4096).collect();
    let out = Output::new(writer, ms(250));
    out.emit(failure_event(&failure))?;
    out.emit(json!({"type":"bridge_complete","success":false,"cleanup":Cleanup::not_started(),"settled":false}))
}

#[cfg(feature = "fixtures")]
pub use crate::process::SpawnFault;
#[cfg(feature = "fixtures")]
pub fn run_with_spawn_fault(
    config: Config,
    task: String,
    writer: impl Write + Send + 'static,
    fault: SpawnFault,
) -> Report {
    run_inner(config, task, writer, Some(fault))
}
pub fn run(config: Config, task: String, writer: impl Write + Send + 'static) -> Report {
    run_inner(config, task, writer, None)
}
fn run_inner(
    mut config: Config,
    task: String,
    writer: impl Write + Send + 'static,
    fault: Option<crate::process::SpawnFault>,
) -> Report {
    let mut report = Report::empty();
    let mut redactions = Redactions::default();
    // Use a safe fixed bound even before configuration validation.
    let out = Output::new(writer, ms(config.deadlines.command_ms.clamp(10, 60_000)));
    let prepare = (|| -> Result<Command> {
        config.validate()?;
        if task.trim().is_empty() || task.len() > MAX_TASK {
            return Err(Failure::new(
                "invalid_task",
                "nonempty UTF-8 task <= 1MiB required",
            ));
        }
        if config.cancelled()? {
            return Err(Failure::new(
                "cancelled",
                "cancel marker matched before launch",
            ));
        }
        if let Some(path) = &config.session_path {
            validate_file(path, None, &config)?;
        }
        let credentials = config.credential_environment()?;
        redactions = Redactions::from_config(&credentials, &config)?;
        out.set_redactions(redactions.clone());
        redactions.check_config(&config)?;
        let mut cmd = Command::new(native_path(&config.pi.program)?);
        cmd.args(config.pi_args())
            .current_dir(native_path(&config.task_cwd)?)
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::piped())
            .env_clear();
        // Infrastructure only; explicit credential references are added separately.
        // No inherited PI_* selection, NODE_OPTIONS or personal resource variables.
        for name in [
            "PATH",
            "SystemRoot",
            "WINDIR",
            "COMSPEC",
            "PATHEXT",
            "TEMP",
            "TMP",
            "TMPDIR",
            "LANG",
            "LC_ALL",
        ] {
            if let Some(v) = std::env::var_os(name) {
                cmd.env(name, v);
            }
        }
        cmd.env("PI_CODING_AGENT_DIR", native_path(&config.agent_dir)?)
            .env(
                "PI_CODING_AGENT_SESSION_DIR",
                native_path(&config.session_dir)?,
            )
            .env("PI_OFFLINE", "1");
        cmd.envs(credentials);
        Ok(cmd)
    })()
    .map_err(SpawnFailure::before_child)
    .and_then(|mut cmd| Owned::spawn(&mut cmd, ms(config.deadlines.hard_kill_ms), fault));
    match prepare {
        Err(error) => {
            report.failure = Some(error.failure);
            report.cleanup = error.cleanup;
        }
        Ok(mut owned) => {
            let writer = PipeWriter::new(owned.child.stdin.take().unwrap());
            let rx = readers(
                owned.child.stdout.take().unwrap(),
                owned.child.stderr.take().unwrap(),
                redactions.clone(),
            );
            let mut rpc = Rpc {
                c: &config,
                out: &out,
                owned,
                writer,
                rx,
                pending: HashMap::new(),
                responses: HashMap::new(),
                seq: 0,
                parser: TurnParser::default(),
                session: None,
                session_emitted: false,
                prompt_sent: false,
                cancelling: false,
                accepting_events: true,
                stdout_eof: false,
                stderr_eof: false,
                total_deadline: Instant::now() + ms(config.deadlines.turn_ms),
            };
            if let Err(e) = rpc.turn(&task) {
                report.failure = Some(e);
                rpc.stop(&mut report);
            }
            rpc.shutdown(&mut report);
            report.settled = rpc.parser.settled;
            report.final_message = rpc.parser.final_message.clone();
            report.usage = rpc.parser.usage.clone();
            report.nested_usage = rpc.parser.nested_usage.clone();
            // Check the actual persisted history again after Pi has disposed, too.
            if report.failure.is_none() {
                if let Some(s) = &mut rpc.session {
                    if let Err(e) = s.verify(&config) {
                        report.failure = Some(e);
                    } else if !rpc.session_emitted {
                        if let Err(e) = out.emit(s.event(&config)) {
                            report.failure = Some(e);
                        }
                        rpc.session_emitted = true;
                    }
                }
            }
            if report.failure.is_none() && report.child_exit != Some(0) {
                report.failure = Some(Failure::new(
                    "child_exit",
                    "Pi did not exit with status zero",
                ));
            }
            if report.failure.is_none() && report.cleanup.status != "verified" {
                report.failure = Some(Failure::new("cleanup_unknown", &report.cleanup.detail));
            }
        }
    }
    report.success = report.failure.is_none() && report.settled;
    report.redact(&redactions);
    if let Some(f) = &report.failure {
        let _ = out.emit(failure_event(f));
    }
    if let Err(e)=out.emit(json!({"type":"bridge_complete","success":report.success,"cleanup":report.cleanup,"childExit":report.child_exit,"settled":report.settled,"usage":report.usage,"nestedUsage":report.nested_usage,"finalMessage":report.final_message,"cancelAcknowledged":report.cancel_acknowledged,"queueCleared":report.queue_cleared,"abortIdle":report.abort_idle})){
        report.success=false;
        let _=out.emit(failure_event(&e));
        report.failure=Some(e);
    }
    report.redact(&redactions);
    report
}
