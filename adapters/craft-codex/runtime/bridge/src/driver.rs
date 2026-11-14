use crate::{
    config::{self, Config, BUILDER_NAMESPACE, BUILDER_TOOLS, MAX_RECORD, MAX_STREAM, MAX_TASK},
    parser::{failure_event, TurnReport, Usage},
    process::{Cleanup, Owned},
    session::{self, ThreadReceipt},
    Failure, Result,
};
use serde_json::{json, Value};
use std::{
    collections::{BTreeMap, HashMap, HashSet},
    fs::{self, OpenOptions},
    io::{BufRead, BufReader, BufWriter, Read, Write},
    path::{Path, PathBuf},
    process::{Command, Stdio},
    sync::mpsc::{self, Receiver},
    thread,
    time::{Duration, Instant},
};

fn ms(value: u64) -> Duration {
    Duration::from_millis(value)
}

fn fail(code: &str, detail: impl ToString) -> Failure {
    Failure::new(code, detail)
}

struct LineChild {
    owned: Owned,
    stdin: Option<BufWriter<std::process::ChildStdin>>,
    lines: Receiver<Result<Option<Value>>>,
    stderr_done: Receiver<()>,
}

impl LineChild {
    fn spawn(
        program: &std::path::Path,
        args: &[String],
        cwd: &std::path::Path,
        home: Option<&std::path::Path>,
        timeout: Duration,
    ) -> Result<Self> {
        let mut command = Command::new(config::native_path(program)?);
        command
            .args(args)
            .current_dir(config::native_path(cwd)?)
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::piped())
            .env_clear();

        for name in [
            "PATH", "SystemRoot", "WINDIR", "COMSPEC", "PATHEXT", "TEMP", "TMP", "TMPDIR",
            "LANG", "LC_ALL",
        ] {
            if let Some(value) = std::env::var_os(name) {
                command.env(name, value);
            }
        }
        if let Some(home) = home {
            command.env("CODEX_HOME", config::native_path(home)?);
        }

        let mut owned = Owned::spawn(&mut command, timeout, None)
            .map_err(|failure| failure.failure)?;
        let stdin = Some(BufWriter::new(
            owned
                .child
                .stdin
                .take()
                .ok_or_else(|| fail("spawn_failed", "child stdin unavailable"))?,
        ));
        let stdout = owned
            .child
            .stdout
            .take()
            .ok_or_else(|| fail("spawn_failed", "child stdout unavailable"))?;
        let stderr = owned
            .child
            .stderr
            .take()
            .ok_or_else(|| fail("spawn_failed", "child stderr unavailable"))?;

        let (tx, lines) = mpsc::sync_channel(32);
        thread::spawn(move || {
            let mut reader = BufReader::new(stdout);
            let mut line = String::new();
            loop {
                line.clear();
                match reader.read_line(&mut line) {
                    Ok(0) => {
                        let _ = tx.send(Ok(None));
                        break;
                    }
                    Ok(size) if size > MAX_RECORD => {
                        let _ = tx.send(Err(fail("record_limit", "JSONL record exceeded")));
                        break;
                    }
                    Ok(_) => {
                        let text = line.trim_end_matches(['\r', '\n']);
                        if text.len() > MAX_RECORD {
                            let _ = tx.send(Err(fail("record_limit", "JSONL record exceeded")));
                            break;
                        }
                        let value = serde_json::from_str::<Value>(text)
                            .map(Some)
                            .map_err(|error| fail("bad_json", error));
                        if tx.send(value).is_err() {
                            break;
                        }
                    }
                    Err(error) => {
                        let _ = tx.send(Err(fail("pipe_read_failed", error)));
                        break;
                    }
                }
            }
        });

        let (stderr_tx, stderr_done) = mpsc::channel();
        thread::spawn(move || {
            let mut reader = BufReader::new(stderr);
            let mut total = 0usize;
            let mut buffer = [0u8; 8192];
            loop {
                match reader.read(&mut buffer) {
                    Ok(0) => break,
                    Ok(size) => {
                        total = total.saturating_add(size);
                        if total > MAX_STREAM {
                            break;
                        }
                    }
                    Err(_) => break,
                }
            }
            let _ = stderr_tx.send(());
        });

        Ok(Self {
            owned,
            stdin,
            lines,
            stderr_done,
        })
    }

    fn send(&mut self, value: Value) -> Result<()> {
        let Some(stdin) = &mut self.stdin else {
            return Err(fail("command_write_failed", "stdin closed"));
        };
        serde_json::to_writer(&mut *stdin, &value)
            .map_err(|error| fail("command_write_failed", error))?;
        stdin
            .write_all(b"\n")
            .map_err(|error| fail("command_write_failed", error))?;
        stdin
            .flush()
            .map_err(|error| fail("command_write_failed", error))
    }

    fn receive(&self, deadline: Instant, code: &str) -> Result<Value> {
        self.receive_cancelable(deadline, code, || Ok(false))?
            .ok_or_else(|| fail("cancelled", "cancel requested while receiving app-server output"))
    }

    fn receive_cancelable<F>(&self, deadline: Instant, code: &str, mut cancelled: F) -> Result<Option<Value>>
    where
        F: FnMut() -> Result<bool>,
    {
        loop {
            if cancelled()? {
                return Ok(None);
            }
            let remaining = deadline
                .checked_duration_since(Instant::now())
                .ok_or_else(|| fail(code, "deadline exceeded"))?;
            match self.lines.recv_timeout(remaining.min(Duration::from_millis(25))) {
                Ok(Ok(Some(value))) => return Ok(Some(value)),
                Ok(Ok(None)) => return Err(fail("app_server_eof", "server closed stdout")),
                Ok(Err(error)) => return Err(error),
                Err(mpsc::RecvTimeoutError::Timeout) => continue,
                Err(_) => return Err(fail("app_server_eof", "server output unavailable")),
            }
        }
    }

    fn cleanup(&mut self, deadline: Instant) -> (Cleanup, bool) {
        self.stdin.take();
        while Instant::now() < deadline {
            let cleanup = self.owned.cleanup();
            if cleanup.root_exited && cleanup.members_empty {
                let mut stdout_closed = false;
                while let Ok(message) = self.lines.recv_timeout(Duration::from_millis(5)) {
                    match message {
                        Ok(Some(_)) => {}
                        Ok(None) => {
                            stdout_closed = true;
                            break;
                        }
                        Err(_) => break,
                    }
                }
                let stderr_closed = self.stderr_done.recv_timeout(Duration::from_millis(5)).is_ok();
                return (cleanup, stdout_closed && stderr_closed);
            }
            thread::sleep(Duration::from_millis(5));
        }
        self.owned.terminate();
        (self.owned.cleanup(), false)
    }
}

struct McpClient {
    child: LineChild,
    next_id: u64,
    tools: HashMap<String, Value>,
}

impl McpClient {
    fn start(config: &Config) -> Result<Self> {
        let child = LineChild::spawn(
            &config.mcp.program,
            &config.mcp.argv,
            &config.task_cwd,
            None,
            ms(config.deadlines.hard_kill_ms),
        )?;
        let mut client = Self {
            child,
            next_id: 0,
            tools: HashMap::new(),
        };
        let result = (|| {
            client.request(
                "initialize",
                json!({
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "craft-codex-executor", "version": "1"}
                }),
                Instant::now() + ms(config.deadlines.command_ms),
            )?;
            client.child.send(json!({
                "jsonrpc": "2.0",
                "method": "notifications/initialized",
                "params": {}
            }))?;
            let listed = client.request(
                "tools/list",
                json!({}),
                Instant::now() + ms(config.deadlines.command_ms),
            )?;
            let tools = listed["tools"]
                .as_array()
                .ok_or_else(|| fail("mcp_protocol", "tools/list missing tools"))?;
            for tool in tools {
                if let Some(name) = tool["name"].as_str() {
                    client.tools.insert(name.to_owned(), tool.clone());
                }
            }
            let expected: Vec<&str> = BUILDER_TOOLS
                .iter()
                .map(|tool| tool.strip_prefix("mcp__craft__").unwrap())
                .collect();
            if client.tools.len() != expected.len()
                || expected.iter().any(|name| !client.tools.contains_key(*name))
            {
                return Err(fail("tool_denied", "MCP directory differs from six bounded tools"));
            }
            Ok::<(), Failure>(())
        })();
        if let Err(error) = result {
            let (cleanup, pipes) = client.child.cleanup(Instant::now() + ms(config.deadlines.shutdown_ms));
            if !pipes || cleanup.status != "verified" {
                return Err(fail("cleanup_unknown", format!("MCP cleanup failed after startup error: {}", error.detail)));
            }
            return Err(error);
        }
        Ok(client)
    }

    fn request(&mut self, method: &str, params: Value, deadline: Instant) -> Result<Value> {
        self.next_id += 1;
        let id = self.next_id;
        self.child.send(json!({
            "jsonrpc": "2.0",
            "id": id,
            "method": method,
            "params": params
        }))?;
        loop {
            let value = self.child.receive(deadline, "command_deadline")?;
            if value.get("id").and_then(Value::as_u64) != Some(id) {
                continue;
            }
            if value.get("error").is_some() {
                return Err(fail("mcp_call_failed", "MCP returned a JSON-RPC error"));
            }
            return Ok(value["result"].clone());
        }
    }

    fn dynamic_tools(&self) -> Value {
        let tools = self
            .tools
            .values()
            .map(|tool| {
                json!({
                    "type": "function",
                    "name": tool["name"],
                    "description": tool["description"],
                    "inputSchema": tool.get("inputSchema").cloned().unwrap_or_else(|| json!({"type": "object"}))
                })
            })
            .collect::<Vec<_>>();
        json!([{
            "type": "namespace",
            "name": BUILDER_NAMESPACE,
            "description": "Craft bounded Builder tools",
            "tools": tools
        }])
    }

    fn call(&mut self, raw: &str, arguments: Value, deadline: Instant) -> Result<Value> {
        if !self.tools.contains_key(raw) {
            return Err(fail("unexpected_tool", raw));
        }
        self.request(
            "tools/call",
            json!({"name": raw, "arguments": arguments}),
            deadline,
        )
    }
}

fn emit(writer: &mut impl Write, value: &Value) -> Result<()> {
    serde_json::to_writer(&mut *writer, value).map_err(|error| fail("output_write_failed", error))?;
    writer
        .write_all(b"\n")
        .map_err(|error| fail("output_write_failed", error))?;
    writer
        .flush()
        .map_err(|error| fail("output_write_failed", error))
}

fn progress(writer: &mut impl Write, kind: &str, value: &Value) -> Result<()> {
    emit(
        writer,
        &json!({"type": "bridge_progress", "kind": kind, "bytes": value.to_string().len()}),
    )
}

fn mcp_result_success(value: &Value) -> bool {
    !value["isError"].as_bool().unwrap_or(false)
}
fn effective_mcp_names(config_read: &Value) -> Result<Vec<String>> {
    let table = config_read["config"]["mcp_servers"].as_object().cloned().unwrap_or_default();
    let mut names = table.keys().cloned().collect::<Vec<_>>();
    names.sort();
    for name in &names { config::validate_mcp_server_name(name).map_err(|error| fail(&error.code, error.detail))?; }
    Ok(names)
}

fn canonical_value(value: &Value) -> Value {
    match value {
        Value::Object(object) => {
            let mut sorted = BTreeMap::new();
            for (key, value) in object { sorted.insert(key.clone(), canonical_value(value)); }
            Value::Object(sorted.into_iter().collect())
        }
        Value::Array(values) => Value::Array(values.iter().map(canonical_value).collect()),
        other => other.clone(),
    }
}

fn value_hash(value: &Value) -> Result<String> {
    Ok(config::hash_bytes(&serde_json::to_vec(&canonical_value(value)).map_err(|e| fail("config_unknown", e))?))
}

fn source_path_from_layer(name: &Value) -> Result<Option<(String, PathBuf)>> {
    let kind = name["type"].as_str().ok_or_else(|| fail("config_unknown", "config/read layer type missing"))?;
    match kind {
        "system" | "user" | "legacyManagedConfigTomlFromFile" | "packagedDefaults" => {
            let path = name["file"].as_str().ok_or_else(|| fail("config_unknown", "file-backed config layer source missing"))?;
            Ok(Some((kind.to_owned(), PathBuf::from(path))))
        }
        "project" => {
            let folder = name["dotCodexFolder"].as_str().ok_or_else(|| fail("config_unknown", "project layer source missing"))?;
            Ok(Some((kind.to_owned(), PathBuf::from(folder).join("config.toml"))))
        }
        "sessionFlags" | "mdm" | "enterpriseManaged" | "legacyManagedConfigTomlFromMdm" => Ok(None),
        _ => Err(fail("config_unknown", format!("unknown config/read layer type: {kind}"))),
    }
}

fn source_identity(path: &Path) -> Result<Value> {
    if !path.is_absolute() || path.components().any(|c| matches!(c, std::path::Component::ParentDir)) {
        return Err(fail("config_unknown", "config/read source path must be absolute without parent traversal"));
    }
    // Reject links independently of Windows' ordinary versus verbatim spelling.
    for ancestor in path.ancestors() {
        if let Ok(metadata) = fs::symlink_metadata(ancestor) {
            #[cfg(windows)]
            let reparse = {
                use std::os::windows::fs::MetadataExt;
                metadata.file_attributes() & 0x400 != 0
            };
            #[cfg(not(windows))]
            let reparse = false;
            if metadata.file_type().is_symlink() || reparse {
                return Err(fail("config_unknown", "config/read source traverses a link or reparse point"));
            }
        }
    }
    match fs::symlink_metadata(path) {
        Ok(_) => {
            let canonical = config::canonical(path).map_err(|error| fail(&error.code, error.detail))?;
            if !canonical.is_file() { return Err(fail("config_unknown", "config/read source is not a regular file")); }
            Ok(json!({"path": canonical, "exists": true, "sha256": config::hash_file(&canonical).map_err(|error| fail(&error.code, error.detail))?}))
        }
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => {
            Ok(json!({"path": path, "exists": false, "sha256": Value::Null}))
        }
        Err(_) => Err(fail("config_unknown", "config/read source metadata cannot be inspected")),
    }
}

fn config_graph_identity(config_read: &Value, inputs: &[config::ConfigInput]) -> Result<Value> {
    // wait_plain_response already strips the JSON-RPC envelope. Identity is
    // exclusively ConfigReadResponse semantic data, never the changing RPC id.
    let result = config_read;
    let actual_config = result.get("config").filter(|v| v.is_object()).ok_or_else(|| fail("config_unknown", "config/read config missing"))?;
    let layers = result.get("layers").and_then(Value::as_array).ok_or_else(|| fail("config_unknown", "config/read layers missing"))?;
    let origins = result.get("origins").ok_or_else(|| fail("config_unknown", "config/read origins missing"))?;
    let names = effective_mcp_names(config_read)?;
    let mcp_object = result["config"]["mcp_servers"].as_object().cloned().unwrap_or_default();
    let mcp_set = names.iter().map(|name| json!({"name": name, "enabled": mcp_object[name].get("enabled").cloned().unwrap_or(Value::Null)})).collect::<Vec<_>>();
    let mut sources = Vec::new();
    for layer in layers {
        let name = layer.get("name").ok_or_else(|| fail("config_unknown", "config/read layer name missing"))?;
        if let Some((kind, path)) = source_path_from_layer(name)? {
            let mut identity = source_identity(&path)?;
            identity["kind"] = json!(kind);
            identity["version"] = layer.get("version").cloned().unwrap_or(Value::Null);
            sources.push(identity);
        }
    }
    sources.sort_by_key(|value| value["path"].as_str().unwrap_or_default().to_owned());
    let static_inputs = inputs.iter().map(|input| json!({"path": input.path, "exists": input.exists, "sha256": input.sha256})).collect::<Vec<_>>();
    let config_sha256 = value_hash(actual_config)?;
    let layers_sha256 = value_hash(&Value::Array(layers.clone()))?;
    let origins_sha256 = value_hash(origins)?;
    let mcp_sha256 = value_hash(&Value::Array(mcp_set))?;
    let metadata = json!({"config_sha256": config_sha256, "layers_sha256": layers_sha256, "origins_sha256": origins_sha256, "mcp_sha256": mcp_sha256, "mcp_names": names, "sources": sources, "static_inputs": static_inputs});
    let fingerprint = value_hash(&metadata)?;
    Ok(json!({"version": 1, "fingerprint": fingerprint, "config_sha256": metadata["config_sha256"], "layers_sha256": metadata["layers_sha256"], "origins_sha256": metadata["origins_sha256"], "mcp_sha256": metadata["mcp_sha256"], "mcp_names": metadata["mcp_names"], "sources": metadata["sources"], "static_inputs": metadata["static_inputs"]}))
}

fn graph_mcp_names(identity: &Value) -> Result<Vec<String>> {
    identity["mcp_names"].as_array().ok_or_else(|| fail("config_unknown", "config graph MCP names missing"))?.iter().map(|value| value.as_str().map(ToOwned::to_owned).ok_or_else(|| fail("config_unknown", "config graph MCP name invalid"))).collect()
}

fn assert_config_graph(expected: &Value, actual: &Value) -> Result<()> {
    if expected == actual { Ok(()) } else { Err(fail("identity_mismatch", "Codex config graph changed during this turn")) }
}

fn config_identity_path(config: &Config) -> Result<PathBuf> {
    let parent = config.thread_receipt.parent().ok_or_else(|| fail("config_unknown", "thread receipt parent missing"))?;
    if !parent.is_dir() { return Err(fail("config_unknown", "thread receipt parent missing")); }
    Ok(parent.join("config-identity.json"))
}

fn establish_config_identity(config: &Config, identity: &Value) -> Result<()> {
    let path = config_identity_path(config)?;
    let bytes = serde_json::to_vec(identity).map_err(|e| fail("config_unknown", e))?;
    match OpenOptions::new().write(true).create_new(true).open(&path) {
        Ok(mut file) => { file.write_all(&bytes).map_err(|e| fail("config_identity_write", e))?; file.flush().map_err(|e| fail("config_identity_write", e))?; Ok(()) }
        Err(error) if error.kind() == std::io::ErrorKind::AlreadyExists => {
            let existing = config::read_bounded(fs::File::open(&path).map_err(|e| fail("config_identity_read", e))?, 128 * 1024)?;
            let existing: Value = serde_json::from_slice(&existing).map_err(|e| fail("config_identity_unknown", e))?;
            if existing == *identity { Ok(()) } else { Err(fail("identity_mismatch", "shared Codex config graph changed during this run")) }
        }
        Err(error) => Err(fail("config_identity_write", error)),
    }
}

fn read_config_graph(
    codex: &mut LineChild,
    mcp: &mut McpClient,
    state: &mut State,
    config: &Config,
    writer: &mut impl Write,
    deadline: Instant,
    next_id: &mut u64,
) -> Result<Value> {
    config.clone().validate().map_err(|error| fail(&error.code, error.detail))?;
    let request = send_request(codex, next_id, "config/read", json!({"cwd": config.task_cwd, "includeLayers": true}))?;
    let response = wait_plain_response(codex, mcp, request, state, config, writer, deadline, next_id)?;
    config_graph_identity(&response, &config.config_inputs)
}

fn thread_config(effort: &str, mcp_names: &[String]) -> Value {
    let mut config = json!({"model_reasoning_effort": effort});
    for name in mcp_names { config[format!("mcp_servers.{name}.enabled")] = json!(false); }
    config
}

fn validate_mcp_status(result: &Value, expected: &[String]) -> Result<()> {
    let data = result["data"].as_array().ok_or_else(|| fail("mcp_status_unknown", "thread-scoped MCP status data missing"))?;
    let mut seen = HashSet::new();
    for row in data {
        let name = row["name"].as_str().ok_or_else(|| fail("mcp_status_unknown", "MCP status name missing"))?;
        seen.insert(name.to_owned());
        if row["runtimeStatus"] != "disabled" || !row["toolsError"].is_null() { return Err(fail("mcp_status_active", "effective MCP server is not disabled")); }
    }
    if expected.iter().any(|name| !seen.contains(name)) { return Err(fail("mcp_status_unknown", "effective MCP server missing from thread-scoped status")); }
    Ok(())
}
fn thread_actual(result: &Value, config: &Config) -> Result<Value> {
    let model = result["model"]
        .as_str()
        .ok_or_else(|| fail("model_unknown", "thread response model missing"))?;
    let provider = result["modelProvider"]
        .as_str()
        .ok_or_else(|| fail("model_unknown", "thread response provider missing"))?;
    let effort = result["reasoningEffort"]
        .as_str()
        .ok_or_else(|| fail("model_unknown", "thread response reasoning effort missing"))?;
    let cwd = result["cwd"]
        .as_str()
        .ok_or_else(|| fail("model_unknown", "thread response cwd missing"))?;
    if model != config.model
        || provider != config.expected_provider
        || effort != config.effort
        || config::canonical(std::path::Path::new(cwd))
            .map_err(|_| fail("model_unknown", "thread response cwd invalid"))?
            != config.task_cwd
    {
        return Err(fail(
            "model_mismatch",
            "thread response model/provider/effort/cwd differs",
        ));
    }
    if result["approvalPolicy"] != "never"
        || result["sandbox"]["type"] != "readOnly"
        || result["sandbox"]["networkAccess"] != false
    {
        return Err(fail("policy_mismatch", "thread response sandbox/approval differs"));
    }
    Ok(json!({
        "provider": provider,
        "model": model,
        "effort": effort,
        "cwd": cwd,
        "sandbox": result["sandbox"],
        "approvalPolicy": result["approvalPolicy"]
    }))
}

fn usage(value: &Value) -> Result<Usage> {
    let total = &value["total"];
    let input = total["inputTokens"]
        .as_u64()
        .ok_or_else(|| fail("usage_unknown", "total inputTokens missing"))?;
    let output = total["outputTokens"]
        .as_u64()
        .ok_or_else(|| fail("usage_unknown", "total outputTokens missing"))?;
    let total_tokens = total["totalTokens"]
        .as_u64()
        .ok_or_else(|| fail("usage_unknown", "total totalTokens missing"))?;
    Ok(Usage {
        input,
        output,
        cache_read: total["cachedInputTokens"].as_u64(),
        cache_write: total["cacheWriteInputTokens"].as_u64(),
        total_tokens: Some(total_tokens),
        estimated_cost: None,
    })
}

fn text_from(value: &Value) -> Option<String> {
    if let Some(text) = value["text"].as_str() {
        return Some(text.to_owned());
    }
    let content = value["content"].as_array()?;
    let text = content
        .iter()
        .filter_map(|item| item["text"].as_str())
        .collect::<Vec<_>>()
        .join("");
    (!text.is_empty()).then_some(text)
}

fn allowed_notification(method: &str) -> bool {
    matches!(
        method,
        "thread/started"
            | "thread/status/changed"
            | "thread/tokenUsage/updated"
            | "turn/started"
            | "turn/completed"
            | "turn/plan/updated"
            | "turn/diff/updated"
            | "item/started"
            | "item/completed"
            | "item/agentMessage/delta"
            | "account/rateLimits/updated"
            | "remoteControl/status/changed"
            | "error"
            | "warning"
    )
}

struct State {
    thread_id: Option<String>,
    turn_id: Option<String>,
    pending: HashSet<String>,
    seen_calls: HashSet<String>,
    rejected: bool,
    cancel_sent: bool,
    owner_cancel: bool,
    interrupt_id: Option<u64>,
    interrupt_acknowledged: bool,
    interrupt_deadline: Option<Instant>,
    terminal: Option<Value>,
    usage: Option<Usage>,
    effect_dispatches: u64,
    text: String,
}

impl State {
    fn new(thread_id: Option<String>) -> Self {
        Self {
            thread_id,
            turn_id: None,
            pending: HashSet::new(),
            seen_calls: HashSet::new(),
            rejected: false,
            cancel_sent: false,
            owner_cancel: false,
            interrupt_id: None,
            interrupt_acknowledged: false,
            interrupt_deadline: None,
            terminal: None,
            usage: None,
            effect_dispatches: 0,
            text: String::new(),
        }
    }

    fn effects_open(&self) -> bool {
        !self.cancel_sent && !self.rejected && self.terminal.is_none()
    }

    fn bind_thread(&mut self, thread_id: &str) -> Result<()> {
        if thread_id.is_empty() {
            return Err(fail("turn_identity", "empty thread id"));
        }
        if let Some(expected) = &self.thread_id {
            if expected != thread_id {
                return Err(fail("turn_identity", "thread id mismatch"));
            }
        } else {
            self.thread_id = Some(thread_id.to_owned());
        }
        Ok(())
    }

    fn bind_turn(&mut self, turn_id: &str) -> Result<()> {
        if turn_id.is_empty() {
            return Err(fail("turn_identity", "empty turn id"));
        }
        if let Some(expected) = &self.turn_id {
            if expected != turn_id {
                return Err(fail("turn_identity", "turn id mismatch"));
            }
        } else {
            self.turn_id = Some(turn_id.to_owned());
        }
        Ok(())
    }

    fn bind_params(&mut self, params: &Value, require_turn: bool) -> Result<()> {
        let thread_id = params["threadId"]
            .as_str()
            .ok_or_else(|| fail("turn_identity", "threadId missing"))?;
        self.bind_thread(thread_id)?;
        if require_turn {
            let turn_id = params["turnId"]
                .as_str()
                .ok_or_else(|| fail("turn_identity", "turnId missing"))?;
            self.bind_turn(turn_id)?;
        }
        Ok(())
    }
}

fn send_interrupt(codex: &mut LineChild, state: &mut State, next_id: &mut u64, grace: Duration) -> Result<()> {
    if state.cancel_sent {
        return Ok(());
    }
    let thread_id = state
        .thread_id
        .clone()
        .ok_or_else(|| fail("turn_identity", "cannot interrupt without thread id"))?;
    let turn_id = state
        .turn_id
        .clone()
        .ok_or_else(|| fail("turn_identity", "cannot interrupt without turn id"))?;
    *next_id += 1;
    let interrupt_id = *next_id;
    codex.send(json!({
        "id": interrupt_id,
        "method": "turn/interrupt",
        "params": {"threadId": thread_id, "turnId": turn_id}
    }))?;
    state.interrupt_id = Some(interrupt_id);
    state.interrupt_deadline = Some(Instant::now() + grace);
    state.cancel_sent = true;
    Ok(())
}

fn reject_request(
    codex: &mut LineChild,
    state: &mut State,
    message: &Value,
    next_id: &mut u64,
    grace: Duration,
) -> Result<()> {
    if let Some(id) = message.get("id") {
        codex.send(json!({
            "id": id,
            "error": {"code": -32001, "message": "request rejected by codex-dynamic-bounded-v1"}
        }))?;
    }
    state.rejected = true;
    if !state.cancel_sent && state.terminal.is_none() && state.turn_id.is_some() {
        send_interrupt(codex, state, next_id, grace)?;
    }
    Ok(())
}

fn reserve_call(state: &mut State, call_id: &str) -> bool {
    state.seen_calls.insert(call_id.to_owned())
}
fn dynamic_response(
    codex: &mut LineChild,
    mcp: &mut McpClient,
    message: &Value,
    state: &mut State,
    deadline: Instant,
    next_id: &mut u64,
    grace: Duration,
    writer: &mut impl Write,
) -> Result<()> {
    let params = &message["params"];
    if !state.effects_open() {
        return reject_request(codex, state, message, next_id, grace);
    }
    state.bind_params(params, true)?;
    let namespace = params["namespace"]
        .as_str()
        .ok_or_else(|| fail("bad_tool_call", "namespace missing"))?;
    let raw = params["tool"]
        .as_str()
        .ok_or_else(|| fail("bad_tool_call", "tool missing"))?;
    let call_id = params["callId"]
        .as_str()
        .ok_or_else(|| fail("bad_tool_call", "callId missing"))?;
    if namespace != BUILDER_NAMESPACE
        || !BUILDER_TOOLS
            .iter()
            .any(|tool| tool.strip_prefix("mcp__craft__").unwrap() == raw)
        || !reserve_call(state, call_id)
    {
        return reject_request(codex, state, message, next_id, grace);
    }

    if !state.effects_open() {
        return reject_request(codex, state, message, next_id, grace);
    }
    state.effect_dispatches = state.effect_dispatches.saturating_add(1);
    state.pending.insert(call_id.to_owned());
    emit(
        writer,
        &json!({"type": "bridge_tool_started", "callId": call_id, "name": raw}),
    )?;
    let result = mcp.call(raw, params["arguments"].clone(), deadline);
    state.pending.remove(call_id);
    let (success, content) = match result {
        Ok(value) => {
            let success = mcp_result_success(&value);
            let content = serde_json::to_string(&value).unwrap_or_else(|_| "{}".to_owned());
            (success, content)
        }
        Err(error) => (false, error.detail),
    };
    codex.send(json!({
        "id": message["id"],
        "result": {
            "success": success,
            "contentItems": [{"type": "inputText", "text": content}]
        }
    }))?;
    emit(
        writer,
        &json!({"type": "bridge_tool_finished", "callId": call_id, "ok": success}),
    )
}

fn process_message(
    codex: &mut LineChild,
    mcp: &mut McpClient,
    message: &Value,
    state: &mut State,
    config: &Config,
    writer: &mut impl Write,
    deadline: Instant,
    next_id: &mut u64,
) -> Result<Option<Value>> {
    if message.get("method").is_some() {
        let method = message["method"].as_str().unwrap_or_default();
        if method == "item/tool/call" {
            if !state.cancel_sent && config.cancelled()? {
                state.owner_cancel = true;
                send_interrupt(codex, state, next_id, ms(config.deadlines.grace_ms))?;
            }
            dynamic_response(
                codex,
                mcp,
                message,
                state,
                deadline,
                next_id,
                ms(config.deadlines.grace_ms),
                writer,
            )?;
            return Ok(None);
        }
        if message.get("id").is_some() {
            reject_request(
                codex,
                state,
                message,
                next_id,
                ms(config.deadlines.grace_ms),
            )?;
            return Ok(None);
        }

        match method {
            "turn/started" => {
                let params = &message["params"];
                state.bind_params(params, false)?;
                let turn_id = params["turn"]["id"]
                    .as_str()
                    .ok_or_else(|| fail("turn_identity", "turn/started turn id missing"))?;
                state.bind_turn(turn_id)?;
            }
            "thread/tokenUsage/updated" => {
                let params = &message["params"];
                state.bind_params(params, true)?;
                state.usage = Some(usage(&params["tokenUsage"])?);
            }
            "turn/completed" => {
                let params = &message["params"];
                state.bind_params(params, false)?;
                let turn_id = params["turn"]["id"]
                    .as_str()
                    .ok_or_else(|| fail("turn_identity", "turn/completed turn id missing"))?;
                state.bind_turn(turn_id)?;
                if state.terminal.is_some() {
                    return Err(fail("turn_terminal", "duplicate turn/completed notification"));
                }
                state.terminal = Some(message.clone());
            }
            "item/agentMessage/delta" => {
                if let Some(delta) = message["params"]["delta"].as_str() {
                    state.text.push_str(delta);
                }
            }
            "item/completed" => {
                if message["params"]["item"]["type"] == "agentMessage" {
                    if let Some(text) = text_from(&message["params"]["item"]) {
                        state.text = text;
                    }
                }
            }
            _ => {}
        }
        if !allowed_notification(method) {
            return Err(fail(
                "unknown_notification",
                format!("unknown app-server notification: {method}"),
            ));
        }
        progress(writer, method, message)?;
        return Ok(None);
    }

    if message.get("id").is_some() {
        return Ok(Some(message.clone()));
    }
    Err(fail(
        "bad_protocol",
        "JSON-RPC message has neither method nor id",
    ))
}

fn send_request(
    codex: &mut LineChild,
    next_id: &mut u64,
    method: &str,
    params: Value,
) -> Result<u64> {
    *next_id += 1;
    codex.send(json!({"id": *next_id, "method": method, "params": params}))?;
    Ok(*next_id)
}

fn response_is(value: &Value, id: u64) -> bool {
    value.get("id").and_then(Value::as_u64) == Some(id)
}

fn wait_plain_response(
    codex: &mut LineChild,
    mcp: &mut McpClient,
    id: u64,
    state: &mut State,
    config: &Config,
    writer: &mut impl Write,
    deadline: Instant,
    next_id: &mut u64,
) -> Result<Value> {
    loop {
        let value = codex.receive(deadline, "command_deadline")?;
        if response_is(&value, id) {
            if value.get("error").is_some() {
                return Err(fail("app_server_error", "app-server response error"));
            }
            return Ok(value["result"].clone());
        }
        if let Some(response) = process_message(
            codex, mcp, &value, state, config, writer, deadline, next_id,
        )? {
            return Err(fail(
                "bad_response",
                format!("unexpected app-server response id: {}", response["id"]),
            ));
        }
    }
}

fn receive_deadline(turn_deadline: Instant, interrupt_deadline: Option<Instant>) -> Instant {
    interrupt_deadline.unwrap_or(turn_deadline)
}

fn terminal_status(state: &State) -> Option<&str> {
    state.terminal.as_ref()?.get("params")?.get("turn")?.get("status")?.as_str()
}

fn check_terminal(
    state: &State,
    report: &mut TurnReport,
) -> Result<Option<bool>> {
    if let Some(observed) = &state.usage {
        report.usage = observed.clone();
    }
    let Some(status) = terminal_status(state) else {
        return Ok(None);
    };
    if !state.pending.is_empty() {
        return Err(fail("tool_pending", "turn completed with pending tool calls"));
    }
    match status {
        "completed" => {
            if state.cancel_sent {
                return Err(fail(
                    "cancel_failed",
                    "turn completed normally after cancellation request",
                ));
            }
            let usage = state
                .usage
                .clone()
                .ok_or_else(|| fail("usage_unknown", "no actual thread token usage"))?;
            report.usage = usage;
            report.final_message = Some(json!({"text": state.text}));
            report.settled = true;
            report.terminal_acknowledged = true;
            Ok(Some(true))
        }
        "interrupted" => {
            report.terminal_acknowledged = true;
            if state.cancel_sent && state.interrupt_acknowledged {
                return Err(fail("cancelled", "turn interrupted after bounded cancellation"));
            }
            Ok(Some(false))
        }
        "failed" => Err(fail("turn_failed", "turn completed with failed status")),
        "inProgress" => Ok(None),
        _ => Err(fail("turn_failed", "unknown turn completion status")),
    }
}

pub fn run(
    config: Config,
    task: String,
    mut writer: impl Write + Send + 'static,
) -> TurnReport {
    let mut report = TurnReport {
        success: false,
        failure: None,
        cleanup: Cleanup::not_started(),
        child_exit: None,
        settled: false,
        final_message: None,
        actual_model: None,
        usage: Usage::default(),
        nested_usage: Usage::default(),
        cancel_acknowledged: false,
        terminal_acknowledged: false,
        thread_receipt: None,
    };
    if let Err(error) = run_inner(&config, &task, &mut writer, &mut report) {
        report.failure = Some(error);
    }
    report.success = report.failure.is_none()
        && report.settled
        && report.cleanup.status == "verified"
        && report.actual_model.is_some()
        && report.usage.total_tokens.is_some();
    if let Some(failure) = &report.failure {
        let _ = emit(&mut writer, &failure_event(failure));
    }
    let _ = emit(
        &mut writer,
        &json!({
            "type": "bridge_complete",
            "success": report.success,
            "cleanup": report.cleanup,
            "childExit": report.child_exit,
            "settled": report.settled,
            "finalMessage": report.final_message,
            "actualModel": report.actual_model,
            "usage": report.usage,
            "usageObserved": report.usage.total_tokens.is_some(),
            "nestedUsage": report.nested_usage,
            "cancelAcknowledged": report.cancel_acknowledged,
            "terminalAcknowledged": report.terminal_acknowledged
        }),
    );
    report
}

fn run_inner(
    config: &Config,
    task: &str,
    writer: &mut impl Write,
    report: &mut TurnReport,
) -> Result<()> {
    if task.trim().is_empty() || task.len() > MAX_TASK {
        return Err(fail("invalid_task", "nonempty UTF-8 task <= 1MiB required"));
    }
    if config.cancelled()? {
        return Err(fail("cancelled", "cancel marker matched before launch"));
    }

    let mut mcp = McpClient::start(config)?;
    let mut codex = match LineChild::spawn(
        &config.codex.program,
        &config.codex.argv,
        &config.task_cwd,
        Some(&config.codex_home),
        ms(config.deadlines.hard_kill_ms),
    ) {
        Ok(child) => child,
        Err(error) => {
            let (cleanup, pipes) =
                mcp.child
                    .cleanup(Instant::now() + ms(config.deadlines.shutdown_ms));
            report.cleanup = cleanup;
            if !pipes || report.cleanup.status != "verified" {
                report.cleanup.status = "unknown";
                return Err(fail("cleanup_unknown", "MCP cleanup failed after Codex startup error"));
            }
            return Err(error);
        }
    };

    let protocol = (|| -> Result<()> {
        let turn_deadline = Instant::now() + ms(config.deadlines.turn_ms);
        let mut next_id = 0u64;
        let init_id = send_request(
            &mut codex,
            &mut next_id,
            "initialize",
            json!({
                "clientInfo": {"name": "craft-codex-executor", "version": "1"},
                "capabilities": {"experimentalApi": true, "requiredHumanApproval": false}
            }),
        )?;
        let mut init_state = State::new(None);
        let _ = wait_plain_response(
            &mut codex,
            &mut mcp,
            init_id,
            &mut init_state,
            config,
            writer,
            turn_deadline,
            &mut next_id,
        )?;
        codex.send(json!({"method": "initialized", "params": {}}))?;

        let config_read_request = send_request(
            &mut codex,
            &mut next_id,
            "config/read",
            json!({"cwd": config.task_cwd, "includeLayers": true}),
        )?;
        let mut config_state = State::new(None);
        let config_read = wait_plain_response(
            &mut codex,
            &mut mcp,
            config_read_request,
            &mut config_state,
            config,
            writer,
            turn_deadline,
            &mut next_id,
        )?;
        let initial_graph = config_graph_identity(&config_read, &config.config_inputs)?;
        establish_config_identity(config, &initial_graph)?;
        let effective_mcp = graph_mcp_names(&initial_graph)?;
        let mut thread_params = json!({
            "model": config.model,
            "cwd": config.task_cwd,
            "ephemeral": true,
            "environments": [],
            "sandbox": "read-only",
            "approvalPolicy": "never",
            "allowProviderModelFallback": false,
            "dynamicTools": mcp.dynamic_tools(),
            "experimentalRawEvents": false,
            "developerInstructions": config.instructions,
            "config": thread_config(&config.effort, &effective_mcp)
        });
        if let Some(provider) = &config.model_provider {
            thread_params["modelProvider"] = json!(provider);
        }
        let thread_request = send_request(
            &mut codex,
            &mut next_id,
            "thread/start",
            thread_params,
        )?;
        let mut thread_state = State::new(None);
        let thread_result = wait_plain_response(
            &mut codex,
            &mut mcp,
            thread_request,
            &mut thread_state,
            config,
            writer,
            turn_deadline,
            &mut next_id,
        )?;
        let thread_id = thread_result["thread"]["id"]
            .as_str()
            .ok_or_else(|| fail("thread_missing", "thread/start thread id missing"))?
            .to_owned();
        thread_state.bind_thread(&thread_id)?;
        let mut status_cursor: Option<String> = None;
        let mut status_rows = Vec::new();
        loop {
            let status_request = send_request(
                &mut codex,
                &mut next_id,
                "mcpServerStatus/list",
                json!({"threadId": thread_id, "detail": "toolsAndAuthOnly", "limit": 100, "cursor": status_cursor}),
            )?;
            let status_result = wait_plain_response(
                &mut codex,
                &mut mcp,
                status_request,
                &mut thread_state,
                config,
                writer,
                turn_deadline,
                &mut next_id,
            )?;
            status_rows.extend(status_result["data"].as_array().cloned().ok_or_else(|| fail("mcp_status_unknown", "thread-scoped MCP status data missing"))?);
            status_cursor = status_result["nextCursor"].as_str().map(ToOwned::to_owned);
            if status_cursor.is_none() { break; }
        }
        validate_mcp_status(&json!({"data": status_rows}), &effective_mcp)?;
        let before_turn_graph = read_config_graph(
            &mut codex,
            &mut mcp,
            &mut thread_state,
            config,
            writer,
            turn_deadline,
            &mut next_id,
        )?;
        assert_config_graph(&initial_graph, &before_turn_graph)?;
        let actual = thread_actual(&thread_result, config)?;
        report.actual_model = Some(actual.clone());

        let receipt = ThreadReceipt {
            version: 1,
            host_created: true,
            thread_id: thread_id.clone(),
            run_id: config.cancel.identity.run_id.clone(),
            turn_id: config.cancel.identity.turn_id.clone(),
            model: config.model.clone(),
            effort: config.effort.clone(),
        };
        session::write(&config.thread_receipt, &receipt)?;
        let mut receipt_event = session::event(&receipt);
        receipt_event["receipt"]["receiptPath"] = json!(config.thread_receipt);
        report.thread_receipt = Some(receipt_event["receipt"].clone());
        emit(writer, &receipt_event)?;

        let turn_request = send_request(
            &mut codex,
            &mut next_id,
            "turn/start",
            json!({
                "threadId": thread_id,
                "input": [{"type": "text", "text": task, "text_elements": []}],
                "environments": [],
                "effort": config.effort
            }),
        )?;
        let mut state = State::new(Some(thread_id.clone()));
        let turn_response = wait_plain_response(
            &mut codex,
            &mut mcp,
            turn_request,
            &mut state,
            config,
            writer,
            turn_deadline,
            &mut next_id,
        );
        if let Some(observed) = &state.usage { report.usage = observed.clone(); }
        let turn_result = turn_response?;
        let response_turn_id = turn_result["turn"]["id"].as_str();
        if let Some(turn_id) = response_turn_id {
            state.bind_turn(turn_id)?;
        }
        if state.turn_id.is_none() {
            return Err(fail(
                "turn_missing",
                "turn/start response and turn/started did not provide a turn id",
            ));
        }

        let mut terminal_seen = false;
        loop {
            if terminal_status(&state).is_some() {
                terminal_seen = true;
                if check_terminal(&state, report)?.is_some() {
                    if state.cancel_sent {
                        if state.interrupt_acknowledged {
                            return Err(fail("cancelled", "turn interrupted after bounded cancellation"));
                        }
                    } else {
                        break;
                    }
                }
            }

            if !state.cancel_sent && config.cancelled()? {
                state.owner_cancel = true;
                send_interrupt(
                    &mut codex,
                    &mut state,
                    &mut next_id,
                    ms(config.deadlines.grace_ms),
                )?;
            }

            if let Some(deadline) = state.interrupt_deadline {
                if Instant::now() >= deadline {
                    return Err(fail("cancel_timeout", "cancel response/terminal grace expired"));
                }
            }
            let receive_deadline = receive_deadline(turn_deadline, state.interrupt_deadline);
            let value = match codex.receive_cancelable(
                receive_deadline,
                if state.interrupt_deadline.is_some() { "cancel_timeout" } else { "turn_deadline" },
                || if state.cancel_sent { Ok(false) } else { config.cancelled() },
            )? {
                Some(value) => value,
                None => {
                    state.owner_cancel = true;
                    send_interrupt(&mut codex, &mut state, &mut next_id, ms(config.deadlines.grace_ms))?;
                    continue;
                }
            };
            if let Some(response) = process_message(
                &mut codex,
                &mut mcp,
                &value,
                &mut state,
                config,
                writer,
                receive_deadline,
                &mut next_id,
            )? {
                let response_id = response["id"].as_u64();
                if state.interrupt_id == response_id {
                    if response.get("error").is_some() {
                        return Err(fail("cancel_failed", "turn/interrupt returned an error"));
                    }
                    state.interrupt_acknowledged = true;
                    if state.owner_cancel { report.cancel_acknowledged = true; }
                    if terminal_seen { return Err(fail("cancelled", "turn interrupted after bounded cancellation")); }
                    continue;
                }
                return Err(fail("bad_response", format!("unexpected app-server response id: {}", response["id"])));
            }
            if let Some(usage) = state.usage.clone() { report.usage = usage; }

            if terminal_status(&state).is_some() {
                terminal_seen = true;
                if check_terminal(&state, report)?.is_some() {
                    if state.cancel_sent {
                        if state.interrupt_acknowledged {
                            return Err(fail("cancelled", "turn interrupted after bounded cancellation"));
                        }
                    } else {
                        break;
                    }
                }
            }
        }
        let mut after_state = State::new(Some(thread_id.clone()));
        let after_round_deadline = Instant::now() + ms(config.deadlines.command_ms);
        let after_round_graph = read_config_graph(
            &mut codex,
            &mut mcp,
            &mut after_state,
            config,
            writer,
            after_round_deadline,
            &mut next_id,
        )?;
        assert_config_graph(&initial_graph, &after_round_graph)?;
        Ok(())
    })();

    codex.stdin.take();
    let (codex_cleanup, codex_pipes) =
        codex.cleanup(Instant::now() + ms(config.deadlines.shutdown_ms));
    report.child_exit = codex
        .owned
        .child
        .try_wait()
        .ok()
        .flatten()
        .and_then(|status| status.code());
    report.cleanup = codex_cleanup;
    let (mcp_cleanup, mcp_pipes) =
        mcp.child
            .cleanup(Instant::now() + ms(config.deadlines.shutdown_ms));
    if !codex_pipes
        || report.cleanup.status != "verified"
        || !mcp_pipes
        || mcp_cleanup.status != "verified"
    {
        report.cleanup.status = "unknown";
        return Err(fail("cleanup_unknown", "Codex or MCP cleanup not verified"));
    }
    report.cleanup.detail = format!(
        "Codex: {}; MCP: {}",
        report.cleanup.detail, mcp_cleanup.detail
    );
    protocol
}

#[cfg(test)]
mod tests {
    use super::*;

    fn report() -> TurnReport {
        TurnReport {
            success: false,
            failure: None,
            cleanup: Cleanup::not_started(),
            child_exit: None,
            settled: false,
            final_message: None,
            actual_model: None,
            usage: Usage::default(),
            nested_usage: Usage::default(),
            cancel_acknowledged: false,
            terminal_acknowledged: false,
            thread_receipt: None,
        }
    }

    #[test]
    fn config_graph_uses_inner_response_without_rpc_envelope() {
        let inputs = vec![config::ConfigInput {
            path: PathBuf::from("D:/fixture/codex/config.toml"),
            exists: false,
            sha256: None,
        }];
        let response = json!({
            "config": {"mcp_servers": {"home": {"enabled": true}}},
            "origins": {"model": "user"},
            "layers": [{"name": {"type": "sessionFlags"}, "version": 1}]
        });
        let first = config_graph_identity(&response, &inputs).unwrap();
        let second = config_graph_identity(&response, &inputs).unwrap();
        assert_eq!(first, second);
        assert_eq!(graph_mcp_names(&first).unwrap(), vec!["home"]);
    }

    #[test]
    fn config_graph_fingerprint_does_not_include_rpc_request_id() {
        let inputs = Vec::new();
        let response = json!({
            "config": {"mcp_servers": {}},
            "origins": {},
            "layers": [{"name": {"type": "sessionFlags"}, "version": 1}]
        });
        let first = config_graph_identity(&response, &inputs).unwrap();
        let second = config_graph_identity(&response, &inputs).unwrap();
        assert_eq!(first["fingerprint"], second["fingerprint"]);
    }

    #[test]
    fn packaged_defaults_file_is_part_of_config_graph_identity() {
        let path = std::env::temp_dir().join(format!("craft-codex-packaged-defaults-{}.toml", std::process::id()));
        fs::write(&path, b"# owned focused fixture\n").unwrap();
        let response = json!({
            "config": {"mcp_servers": {}},
            "origins": {},
            "layers": [{"name": {"type": "packagedDefaults", "file": path.to_string_lossy()}, "version": 1}]
        });
        let identity = config_graph_identity(&response, &[]).unwrap();
        let source = &identity["sources"][0];
        assert_eq!(source["exists"], true);
        assert_eq!(source["sha256"], config::hash_file(&path).unwrap());
        fs::remove_file(path).unwrap();
    }

    #[test]
    fn thread_start_binds_non_default_effort_in_native_config() {
        let mut params = json!({
            "model": "gpt-6.1-sol",
            "cwd": "D:/fixture/workspace",
            "ephemeral": true,
            "environments": [],
            "sandbox": "read-only",
            "approvalPolicy": "never",
            "allowProviderModelFallback": false,
            "dynamicTools": [],
            "experimentalRawEvents": false,
            "config": {"model_reasoning_effort": "high"}
        });
        params["modelProvider"] = json!("gpt");
        assert_eq!(params["config"]["model_reasoning_effort"], "high");
        assert_eq!(params["effort"], Value::Null);
    }

    #[test]
    fn early_turn_identity_and_usage_are_retained_before_response() {
        let mut state = State::new(Some("thread-1".to_owned()));
        state
            .bind_params(
                &json!({"threadId": "thread-1", "turnId": "turn-1"}),
                true,
            )
            .unwrap();
        state.usage = Some(
            usage(&json!({
                "total": {"inputTokens": 7, "outputTokens": 3, "totalTokens": 10}
            }))
            .unwrap(),
        );
        assert_eq!(state.turn_id.as_deref(), Some("turn-1"));
        assert_eq!(state.usage.as_ref().unwrap().total_tokens, Some(10));
    }

    #[test]
    fn duplicate_dynamic_call_is_rejected_after_pending_is_removed() {
        let mut state = State::new(Some("thread-1".to_owned()));
        assert!(state.seen_calls.insert("call-1".to_owned()));
        state.pending.insert("call-1".to_owned());
        state.pending.remove("call-1");
        assert!(!state.seen_calls.insert("call-1".to_owned()));
    }

    #[test]
    fn mcp_is_error_cannot_become_successful_dynamic_response() {
        assert!(!mcp_result_success(&json!({"isError": true})));
        assert!(mcp_result_success(&json!({"isError": false})));
    }

    #[test]
    fn cancelled_or_terminal_state_closes_effect_dispatch() {
        let mut state = State::new(Some("thread-1".to_owned()));
        assert!(state.effects_open());
        state.cancel_sent = true;
        assert!(!state.effects_open());
        state.cancel_sent = false;
        state.terminal = Some(json!({"params":{"turn":{"status":"interrupted"}}}));
        assert!(!state.effects_open());
        assert_eq!(state.effect_dispatches, 0);
    }

    #[test]
    fn cancellation_grace_is_independent_of_old_turn_wall_deadline() {
        let old_turn = Instant::now() + Duration::from_millis(1);
        let grace = Instant::now() + Duration::from_secs(3);
        assert_eq!(receive_deadline(old_turn, Some(grace)), grace);
    }

    #[test]
    fn cancellation_requires_both_interrupt_ack_and_interrupted_terminal() {
        let mut state = State::new(Some("thread-1".to_owned()));
        state.turn_id = Some("turn-1".to_owned());
        state.cancel_sent = true;
        state.terminal = Some(json!({
            "method": "turn/completed",
            "params": {"threadId": "thread-1", "turn": {"id": "turn-1", "status": "interrupted"}}
        }));
        let mut report = report();
        assert_eq!(check_terminal(&state, &mut report).unwrap(), Some(false));
        assert!(report.terminal_acknowledged);
        state.interrupt_acknowledged = true;
        assert!(check_terminal(&state, &mut report).is_err());
    }

    #[test]
    fn cancellation_cannot_accept_normal_completed_terminal() {
        let mut state = State::new(Some("thread-1".to_owned()));
        state.turn_id = Some("turn-1".to_owned());
        state.cancel_sent = true;
        state.terminal = Some(json!({
            "method": "turn/completed",
            "params": {"threadId": "thread-1", "turn": {"id": "turn-1", "status": "completed"}}
        }));
        let mut report = report();
        assert!(check_terminal(&state, &mut report).is_err());
        assert!(!report.settled);
    }
    #[test]
    fn cancellation_ack_without_terminal_does_not_settle() {
        let mut state = State::new(Some("thread-1".to_owned()));
        state.turn_id = Some("turn-1".to_owned());
        state.cancel_sent = true;
        state.interrupt_acknowledged = true;
        let mut report = report();
        assert_eq!(check_terminal(&state, &mut report).unwrap(), None);
        assert!(!report.terminal_acknowledged);
        assert!(!report.settled);
    }
}