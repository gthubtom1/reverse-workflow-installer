//! Scripted protocol peer; never calls a provider. Scenarios are task text.
use serde_json::{Value, json};
use std::{
    fs,
    io::{self, BufRead, Write},
    path::PathBuf,
    process::{self, Command, Stdio},
    thread,
    time::Duration,
};
fn emit(v: Value) {
    let mut o = io::stdout().lock();
    serde_json::to_writer(&mut o, &v).unwrap();
    o.write_all(
        b"
",
    )
    .unwrap();
    o.flush().unwrap();
}
fn main() {
    let args: Vec<String> = std::env::args().collect();
    if args
        .get(1)
        .is_some_and(|arg| arg == "--report-redaction" || arg == "--report-redaction-sink")
    {
        let config = craft_pi_bridge::config::Config::load(std::path::Path::new(&args[2])).unwrap();
        println!("config_debug={:?}", config.clone());
        let report = if args[1] == "--report-redaction-sink" {
            struct FailedSink(String);
            impl Write for FailedSink {
                fn write(&mut self, _: &[u8]) -> io::Result<usize> {
                    Err(io::Error::other(self.0.clone()))
                }
                fn flush(&mut self) -> io::Result<()> {
                    Ok(())
                }
            }
            craft_pi_bridge::driver::run(
                config,
                "approved task".into(),
                FailedSink(std::env::var("CRAFT_BRIDGE_ALLOWED_TEST_KEY").unwrap()),
            )
        } else {
            craft_pi_bridge::driver::run(config, "approved task".into(), io::stdout())
        };
        println!("report_debug={report:?}");
        println!("report_json={}", serde_json::to_string(&report).unwrap());
        return;
    }
    if args.get(1).is_some_and(|a| a == "--descendant") {
        let path = &args[2];
        loop {
            fs::write(path, b"alive").unwrap();
            thread::sleep(Duration::from_millis(25));
        }
    }
    let arg = |flag: &str| {
        args.iter()
            .position(|a| a == flag)
            .and_then(|i| args.get(i + 1))
            .cloned()
            .unwrap()
    };
    let root = PathBuf::from(arg("--session-dir"));
    let agent = PathBuf::from(std::env::var("PI_CODING_AGENT_DIR").unwrap());
    let scenario = fs::read_to_string(agent.join("scenario")).unwrap_or_default();
    if scenario == "credential-probe" {
        emit(
            json!({"type":"credential_probe", "allowedMatches": std::env::var("CRAFT_BRIDGE_ALLOWED_TEST_KEY").ok().as_deref() == Some("fixture-allowed-not-real-key"), "unlistedPresent": std::env::var_os("CRAFT_BRIDGE_UNLISTED_TEST_KEY").is_some()}),
        );
    }
    if scenario.starts_with("credential-echo") {
        // Fixture learns the synthetic value only through its environment. Never
        // write it to a config, fixture input file, argv or persisted history.
        let value = std::env::var("CRAFT_BRIDGE_ALLOWED_TEST_KEY").unwrap();
        let diagnostic = json!({"type":"credential_diagnostic", "message":format!("provider diagnostic: {value}"), "nested":{"value":value}});
        for byte in diagnostic.to_string().as_bytes() {
            io::stdout().write_all(&[*byte]).unwrap();
            io::stdout().flush().unwrap();
        }
        io::stdout().write_all(b"\n").unwrap();
        io::stdout().flush().unwrap();
        io::stderr().write_all(&[0xff, 0x00]).unwrap();
        for byte in value.as_bytes() {
            io::stderr().write_all(&[*byte]).unwrap();
            io::stderr().flush().unwrap();
            thread::sleep(Duration::from_millis(1));
        }
        let escaped = serde_json::to_string(&value).unwrap();
        io::stderr().write_all(b"; escaped=").unwrap();
        for chunk in escaped.as_bytes()[1..escaped.len() - 1].chunks(3) {
            io::stderr().write_all(chunk).unwrap();
            io::stderr().flush().unwrap();
            thread::sleep(Duration::from_millis(1));
        }
        io::stderr().write_all(b"; truncated=").unwrap();
        io::stderr()
            .write_all(&value.as_bytes()[..value.len() / 2])
            .unwrap();
        io::stderr().flush().unwrap();
    }
    if scenario == "early-exit" {
        process::exit(0);
    }
    if scenario == "no-read" {
        thread::sleep(Duration::from_secs(30));
        return;
    }
    let file = args
        .iter()
        .position(|a| a == "--session")
        .map(|i| PathBuf::from(&args[i + 1]))
        .unwrap_or(root.join("actual-not-guessed.jsonl"));
    let cwd = std::env::current_dir().unwrap();
    let id = "fixture-session-id";
    let stdin = io::stdin();
    let mut clear = false;
    let mut prompted = false;
    let mut descendant = None;
    for line in stdin.lock().lines() {
        let v: Value = serde_json::from_str(&line.unwrap()).unwrap();
        let kind = v["type"].as_str().unwrap();
        if kind == "extension_ui_response" {
            fs::write(agent.join("ui-response"), v.to_string()).unwrap();
            continue;
        }
        let response = |data: Value| json!({"type":"response","id":v["id"],"command":kind,"success":true,"data":data});
        fs::OpenOptions::new()
            .create(true)
            .append(true)
            .open(agent.join("commands.jsonl"))
            .unwrap()
            .write_all(
                format!(
                    "{kind}
"
                )
                .as_bytes(),
            )
            .unwrap();
        match kind {
            "set_model" if scenario == "credential-echo-error" => emit(
                json!({"type":"response","id":v["id"],"command":kind,"success":false,"error":format!("provider rejected credential {}", std::env::var("CRAFT_BRIDGE_ALLOWED_TEST_KEY").unwrap())}),
            ),
            "set_model" if scenario == "response-error" => emit(
                json!({"type":"response","id":v["id"],"command":kind,"success":false,"error":"fixture model unavailable"}),
            ),
            "get_state" => {
                if scenario == "command-timeout" {
                    continue;
                }
                let model = if scenario == "wrong-state-model" {
                    "wrong"
                } else {
                    "gpt/gpt-6.1-sol"
                };
                let s = if scenario == "wrong-state-session" {
                    root.parent().unwrap().join("escaped.jsonl")
                } else {
                    file.clone()
                };
                let mut r = response(
                    json!({"model":{"provider":"magpie","id":model},"thinkingLevel":"high","isStreaming":false,"isCompacting":false,"pendingMessageCount":0,"sessionId":id,"sessionFile":s}),
                );
                if scenario == "credential-id-collision" {
                    r["data"]["sessionId"] =
                        json!(std::env::var("CRAFT_BRIDGE_ALLOWED_TEST_KEY").unwrap());
                }
                if scenario == "bad-response-id" {
                    r["id"] = json!("foreign");
                }
                if scenario == "close-input" {
                    #[cfg(windows)]
                    {
                        use std::os::windows::io::AsRawHandle;
                        unsafe {
                            windows_sys::Win32::Foundation::CloseHandle(
                                io::stdin().as_raw_handle() as _,
                            );
                        }
                    }
                    #[cfg(unix)]
                    unsafe {
                        libc::close(libc::STDIN_FILENO);
                    }
                    emit(r);
                    thread::sleep(Duration::from_secs(30));
                    return;
                }
                emit(r);
            }
            "prompt" => {
                prompted = true;
                let disposition = match scenario.as_str() {
                    "queued" => "queued",
                    "handled" => "handled",
                    _ => "started",
                };
                if scenario != "lost-session" && scenario != "delayed-session" {
                    let h = json!({"type":"session","version":3,"id":id,"timestamp":"2026-11-09T00:00:00Z","cwd":if scenario=="wrong-cwd"{root.clone()}else{cwd.clone()}});
                    if !file.exists() {
                        fs::write(
                            &file,
                            format!(
                                "{h}
"
                            ),
                        )
                        .unwrap();
                    }
                }
                emit(response(json!({"disposition":disposition})));
                if scenario == "delayed-session" {
                    emit(json!({"type":"agent_start"}));
                    thread::sleep(Duration::from_millis(20));
                    let mut history = fs::File::create(&file).unwrap();
                    emit(
                        json!({"type":"message_start", "message":{"role":"user","content":"approved task"}}),
                    );
                    thread::sleep(Duration::from_millis(20));
                    let mut header = json!({"type":"session","version":3,"id":id,"timestamp":"2026-11-09T00:00:00Z","cwd":cwd}).to_string().into_bytes();
                    header.push(b'\n');
                    let half = header.len() / 2;
                    history.write_all(&header[..half]).unwrap();
                    history.flush().unwrap();
                    emit(
                        json!({"type":"message_end", "message":{"role":"user","content":"approved task"}}),
                    );
                    thread::sleep(Duration::from_millis(20));
                    history.write_all(&header[half..]).unwrap();
                    let entry = b"{\"type\":\"message\",\"message\":{\"role\":\"user\",\"content\":\"fixture\"}}\n";
                    history.write_all(&entry[..entry.len() / 2]).unwrap();
                    history.flush().unwrap();
                    emit(
                        json!({"type":"message_update","assistantMessageEvent":{"type":"text_delta","delta":"persisting"}}),
                    );
                    thread::sleep(Duration::from_millis(20));
                    history.write_all(&entry[entry.len() / 2..]).unwrap();
                    history.flush().unwrap();
                }
                if scenario == "session-partial-tail" {
                    fs::OpenOptions::new()
                        .append(true)
                        .open(&file)
                        .unwrap()
                        .write_all(b"{")
                        .unwrap();
                }
                if [
                    "queued",
                    "handled",
                    "hang",
                    "hard-cancel",
                    "descendant",
                    "cancel",
                ]
                .contains(&scenario.as_str())
                {
                    if scenario == "descendant" {
                        descendant = Some(
                            Command::new(std::env::current_exe().unwrap())
                                .args(["--descendant", agent.join("heartbeat").to_str().unwrap()])
                                .stdin(Stdio::null())
                                .stdout(Stdio::null())
                                .stderr(Stdio::null())
                                .spawn()
                                .unwrap(),
                        );
                    }
                    continue;
                }
                emit(json!({"type":"agent_start"}));
                if scenario.starts_with("credential-deltas") {
                    let value = std::env::var("CRAFT_BRIDGE_ALLOWED_TEST_KEY").unwrap();
                    let half = value
                        .char_indices()
                        .nth(value.chars().count() / 2)
                        .unwrap()
                        .0;
                    for kind in ["text_delta", "thinking_delta", "toolcall_delta"] {
                        for part in [&value[..half], &value[half..]] {
                            emit(
                                json!({"type":"message_update","assistantMessageEvent":{"type":kind,"delta":part,"contentIndex":0}}),
                            );
                        }
                    }
                    emit(
                        json!({"type":"message_start","message":{"role":"assistant","content":[{"type":"text","text":&value[..half]}]}}),
                    );
                    emit(
                        json!({"type":"tool_execution_update","toolCallId":"tool-1","toolName":"mcp__fixture__read","partialResult":{"content":[{"type":"text","text":&value[half..]}]}}),
                    );
                    if scenario == "credential-deltas-eof" {
                        return;
                    }
                }
                if scenario == "bad-json" {
                    print!(
                        "not-json
"
                    );
                    io::stdout().flush().unwrap();
                    continue;
                }
                if scenario == "invalid-utf8" {
                    io::stdout().write_all(&[0xff, b'\n']).unwrap();
                    io::stdout().flush().unwrap();
                    continue;
                }
                if scenario == "truncated" {
                    print!("{}", r#"{"type":"agent_end"}"#);
                    io::stdout().flush().unwrap();
                    return;
                }
                if scenario == "record-limit" {
                    io::stdout()
                        .write_all(&vec![b'x'; 1024 * 1024 + 2])
                        .unwrap();
                    io::stdout().flush().unwrap();
                    continue;
                }
                if scenario == "stderr-flood" {
                    io::stderr().write_all(&vec![b'd'; 256 * 1024]).unwrap();
                }
                if scenario == "ui" {
                    emit(
                        json!({"type":"extension_ui_request","id":"deny-me","method":"confirm","title":"approval"}),
                    );
                    continue;
                }
                let delta = json!({"type":"message_update","usage":{"totalTokens":9999},"assistantMessageEvent":{"type":"text_delta","delta":"你好🙂 line end"}});
                if scenario == "utf8" {
                    let mut bytes = delta.to_string().into_bytes();
                    bytes.extend(
                        b"
",
                    );
                    for byte in bytes {
                        io::stdout().write_all(&[byte]).unwrap();
                        io::stdout().flush().unwrap();
                    }
                } else {
                    emit(delta);
                }
                emit(
                    json!({"type":"tool_execution_start","toolCallId":"tool-1","toolName":if scenario=="unexpected-tool"{"bash"}else{"mcp__fixture__read"},"args":{"path":"a"}}),
                );
                emit(
                    json!({"type":"tool_execution_end","toolCallId":"tool-1","toolName":"mcp__fixture__read","result":{"content":[]},"isError":false}),
                );
                let model = if scenario == "wrong-final-model" {
                    "other"
                } else {
                    "gpt/gpt-6.1-sol"
                };
                let stop = match scenario.as_str() {
                    "exit0-error" => "error",
                    "length" => "length",
                    "deferred" => "deferred",
                    _ => "stop",
                };
                let mut message = json!({"role":"assistant","content":[{"type":"text","text":"done"}],"api":"fixture","provider":"magpie","model":model,"thinkingLevel":"high","stopReason":stop,"timestamp":123,"responseId":"response-1","usage":{"input":10,"output":5,"cacheRead":2,"cacheWrite":3,"totalTokens":20,"cost":{"total":0.1}}});
                if scenario == "credential-deltas" {
                    let value = std::env::var("CRAFT_BRIDGE_ALLOWED_TEST_KEY").unwrap();
                    let half = value
                        .char_indices()
                        .nth(value.chars().count() / 2)
                        .unwrap()
                        .0;
                    message["content"] = json!([{"type":"text","text":&value[..half]},{"type":"text","text":&value[half..]}]);
                    emit(
                        json!({"type":"message_end","message":{"role":"toolResult","toolCallId":"tool-1","toolName":"mcp__fixture__read","content":message["content"].clone()}}),
                    );
                }
                if scenario.starts_with("credential-echo") {
                    message["content"][0]["text"] =
                        json!(std::env::var("CRAFT_BRIDGE_ALLOWED_TEST_KEY").unwrap());
                }
                if scenario == "wrong-thinking" {
                    message["thinkingLevel"] = json!("low");
                }
                if scenario == "wrong-response-model" {
                    message["responseModel"] = json!("other");
                }
                if scenario != "no-final" {
                    emit(json!({"type":"message_end","message":message}));
                }
                if scenario == "duplicate-usage" {
                    emit(json!({"type":"message_end","message":message}));
                    emit(json!({"type":"turn_end","message":message}));
                }
                emit(json!({"type":"agent_end","messages":[message],"willRetry":false}));
                if scenario != "missing-settled" {
                    emit(json!({"type":"agent_settled","aborted":scenario=="aborted-settled"}));
                }
                if scenario == "exit7" {
                    process::exit(7);
                }
                if scenario == "missing-settled" {
                    return;
                }
                if scenario == "after-settled" {
                    emit(json!({"type":"agent_start"}));
                }
                if scenario == "delete-on-exit" {
                    fs::remove_file(&file).unwrap();
                }
            }
            "clear_queue" => {
                if scenario == "hard-cancel" {
                    continue;
                }
                clear = true;
                emit(response(
                    json!({"steering":["stale queued task"],"followUp":[]}),
                ));
            }
            "abort" => {
                if scenario == "hard-cancel" {
                    continue;
                }
                if !clear {
                    fs::write(agent.join("queue-ran"), b"bad").unwrap();
                }
                emit(json!({"type":"agent_settled","aborted":true}));
                emit(response(Value::Null));
            }
            _ => emit(response(Value::Null)),
        }
    }
    if scenario == "exit7-after-eof" {
        process::exit(7);
    }
    if ["exit-hang", "hard-cancel"].contains(&scenario.as_str()) && prompted {
        thread::sleep(Duration::from_secs(30));
    }
    // A child deliberately survives normal EOF; the owned job must kill it.
    if let Some(child) = descendant {
        std::mem::forget(child);
    }
}
