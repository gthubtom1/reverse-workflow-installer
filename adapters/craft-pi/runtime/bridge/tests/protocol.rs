#![cfg(feature = "fixtures")]
use craft_pi_bridge::{
    adapter::PiRpcAdapter,
    config::{Cancel, CancelIdentity, Config, Deadlines, PiCommand},
    driver::{self, Report},
    parser::{AdapterEvent, BridgeParser},
};
use serde_json::{Value, json};
use std::{
    fs,
    io::{self, Write},
    path::PathBuf,
    process::{Command, Stdio},
    sync::{
        Arc, Mutex,
        atomic::{AtomicU64, Ordering},
    },
    thread,
    time::{Duration, Instant},
};
static NEXT: AtomicU64 = AtomicU64::new(0);
struct Fixture {
    root: PathBuf,
    c: Config,
}
impl Fixture {
    fn new(scenario: &str) -> Self {
        let root = PathBuf::from(std::env::var_os("CRAFT_TEST_ROOT").expect("CRAFT_TEST_ROOT must be explicit"))
            .join(format!(
                "{}-{}-{}",
                std::process::id(),
                NEXT.fetch_add(1, Ordering::Relaxed),
                scenario
            ));
        for dir in ["app", "agent", "sessions", "control"] {
            fs::create_dir_all(root.join(dir)).unwrap();
        }
        fs::write(root.join("agent/scenario"), scenario).unwrap();
        let mut c = Config {
            provider: "magpie".into(),
            model: "gpt/gpt-6.1-sol".into(),
            thinking: "high".into(),
            public_selection: None,
            pi: PiCommand {
                program: PathBuf::from(env!("CARGO_BIN_EXE_fake-pi")),
                argv: vec![],
            },
            task_cwd: root.join("app"),
            agent_dir: root.join("agent"),
            session_dir: root.join("sessions"),
            session_path: None,
            instructions: "Only implement the approved task. Do not delegate or expand scope."
                .into(),
            selected_mcp_tools: vec!["mcp__fixture__read".into()],
            credential_env_keys: vec![],
            cancel: Cancel {
                marker: root.join("control/cancel.json"),
                identity: CancelIdentity {
                    run_id: "run-0123456789abcdef".into(),
                    turn_id: "turn-0123456789abcdef".into(),
                    generation: 1,
                    token: "token-0123456789abcdef".into(),
                },
            },
            deadlines: Deadlines {
                input_ms: 1000,
                command_ms: 1500,
                turn_ms: 3000,
                grace_ms: 500,
                shutdown_ms: 250,
                hard_kill_ms: 2000,
            },
        };
        c.validate().unwrap();
        Self { root, c }
    }
    fn config_file(&self) -> PathBuf {
        let p = self.root.join("driver.json");
        fs::write(&p, serde_json::to_vec_pretty(&self.c).unwrap()).unwrap();
        p
    }
    fn run(&self) -> (Report, Vec<Value>) {
        let buf = Buffer::default();
        let report = driver::run(self.c.clone(), "approved task".into(), buf.clone());
        let events = parse(&buf.0.lock().unwrap());
        (report, events)
    }
    fn cli_with_env(&self, environment: &[(&str, &str)]) -> std::process::Output {
        let path = self.config_file();
        let mut command = Command::new(env!("CARGO_BIN_EXE_pi-rpc-driver"));
        command
            .arg(path)
            .env_remove("CRAFT_BRIDGE_ALLOWED_TEST_KEY")
            .env_remove("CRAFT_BRIDGE_UNLISTED_TEST_KEY")
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::piped());
        for (key, value) in environment {
            command.env(key, value);
        }
        let mut child = command.spawn().unwrap();
        let _ = child.stdin.take().unwrap().write_all(b"approved task");
        child.wait_with_output().unwrap()
    }
    fn cancel_after_prompt(&self) -> thread::JoinHandle<()> {
        let c = self.c.clone();
        thread::spawn(move || {
            let deadline = Instant::now() + Duration::from_secs(4);
            while !fs::read_to_string(c.agent_dir.join("commands.jsonl"))
                .unwrap_or_default()
                .lines()
                .any(|l| l == "prompt")
            {
                assert!(Instant::now() < deadline, "fixture never received prompt");
                thread::sleep(Duration::from_millis(5));
            }
            let pending = c.cancel.marker.with_extension("tmp");
            fs::write(&pending, serde_json::to_vec(&c.cancel.identity).unwrap()).unwrap();
            fs::rename(pending, c.cancel.marker).unwrap();
        })
    }
}
#[derive(Clone, Default)]
struct Buffer(Arc<Mutex<Vec<u8>>>);
impl Write for Buffer {
    fn write(&mut self, b: &[u8]) -> io::Result<usize> {
        self.0.lock().unwrap().extend_from_slice(b);
        Ok(b.len())
    }
    fn flush(&mut self) -> io::Result<()> {
        Ok(())
    }
}
fn parse(bytes: &[u8]) -> Vec<Value> {
    bytes
        .split(|b| *b == b'\n')
        .filter(|b| !b.is_empty())
        .map(|b| serde_json::from_slice(b).unwrap())
        .collect()
}
fn check_error(scenario: &str, code: &str) {
    let f = Fixture::new(scenario);
    let (r, e) = f.run();
    assert!(!r.success, "{r:?}");
    assert_eq!(r.failure.as_ref().unwrap().code, code, "{r:?}");
    assert!(
        e.iter()
            .any(|e| e["type"] == "bridge_failure" && e["code"] == code)
    );
    assert!(r.cleanup.root_exited, "{r:?}");
    assert!(r.cleanup.members_empty, "{r:?}");
}
fn protocol_ok(r: &Report) {
    assert!(r.settled, "{r:?}");
    assert_eq!(r.child_exit, Some(0));
    #[cfg(windows)]
    assert!(r.success, "{r:?}");
    #[cfg(unix)]
    assert_eq!(r.failure.as_ref().unwrap().code, "cleanup_unknown");
}

#[test]
fn normal_round_trip_and_craft_consumption() {
    let f = Fixture::new("normal");
    let (r, events) = f.run();
    protocol_ok(&r);
    let commands = fs::read_to_string(f.c.agent_dir.join("commands.jsonl")).unwrap();
    assert_eq!(
        commands.lines().collect::<Vec<_>>(),
        vec!["set_model", "set_thinking_level", "get_state", "prompt"]
    );
    let mut parser = BridgeParser::default();
    let mut mapped = vec![];
    for e in &events {
        mapped.extend(parser.parse(e).unwrap());
    }
    assert!(
        mapped
            .iter()
            .any(|v| matches!(v,AdapterEvent::TextDelta(s) if s.contains("你好")))
    );
    assert!(
        mapped
            .iter()
            .any(|v| matches!(v,AdapterEvent::ToolStarted{id,..} if id=="tool-1"))
    );
    assert!(
        mapped
            .iter()
            .any(|v| matches!(v,AdapterEvent::ToolFinished{id,..} if id=="tool-1"))
    );
    assert!(!events.iter().any(|v| v["type"] == "session"));
    #[cfg(windows)]
    assert!(parser.successful(Some(0)));
    assert!(!parser.successful(Some(1)));
    assert!(!BridgeParser::default().successful(Some(0)));
}
#[test]
fn exact_config_json_and_real_cli() {
    let f = Fixture::new("normal");
    let path = f.config_file();
    let loaded = Config::load(&path).unwrap();
    assert_eq!(loaded.cancel.identity, f.c.cancel.identity);
    let mut p = Command::new(env!("CARGO_BIN_EXE_pi-rpc-driver"))
        .args(["--config", path.to_str().unwrap()])
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .unwrap();
    p.stdin
        .take()
        .unwrap()
        .write_all("task with 你好\n".as_bytes())
        .unwrap();
    let output = p.wait_with_output().unwrap();
    let records = parse(&output.stdout);
    assert!(records.iter().any(|v| v["type"] == "bridge_session"));
    #[cfg(windows)]
    assert!(
        output.status.success(),
        "{}",
        String::from_utf8_lossy(&output.stdout)
    );
}
#[test]
fn utf8_split_crlf_and_unicode_separators() {
    let (r, e) = Fixture::new("utf8").run();
    protocol_ok(&r);
    assert!(
        e.iter()
            .any(|v| v["assistantMessageEvent"]["delta"] == "你好🙂\u{2028}line\u{2029}end")
    );
}
#[test]
fn deduplicate_completed_usage() {
    let (r, _) = Fixture::new("duplicate-usage").run();
    protocol_ok(&r);
    assert_eq!(r.usage.total_tokens, 20);
    assert_eq!(r.usage.input, 10);
    assert_eq!(r.usage.output, 5);
    assert_eq!(r.usage.estimated_cost, 0.1);
}
#[test]
fn state_model_mismatch() {
    check_error("wrong-state-model", "model_mismatch");
}
#[test]
fn final_model_mismatch() {
    check_error("wrong-final-model", "model_mismatch");
}
#[test]
fn final_thinking_mismatch() {
    check_error("wrong-thinking", "model_mismatch");
}
#[test]
fn provider_response_model_mismatch() {
    check_error("wrong-response-model", "model_mismatch");
}
#[test]
fn exit_zero_is_not_provider_success() {
    check_error("exit0-error", "assistant_failed");
}
#[test]
fn length_is_failure() {
    check_error("length", "assistant_failed");
}
#[test]
fn deferred_is_failure() {
    check_error("deferred", "assistant_failed");
}
#[test]
fn missing_settled_is_failure() {
    check_error("missing-settled", "missing_settled");
}
#[test]
fn queued_is_not_owned_turn() {
    check_error("queued", "prompt_not_started");
}
#[test]
fn handled_is_not_owned_turn() {
    check_error("handled", "prompt_not_started");
}
#[test]
fn response_failure() {
    check_error("response-error", "command_failed");
}
#[test]
fn response_id_must_correlate() {
    check_error("bad-response-id", "bad_response");
}
#[test]
fn malformed_json() {
    check_error("bad-json", "bad_json");
}
#[test]
fn invalid_utf8() {
    check_error("invalid-utf8", "invalid_utf8");
}
#[test]
fn partial_frame_at_exit() {
    check_error("truncated", "truncated_frame");
}
#[test]
fn record_size_bound() {
    check_error("record-limit", "record_limit");
}
#[test]
fn missing_new_session_file() {
    check_error("lost-session", "session_missing");
}
#[test]
fn wrong_header_cwd() {
    check_error("wrong-cwd", "session_mismatch");
}
#[test]
fn session_outside_owned_root() {
    check_error("wrong-state-session", "session_mismatch");
}
#[test]
fn nonzero_exit_after_complete_events() {
    check_error("exit7-after-eof", "child_exit");
}
#[test]
fn stderr_is_independently_drained() {
    let (r, e) = Fixture::new("stderr-flood").run();
    protocol_ok(&r);
    let size: usize = e
        .iter()
        .filter(|v| v["type"] == "bridge_stderr")
        .map(|v| v["bytes"].as_array().unwrap().len())
        .sum();
    assert_eq!(size, 256 * 1024);
}
#[test]
fn extension_dialog_denied() {
    let f = Fixture::new("ui");
    let (r, _) = f.run();
    assert_eq!(r.failure.unwrap().code, "extension_ui_denied");
    let v: Value =
        serde_json::from_slice(&fs::read(f.c.agent_dir.join("ui-response")).unwrap()).unwrap();
    assert_eq!(v["cancelled"], true);
}
#[test]
fn cooperative_cancel_clears_before_abort() {
    let f = Fixture::new("cancel");
    let marker = f.cancel_after_prompt();
    let (r, e) = f.run();
    marker.join().unwrap();
    assert_eq!(r.failure.as_ref().unwrap().code, "cancelled");
    assert!(
        r.cancel_acknowledged && r.queue_cleared && r.abort_idle,
        "{r:?}"
    );
    assert!(!f.c.agent_dir.join("queue-ran").exists());
    let commands = fs::read_to_string(f.c.agent_dir.join("commands.jsonl")).unwrap();
    assert!(commands.ends_with("clear_queue\nabort\n"));
    assert!(e.iter().any(|v| v["type"] == "bridge_cancel_ack"));
    assert!(r.cleanup.root_exited && r.cleanup.members_empty);
}
#[test]
fn stale_cancel_token_is_not_replayed() {
    let f = Fixture::new("normal");
    let mut identity = f.c.cancel.identity.clone();
    identity.token = "stale-0123456789abcdef".into();
    fs::write(&f.c.cancel.marker, serde_json::to_vec(&identity).unwrap()).unwrap();
    let (r, _) = f.run();
    protocol_ok(&r);
    assert!(!r.cancel_acknowledged);
}
#[test]
fn stale_cancel_turn_is_not_replayed() {
    let f = Fixture::new("normal");
    let mut id = f.c.cancel.identity.clone();
    id.turn_id = "old-turn-0123456789abcdef".into();
    fs::write(&f.c.cancel.marker, serde_json::to_vec(&id).unwrap()).unwrap();
    let (r, _) = f.run();
    protocol_ok(&r);
}
#[test]
fn cancel_before_spawn() {
    let f = Fixture::new("normal");
    fs::write(
        &f.c.cancel.marker,
        serde_json::to_vec(&f.c.cancel.identity).unwrap(),
    )
    .unwrap();
    let (r, _) = f.run();
    assert_eq!(r.failure.unwrap().code, "cancelled");
    assert_eq!(r.cleanup.status, "not_started");
    assert!(!f.c.agent_dir.join("commands.jsonl").exists());
}
#[test]
fn uncooperative_cancel_is_hard_terminated() {
    let f = Fixture::new("hard-cancel");
    let marker = f.cancel_after_prompt();
    let (r, _) = f.run();
    marker.join().unwrap();
    assert_eq!(r.failure.as_ref().unwrap().code, "cancelled");
    assert!(r.cleanup.hard_terminated, "{r:?}");
    assert!(r.cleanup.root_exited && r.cleanup.members_empty, "{r:?}");
    assert!(!r.abort_idle);
}
#[test]
fn turn_deadline_cleans_up() {
    let mut f = Fixture::new("hang");
    f.c.deadlines.turn_ms = 500;
    let (r, _) = f.run();
    assert_eq!(r.failure.as_ref().unwrap().code, "turn_deadline");
    assert!(r.queue_cleared && r.abort_idle, "{r:?}");
    assert!(r.cleanup.root_exited && r.cleanup.members_empty);
}
#[test]
fn eof_shutdown_deadline() {
    check_error("exit-hang", "shutdown_deadline");
}
#[test]
fn descendant_cannot_outlive_owned_job() {
    let f = Fixture::new("descendant");
    let marker = f.cancel_after_prompt();
    let (r, _) = f.run();
    marker.join().unwrap();
    assert!(r.cleanup.hard_terminated, "{r:?}");
    assert!(r.cleanup.root_exited && r.cleanup.members_empty, "{r:?}");
    let heartbeat = f.c.agent_dir.join("heartbeat");
    let before = fs::metadata(&heartbeat).unwrap().modified().unwrap();
    thread::sleep(Duration::from_millis(100));
    assert_eq!(before, fs::metadata(heartbeat).unwrap().modified().unwrap());
}
#[test]
fn missing_resume_file_never_starts_fresh() {
    let mut f = Fixture::new("normal");
    f.c.session_path = Some(f.c.session_dir.join("lost.jsonl"));
    let (r, _) = f.run();
    assert_eq!(r.failure.unwrap().code, "session_missing");
    assert!(!f.c.agent_dir.join("commands.jsonl").exists());
}
#[test]
fn corrupt_resume_refused_before_spawn() {
    let mut f = Fixture::new("normal");
    let file = f.c.session_dir.join("resume.jsonl");
    fs::write(&file, b"{\"type\":\"session\"}\n{").unwrap();
    f.c.session_path = Some(file);
    let (r, _) = f.run();
    assert_eq!(r.failure.unwrap().code, "session_corrupt");
    assert!(!f.c.agent_dir.join("commands.jsonl").exists());
}
#[test]
fn exact_resume_file_is_used() {
    let f = Fixture::new("normal");
    let (r, e) = f.run();
    protocol_ok(&r);
    let path = e.iter().find(|v| v["type"] == "bridge_session").unwrap()["sessionFile"]
        .as_str()
        .unwrap();
    let mut c = f.c.clone();
    c.session_path = Some(PathBuf::from(path));
    let r = driver::run(c, "followup".into(), Buffer::default());
    protocol_ok(&r);
}
#[test]
fn sink_write_failure_still_cleans_child() {
    struct Broken;
    impl Write for Broken {
        fn write(&mut self, _: &[u8]) -> io::Result<usize> {
            Err(io::Error::new(
                io::ErrorKind::BrokenPipe,
                "fixture closed output",
            ))
        }
        fn flush(&mut self) -> io::Result<()> {
            Ok(())
        }
    }
    let f = Fixture::new("normal");
    let r = driver::run(f.c, "task".into(), Broken);
    assert_eq!(r.failure.unwrap().code, "output_write_failed");
    assert!(r.cleanup.root_exited && r.cleanup.members_empty);
}
#[test]
fn unknown_config_fields_are_rejected() {
    let f = Fixture::new("normal");
    let mut value = serde_json::to_value(&f.c).unwrap();
    value["ssh"] = json!("host");
    let path = f.root.join("bad.json");
    fs::write(&path, value.to_string()).unwrap();
    assert_eq!(Config::load(&path).unwrap_err().code, "invalid_config");
}
#[test]
fn unknown_pi_flags_and_native_tools_are_rejected() {
    let mut f = Fixture::new("normal");
    f.c.pi.argv = vec!["--continue".into()];
    assert_eq!(f.c.validate().unwrap_err().code, "invalid_config");
    f.c.pi.argv.clear();
    f.c.selected_mcp_tools = vec!["bash".into()];
    assert_eq!(f.c.validate().unwrap_err().code, "invalid_config");
}
#[test]
fn adapter_core_refuses_fallback_ssh_questions_extra_args() {
    let f = Fixture::new("normal");
    let p = f.config_file();
    let a = PiRpcAdapter::load(&PathBuf::from(env!("CARGO_BIN_EXE_pi-rpc-driver")), &p).unwrap();
    assert!(!a.plain_fallback());
    assert!(a.prompt_on_stdin());
    assert_eq!(a.folder_var(), "PI_CODING_AGENT_DIR");
    assert!(a.invocation("task", Some("host"), &[], false).is_err());
    assert!(
        a.invocation("task", None, &["--unknown".into()], false)
            .is_err()
    );
    assert!(a.invocation("task", None, &[], true).is_err());
    let plan = a.invocation("task", None, &[], false).unwrap();
    assert_eq!(plan.stdin_text, "task");
    assert_eq!(plan.args[0], "--config");
}
#[test]
fn unexpected_native_tool_event_is_failure() {
    check_error("unexpected-tool", "unexpected_tool");
}
#[test]
fn post_settled_run_event_is_failure() {
    check_error("after-settled", "event_after_settled");
}
#[test]
fn settled_without_final_is_failure() {
    check_error("no-final", "missing_final");
}
#[test]
fn aborted_settled_is_failure() {
    check_error("aborted-settled", "aborted");
}
#[test]
fn deleted_persisted_session_is_failure() {
    check_error("delete-on-exit", "session_missing");
}
#[test]
fn stalled_command_deadline_cleans_child() {
    let mut f = Fixture::new("command-timeout");
    f.c.deadlines.command_ms = 200;
    let (r, _) = f.run();
    assert_eq!(r.failure.as_ref().unwrap().code, "deadline_exceeded");
    assert!(r.cleanup.root_exited && r.cleanup.members_empty, "{r:?}");
}
#[test]
fn child_stdin_write_failure_is_structured() {
    check_error("close-input", "command_write_failed");
}
#[test]
fn missing_runtime_is_explicit() {
    let mut f = Fixture::new("normal");
    f.c.pi.program = f.root.join("missing-pi.exe");
    let (r, _) = f.run();
    assert_eq!(r.failure.unwrap().code, "runtime_unavailable");
    assert_eq!(r.cleanup.status, "not_started");
}
#[test]
fn cli_stdin_eof_deadline_is_bounded() {
    let mut f = Fixture::new("normal");
    f.c.deadlines.input_ms = 100;
    let path = f.config_file();
    let mut child = Command::new(env!("CARGO_BIN_EXE_pi-rpc-driver"))
        .arg(path)
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .spawn()
        .unwrap();
    let open_stdin = child.stdin.take().unwrap();
    let o = child.wait_with_output().unwrap();
    drop(open_stdin);
    assert!(!o.status.success());
    assert!(
        parse(&o.stdout)
            .iter()
            .any(|v| v["code"] == "input_deadline")
    );
    assert!(!f.c.agent_dir.join("commands.jsonl").exists());
}
#[cfg(windows)]
#[test]
fn killing_driver_closes_owned_job() {
    let f = Fixture::new("descendant");
    let path = f.config_file();
    let mut child = Command::new(env!("CARGO_BIN_EXE_pi-rpc-driver"))
        .arg(path)
        .stdin(Stdio::piped())
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .spawn()
        .unwrap();
    child
        .stdin
        .take()
        .unwrap()
        .write_all(b"approved task")
        .unwrap();
    let heartbeat = f.c.agent_dir.join("heartbeat");
    let deadline = Instant::now() + Duration::from_secs(2);
    while !heartbeat.exists() {
        assert!(Instant::now() < deadline);
        thread::sleep(Duration::from_millis(5));
    }
    child.kill().unwrap();
    child.wait().unwrap();
    thread::sleep(Duration::from_millis(100));
    let before = fs::metadata(&heartbeat).unwrap().modified().unwrap();
    thread::sleep(Duration::from_millis(100));
    assert_eq!(before, fs::metadata(heartbeat).unwrap().modified().unwrap());
}
fn synthetic_credential() -> String {
    format!(
        "synth_{}_{}_only_env_世界🙂_quote_\"_slash_\\_line_\n_end",
        std::process::id(),
        NEXT.fetch_add(1, Ordering::Relaxed)
    )
}
fn assert_no_credential(bytes: &[u8], credential: &str) {
    let escaped = serde_json::to_string(credential).unwrap();
    for pattern in [
        credential.as_bytes(),
        &escaped.as_bytes()[1..escaped.len() - 1],
        &credential.as_bytes()[..credential.len() / 2],
    ] {
        assert!(
            !bytes.windows(pattern.len()).any(|w| w == pattern),
            "sensitive credential material was emitted"
        );
    }
}
#[test]
fn explicit_credential_echo_is_redacted_in_json_and_chunked_binary_stderr() {
    let mut f = Fixture::new("credential-echo");
    f.c.credential_env_keys = vec!["CRAFT_BRIDGE_ALLOWED_TEST_KEY".into()];
    let credential = synthetic_credential();
    let output = f.cli_with_env(&[("CRAFT_BRIDGE_ALLOWED_TEST_KEY", credential.as_str())]);
    #[cfg(windows)]
    assert!(output.status.success());
    assert_no_credential(&output.stdout, &credential);
    assert_no_credential(&output.stderr, &credential);
    assert_no_credential(&fs::read(f.root.join("driver.json")).unwrap(), &credential);
    let events = parse(&output.stdout);
    let mut diagnostics = Vec::new();
    for event in &events {
        if event["type"] == "bridge_stderr" {
            diagnostics.extend(
                event["bytes"]
                    .as_array()
                    .unwrap()
                    .iter()
                    .map(|n| n.as_u64().unwrap() as u8),
            );
        }
    }
    assert_no_credential(&diagnostics, &credential);
    assert!(diagnostics.starts_with(&[0xff, 0x00]));
    assert!(
        diagnostics
            .windows(b"[REDACTED]".len())
            .filter(|w| *w == b"[REDACTED]")
            .count()
            >= 3
    );
    let complete = events
        .iter()
        .find(|v| v["type"] == "bridge_complete")
        .unwrap();
    assert_eq!(complete["finalMessage"]["content"][0]["text"], "[REDACTED]");
    assert!(
        events
            .iter()
            .any(|v| v["type"] == "bridge_progress" && v["event"] == "credential_diagnostic")
    );
    assert!(!events.iter().any(|v| v["type"] == "credential_diagnostic"));
}
#[test]
fn credential_in_provider_failure_detail_is_redacted() {
    let mut f = Fixture::new("credential-echo-error");
    f.c.credential_env_keys = vec!["CRAFT_BRIDGE_ALLOWED_TEST_KEY".into()];
    let credential = synthetic_credential();
    let output = f.cli_with_env(&[("CRAFT_BRIDGE_ALLOWED_TEST_KEY", credential.as_str())]);
    assert!(!output.status.success());
    assert_no_credential(&output.stdout, &credential);
    assert_no_credential(&output.stderr, &credential);
    let events = parse(&output.stdout);
    let failure = events
        .iter()
        .find(|v| v["type"] == "bridge_failure")
        .unwrap();
    assert_eq!(failure["code"], "command_failed");
    assert!(failure["detail"].as_str().unwrap().contains("[REDACTED]"));
    for event in events {
        if event["type"] == "bridge_stderr" {
            let bytes: Vec<u8> = event["bytes"]
                .as_array()
                .unwrap()
                .iter()
                .map(|n| n.as_u64().unwrap() as u8)
                .collect();
            assert_no_credential(&bytes, &credential);
        }
    }
}
#[test]
fn returned_report_and_config_clone_debug_do_not_expose_injected_credential() {
    for mode in ["--report-redaction", "--report-redaction-sink"] {
        let mut f = Fixture::new("credential-echo");
        f.c.credential_env_keys = vec!["CRAFT_BRIDGE_ALLOWED_TEST_KEY".into()];
        let credential = synthetic_credential();
        let config = f.config_file();
        let output = Command::new(env!("CARGO_BIN_EXE_fake-pi"))
            .args([mode, config.to_str().unwrap()])
            .env("CRAFT_BRIDGE_ALLOWED_TEST_KEY", &credential)
            .stdin(Stdio::null())
            .stdout(Stdio::piped())
            .stderr(Stdio::piped())
            .output()
            .unwrap();
        assert!(output.status.success());
        assert_no_credential(&output.stdout, &credential);
        assert_no_credential(&output.stderr, &credential);
        let text = String::from_utf8(output.stdout).unwrap();
        assert!(text.contains("config_debug="));
        assert!(text.contains("report_debug="));
        assert!(text.contains("report_json="));
        if mode == "--report-redaction" {
            assert!(text.contains("[REDACTED]"));
        } else {
            let line = text
                .lines()
                .find_map(|line| line.strip_prefix("report_json="))
                .unwrap();
            let report: Value = serde_json::from_str(line).unwrap();
            assert_eq!(report["failure"]["code"], "output_write_failed");
            assert_eq!(report["cleanup"]["root_exited"], true);
        }
    }
}
fn collect_text_fragments(v: &Value, output: &mut String) {
    match v {
        Value::Array(items) => {
            for item in items {
                collect_text_fragments(item, output);
            }
        }
        Value::Object(map) => {
            for (key, value) in map {
                if ["text", "delta", "thinking"].contains(&key.as_str()) {
                    if let Some(text) = value.as_str() {
                        output.push_str(text);
                    }
                } else if value.is_array() || value.is_object() {
                    collect_text_fragments(value, output);
                }
            }
        }
        _ => {}
    }
}
#[test]
fn credential_content_deltas_and_final_parts_cannot_reassemble_value() {
    for scenario in ["credential-deltas", "credential-deltas-eof"] {
        let mut f = Fixture::new(scenario);
        f.c.credential_env_keys = vec!["CRAFT_BRIDGE_ALLOWED_TEST_KEY".into()];
        let credential = synthetic_credential();
        let output = f.cli_with_env(&[("CRAFT_BRIDGE_ALLOWED_TEST_KEY", &credential)]);
        assert_no_credential(&output.stdout, &credential);
        assert_no_credential(&output.stderr, &credential);
        let events = parse(&output.stdout);
        let mut combined = String::new();
        for v in &events {
            collect_text_fragments(v, &mut combined);
        }
        assert_no_credential(combined.as_bytes(), &credential);
        assert!(!events.iter().any(|v| v["type"] == "message_update"
            || v["type"] == "message_start"
            || v["type"] == "tool_execution_update"));
        if scenario == "credential-deltas" {
            #[cfg(windows)]
            assert!(output.status.success());
            let complete = events
                .iter()
                .find(|v| v["type"] == "bridge_complete")
                .unwrap();
            assert_eq!(complete["finalMessage"]["content"][0]["text"], "[REDACTED]");
            assert!(events.iter().any(|v| v["type"] == "message_end"
                && v["message"]["role"] == "toolResult"
                && v["message"]["content"][0]["text"] == "[REDACTED]"));
        } else {
            assert!(!output.status.success());
            assert!(
                events
                    .iter()
                    .any(|v| v["type"] == "bridge_failure" && v["code"] == "missing_settled")
            );
        }
    }
}
#[cfg(windows)]
#[test]
fn declared_public_selection_accepts_official_partial_rpc_without_thinking() {
    use craft_pi_bridge::config::Selection;
    let secret = "SYNTHETIC_DYNAMIC_SELECTION_QXZ";
    for scenario in ["dynamic-selection-stream", "dynamic-unknown-response"] {
        for field in 0..2 {
            let mut f = Fixture::new(scenario);
            f.c.pi.program = PathBuf::from(std::env::var_os("CRAFT_TEST_NODE").expect("CRAFT_TEST_NODE must be explicit"));
            f.c.pi.argv = vec![
                PathBuf::from(env!("CARGO_MANIFEST_DIR"))
                    .join("tests/fixtures/official_stream_node.cjs")
                    .to_string_lossy()
                    .into(),
            ];
            f.c.provider = if field == 0 {
                secret.into()
            } else {
                "synthetic_provider".into()
            };
            f.c.model = if field == 1 {
                secret.into()
            } else {
                "synthetic_model".into()
            };
            f.c.credential_env_keys = vec!["CRAFT_BRIDGE_ALLOWED_TEST_KEY".into()];
            let environment = [("CRAFT_BRIDGE_ALLOWED_TEST_KEY", secret)];
            // Same peer/config: absent declaration must still fail before spawn.
            let strict = f.cli_with_env(&environment);
            assert!(!strict.status.success());
            assert!(
                parse(&strict.stdout)
                    .iter()
                    .any(|e| e["code"] == "credential_control_conflict")
            );
            assert!(!f.c.agent_dir.join("commands.jsonl").exists());
            f.c.public_selection = Some(Selection {
                provider: f.c.provider.clone(),
                model: f.c.model.clone(),
                thinking: f.c.thinking.clone(),
            });
            let output = f.cli_with_env(&environment);
            let events = parse(&output.stdout);
            assert!(
                fs::read_to_string(f.c.agent_dir.join("commands.jsonl"))
                    .unwrap()
                    .lines()
                    .any(|s| s == "prompt")
            );
            let collision = events
                .iter()
                .find(|e| e["code"] == "credential_control_conflict");
            if let Some(failure) = collision {
                let role = match failure["detail"].as_str() {
                    Some("selection") => "selection",
                    _ => "unknown",
                };
                eprintln!(
                    "public_partial_rpc: prompt_seen=true; failure=credential_control_conflict; role={role}"
                );
            }
            assert!(
                collision.is_none(),
                "public partial metadata was rejected after prompt"
            );
            if scenario == "dynamic-selection-stream" {
                assert!(
                    output.status.success(),
                    "synthetic official stream did not complete"
                );
                assert!(
                    events
                        .iter()
                        .any(|e| e["type"] == "bridge_complete" && e["success"] == true)
                );
            } else {
                assert!(!output.status.success());
                assert!(events.iter().any(|e| e["code"] == "model_mismatch"));
            }
            let message = events.iter().find(|e| e["type"] == "message_end").unwrap();
            assert!(!message["message"]["content"].to_string().contains(secret));
            assert_eq!(message["message"]["errorMessage"], "[REDACTED]");
            if scenario == "dynamic-unknown-response" {
                assert_eq!(
                    message["message"]["responseModel"],
                    "untrusted-[REDACTED]-physical"
                );
            }
            let tool = events
                .iter()
                .find(|e| e["type"] == "tool_execution_end")
                .unwrap();
            assert!(!tool["result"].to_string().contains(secret));
            assert!(tool["result"].to_string().contains("[REDACTED]"));
            for event in events.iter().filter(|e| e["type"] == "bridge_progress") {
                assert!(!event.to_string().contains(secret));
            }
        }
    }
}

#[cfg(windows)]
#[test]
fn official_final_optional_thinking_stays_unknown_and_state_stays_strict() {
    use craft_pi_bridge::config::Selection;
    let secret = "SYNTHETIC_OPTIONAL_SELECTION_QXZ";
    for scenario in [
        "dynamic-no-final-thinking",
        "dynamic-final-wrong-thinking",
        "dynamic-provider-wrong-thinking",
        "dynamic-state-missing-thinking",
        "dynamic-state-wrong-thinking",
    ] {
        let mut f = Fixture::new(scenario);
        f.c.pi.program = PathBuf::from(std::env::var_os("CRAFT_TEST_NODE").expect("CRAFT_TEST_NODE must be explicit"));
        f.c.pi.argv = vec![
            PathBuf::from(env!("CARGO_MANIFEST_DIR"))
                .join("tests/fixtures/official_stream_node.cjs")
                .to_string_lossy()
                .into(),
        ];
        f.c.model = secret.into();
        let state_negative = scenario.starts_with("dynamic-state-");
        if !state_negative {
            f.c.credential_env_keys = vec!["CRAFT_BRIDGE_ALLOWED_TEST_KEY".into()];
        }
        let environment = [("CRAFT_BRIDGE_ALLOWED_TEST_KEY", secret)];
        if scenario == "dynamic-no-final-thinking" {
            let strict = f.cli_with_env(&environment);
            assert!(!strict.status.success());
            assert!(
                parse(&strict.stdout)
                    .iter()
                    .any(|e| e["code"] == "credential_control_conflict")
            );
            assert!(!f.c.agent_dir.join("commands.jsonl").exists());
        }
        f.c.public_selection = Some(Selection {
            provider: f.c.provider.clone(),
            model: f.c.model.clone(),
            thinking: f.c.thinking.clone(),
        });
        let output = f.cli_with_env(&environment);
        let events = parse(&output.stdout);
        if scenario == "dynamic-no-final-thinking" {
            assert!(
                output.status.success(),
                "valid final message without optional effort was refused"
            );
            let message = &events.iter().find(|e| e["type"] == "message_end").unwrap()["message"];
            let final_message = &events
                .iter()
                .find(|e| e["type"] == "bridge_complete")
                .unwrap()["finalMessage"];
            for actual in [message, final_message] {
                assert!(actual.get("thinkingLevel").is_none());
                assert!(actual.get("providerThinkingLevel").is_none());
                assert_eq!(actual["model"], secret);
                assert!(!actual["content"].to_string().contains(secret));
                assert_eq!(actual["errorMessage"], "[REDACTED]");
            }
            assert!(
                events
                    .iter()
                    .any(|e| e["type"] == "bridge_complete" && e["success"] == true)
            );
        } else {
            assert!(!output.status.success());
            if state_negative {
                assert!(events.iter().any(|e| e["code"] == "model_mismatch"));
                let commands = fs::read_to_string(f.c.agent_dir.join("commands.jsonl")).unwrap();
                assert!(!commands.lines().any(|s| s == "prompt"));
            } else {
                assert!(
                    events.iter().any(|e| e["code"] == "model_mismatch"
                        || e["code"] == "credential_control_conflict")
                );
            }
        }
    }
}

#[test]
fn public_selection_declaration_is_strict_and_json_compatible() {
    let f = Fixture::new("public-selection-config");
    let path = f.config_file();
    let mut value = serde_json::to_value(&f.c).unwrap();
    value.as_object_mut().unwrap().remove("public_selection");
    fs::write(&path, value.to_string()).unwrap();
    assert!(Config::load(&path).unwrap().public_selection.is_none());
    value["public_selection"] = Value::Null;
    fs::write(&path, value.to_string()).unwrap();
    assert!(Config::load(&path).unwrap().public_selection.is_none());
    let exact = json!({"provider":f.c.provider,"model":f.c.model,"thinking":f.c.thinking});
    value["public_selection"] = exact.clone();
    fs::write(&path, value.to_string()).unwrap();
    assert!(Config::load(&path).unwrap().public_selection.is_some());
    let mut invalid = vec![json!(true), json!({})];
    for key in ["provider", "model", "thinking"] {
        let mut partial = exact.clone();
        partial.as_object_mut().unwrap().remove(key);
        invalid.push(partial);
        let mut mismatch = exact.clone();
        mismatch[key] = json!("different");
        invalid.push(mismatch);
    }
    let mut extra = exact.clone();
    extra["other_control"] = json!("not-allowed");
    invalid.push(extra);
    for declaration in invalid {
        value["public_selection"] = declaration;
        fs::write(&path, value.to_string()).unwrap();
        assert_eq!(Config::load(&path).unwrap_err().code, "invalid_config");
    }
}

#[test]
fn credential_protocol_spelling_tool_and_long_identity_collisions_fail_safely() {
    for target in [
        "type",
        "mcp__fixture__read",
        "turn-0123456789abcdef",
        "magpie",
        "fixture-session-id",
    ] {
        let mut f = Fixture::new("normal");
        f.c.credential_env_keys = vec!["CRAFT_BRIDGE_ALLOWED_TEST_KEY".into()];
        let output = f.cli_with_env(&[("CRAFT_BRIDGE_ALLOWED_TEST_KEY", target)]);
        assert!(!output.status.success());
        let events = parse(&output.stdout);
        let failure = events
            .iter()
            .find(|v| v["type"] == "bridge_failure")
            .unwrap();
        assert_eq!(failure["code"], "credential_control_conflict");
        assert!(
            events
                .iter()
                .all(|v| v.get("type").and_then(Value::as_str).is_some())
        );
        assert!(!events.iter().any(|v| v["type"] == "bridge_session"
            || v["type"] == "bridge_complete" && v["success"] == true));
        // The literal "type" is unavoidable schema, but its spelling must remain
        // stable on safe refusal; long dynamic identities must never be emitted.
        if target.len() > 16 {
            assert!(!String::from_utf8_lossy(&output.stdout).contains(target));
        }
        if target != "fixture-session-id" {
            assert!(!f.c.agent_dir.join("commands.jsonl").exists());
        }
    }
}
#[cfg(windows)]
#[test]
fn actual_node_entry_and_resource_paths_use_friendly_absolute_spelling() {
    use craft_pi_bridge::config::{canonical, native_path};
    let mut f = Fixture::new("node-launch");
    f.c.pi.program = PathBuf::from(std::env::var_os("CRAFT_TEST_NODE").expect("CRAFT_TEST_NODE must be explicit"));
    f.c.pi.argv = vec![
        PathBuf::from(env!("CARGO_MANIFEST_DIR"))
            .join("tests/fixtures/fake_pi_node.cjs")
            .to_string_lossy()
            .into(),
    ];
    f.c.validate().unwrap();
    assert!(f.c.task_cwd.to_string_lossy().starts_with(r"\\?\"));
    assert!(!f.c.pi.argv[0].starts_with(r"\\?\"));
    let (r, events) = f.run();
    protocol_ok(&r);
    let proof: Value =
        serde_json::from_slice(&fs::read(f.c.agent_dir.join("node-launch-proof.json")).unwrap())
            .unwrap();
    for key in ["entry", "cwd", "agent", "sessionEnv", "sessionArg"] {
        let text = proof[key].as_str().unwrap();
        assert!(!text.starts_with(r"\\?\"));
        assert!(PathBuf::from(text).is_absolute());
    }
    assert_eq!(
        canonical(&PathBuf::from(proof["entry"].as_str().unwrap())).unwrap(),
        canonical(&PathBuf::from(&f.c.pi.argv[0])).unwrap()
    );
    assert_eq!(
        canonical(&PathBuf::from(proof["cwd"].as_str().unwrap())).unwrap(),
        f.c.task_cwd
    );
    assert_eq!(
        canonical(&PathBuf::from(proof["agent"].as_str().unwrap())).unwrap(),
        f.c.agent_dir
    );
    assert_eq!(
        canonical(&PathBuf::from(proof["sessionArg"].as_str().unwrap())).unwrap(),
        f.c.session_dir
    );
    assert_eq!(proof["instructions"], f.c.instructions);
    let session = events
        .iter()
        .find(|v| v["type"] == "bridge_session")
        .unwrap()["sessionFile"]
        .as_str()
        .unwrap();
    let mut c = f.c.clone();
    c.session_path = Some(PathBuf::from(session));
    let r = driver::run(c, "followup via actual Node".into(), Buffer::default());
    protocol_ok(&r);
    let proof: Value =
        serde_json::from_slice(&fs::read(f.c.agent_dir.join("node-launch-proof.json")).unwrap())
            .unwrap();
    assert!(!proof["resume"].as_str().unwrap().starts_with(r"\\?\"));
    assert_eq!(
        canonical(&PathBuf::from(proof["resume"].as_str().unwrap())).unwrap(),
        canonical(&PathBuf::from(session)).unwrap()
    );
    assert_eq!(
        native_path(&f.c.agent_dir).unwrap(),
        PathBuf::from(proof["agent"].as_str().unwrap())
    );
    assert!(native_path(&PathBuf::from(r"\\.\NUL")).is_err());
}
#[test]
fn credential_allowlist_passes_only_explicit_values() {
    let mut f = Fixture::new("credential-probe");
    f.c.credential_env_keys = vec!["CRAFT_BRIDGE_ALLOWED_TEST_KEY".into()];
    let output = f.cli_with_env(&[
        (
            "CRAFT_BRIDGE_ALLOWED_TEST_KEY",
            "fixture-allowed-not-real-key",
        ),
        (
            "CRAFT_BRIDGE_UNLISTED_TEST_KEY",
            "fixture-unlisted-not-real-key",
        ),
    ]);
    let events = parse(&output.stdout);
    let probe = events
        .iter()
        .find(|v| v["type"] == "bridge_progress" && v["event"] == "credential_probe")
        .unwrap();
    assert_eq!(probe["allowedMatches"], true);
    assert_eq!(probe["unlistedPresent"], false);
    #[cfg(windows)]
    assert!(output.status.success());
    for bytes in [&output.stdout, &output.stderr] {
        let text = String::from_utf8_lossy(bytes);
        assert!(
            !text.contains("fixture-allowed-not-real-key"),
            "credential value leaked"
        );
        assert!(
            !text.contains("fixture-unlisted-not-real-key"),
            "unlisted value leaked"
        );
    }
}
#[test]
fn credential_missing_and_empty_fail_before_child_without_values() {
    for environment in [vec![], vec![("CRAFT_BRIDGE_ALLOWED_TEST_KEY", "")]] {
        let mut f = Fixture::new("credential-probe");
        f.c.credential_env_keys = vec!["CRAFT_BRIDGE_ALLOWED_TEST_KEY".into()];
        let output = f.cli_with_env(&environment);
        assert!(!output.status.success());
        assert!(
            parse(&output.stdout)
                .iter()
                .any(|v| v["code"] == "credential_env_missing")
        );
        assert!(!f.c.agent_dir.join("commands.jsonl").exists());
        assert!(!String::from_utf8_lossy(&output.stdout).contains("fixture-allowed-not-real-key"));
    }
}
#[test]
fn invalid_and_reserved_credential_names_are_rejected_without_echo() {
    for (name, code) in [
        (
            "BAD=fixture-allowed-not-real-key",
            "invalid_credential_env_key",
        ),
        ("9BAD", "invalid_credential_env_key"),
        ("PI_CODING_AGENT_DIR", "reserved_credential_env_key"),
        ("Path", "reserved_credential_env_key"),
        ("TEMP", "reserved_credential_env_key"),
        ("NODE_OPTIONS", "reserved_credential_env_key"),
    ] {
        let mut f = Fixture::new("credential-probe");
        f.c.credential_env_keys = vec![name.into()];
        let output = f.cli_with_env(&[(
            "CRAFT_BRIDGE_UNLISTED_TEST_KEY",
            "fixture-unlisted-not-real-key",
        )]);
        assert!(!output.status.success());
        assert!(parse(&output.stdout).iter().any(|v| v["code"] == code));
        assert!(!f.c.agent_dir.join("commands.jsonl").exists());
        for bytes in [&output.stdout, &output.stderr] {
            let text = String::from_utf8_lossy(bytes);
            assert!(!text.contains("fixture-allowed-not-real-key"));
            assert!(!text.contains("fixture-unlisted-not-real-key"));
        }
    }
}
#[test]
fn credential_list_is_bounded_and_duplicate_names_refused() {
    let mut f = Fixture::new("normal");
    f.c.credential_env_keys = (0..33)
        .map(|i| format!("PROVIDER_CREDENTIAL_{i}"))
        .collect();
    assert_eq!(
        f.c.validate().unwrap_err().code,
        "invalid_credential_env_key"
    );
    f.c.credential_env_keys = vec!["PROVIDER_KEY".into(), "provider_key".into()];
    assert_eq!(
        f.c.validate().unwrap_err().code,
        "invalid_credential_env_key"
    );
}
#[test]
fn old_config_omitting_credentials_remains_empty() {
    let f = Fixture::new("normal");
    let mut v = serde_json::to_value(&f.c).unwrap();
    v.as_object_mut().unwrap().remove("credential_env_keys");
    let path = f.root.join("old-config.json");
    fs::write(&path, v.to_string()).unwrap();
    assert!(Config::load(&path).unwrap().credential_env_keys.is_empty());
}
#[test]
fn new_session_event_and_incremental_file_writes_do_not_race() {
    let (r, e) = Fixture::new("delayed-session").run();
    protocol_ok(&r);
    assert!(
        e.iter()
            .any(|v| v["type"] == "bridge_session" && v["headerVerified"] == true)
    );
}
#[test]
fn incomplete_session_tail_still_fails_after_disposal() {
    check_error("session-partial-tail", "session_corrupt");
}
#[cfg(windows)]
#[test]
fn post_spawn_ownership_failures_report_actual_cleanup() {
    for fault in [
        driver::SpawnFault::Snapshot,
        driver::SpawnFault::OpenThread,
        driver::SpawnFault::ResumeThread,
    ] {
        let f = Fixture::new("normal");
        let r = driver::run_with_spawn_fault(
            f.c.clone(),
            "approved task".into(),
            Buffer::default(),
            fault,
        );
        assert_eq!(r.failure.as_ref().unwrap().code, "ownership_failed");
        assert_eq!(r.cleanup.scope, "windows_job");
        assert_ne!(r.cleanup.status, "not_started");
        assert_eq!(r.cleanup.status, "verified", "{r:?}");
        assert!(r.cleanup.root_exited && r.cleanup.members_empty && r.cleanup.hard_terminated);
        assert!(!f.c.agent_dir.join("commands.jsonl").exists());
    }
}
#[cfg(windows)]
#[test]
fn unconfirmed_startup_cleanup_remains_unknown() {
    let mut f = Fixture::new("normal");
    f.c.deadlines.hard_kill_ms = 100;
    let r = driver::run_with_spawn_fault(
        f.c,
        "approved task".into(),
        Buffer::default(),
        driver::SpawnFault::SnapshotUnconfirmedCleanup,
    );
    assert!(!r.success);
    assert_eq!(r.cleanup.status, "unknown");
    assert_eq!(r.cleanup.scope, "windows_job");
    assert!(r.cleanup.hard_terminated);
    assert!(!r.cleanup.members_empty);
}
#[test]
fn preflight_error_exits_when_stdout_is_open_and_unread() {
    let f = Fixture::new("normal");
    let mut v = serde_json::to_value(&f.c).unwrap();
    v["unknown".repeat(40000)] = json!(true);
    let path = f.root.join("large-error.json");
    fs::write(&path, v.to_string()).unwrap();
    let mut child = Command::new(env!("CARGO_BIN_EXE_pi-rpc-driver"))
        .arg(path)
        .stdin(Stdio::null())
        .stdout(Stdio::piped())
        .stderr(Stdio::null())
        .spawn()
        .unwrap();
    let unread_stdout = child.stdout.take().unwrap();
    let deadline = Instant::now() + Duration::from_secs(2);
    let status = loop {
        if let Some(status) = child.try_wait().unwrap() {
            break status;
        }
        if Instant::now() >= deadline {
            let _ = child.kill();
            let _ = child.wait();
            panic!("preflight output blocked while its reader stayed open");
        }
        thread::sleep(Duration::from_millis(5));
    };
    drop(unread_stdout);
    assert_eq!(status.code(), Some(2));
    assert!(!f.c.agent_dir.join("commands.jsonl").exists());
}
#[test]
fn cli_input_limit_and_unknown_args() {
    let f = Fixture::new("normal");
    let path = f.config_file();
    let mut child = Command::new(env!("CARGO_BIN_EXE_pi-rpc-driver"))
        .arg(path)
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .spawn()
        .unwrap();
    let _ = child
        .stdin
        .take()
        .unwrap()
        .write_all(&vec![b'a'; 1024 * 1024 + 1]);
    let o = child.wait_with_output().unwrap();
    assert!(!o.status.success());
    assert!(parse(&o.stdout).iter().any(|v| v["code"] == "input_limit"));
    let o = Command::new(env!("CARGO_BIN_EXE_pi-rpc-driver"))
        .arg("--ssh")
        .output()
        .unwrap();
    assert!(!o.status.success());
    assert!(
        parse(&o.stdout)
            .iter()
            .any(|v| v["code"] == "invalid_arguments")
    );
}
