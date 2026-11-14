use craft_codex_bridge::{config::{Config, MAX_TASK}, driver, Failure};
use std::{io, path::Path, sync::mpsc, thread, time::Duration};
fn main() {
    let args: Vec<String> = std::env::args().skip(1).collect();
    let path = match args.as_slice() { [p] if !p.starts_with('-') => p, [flag,p] if flag == "--config" => p, _ => { emit(Failure::new("invalid_arguments", "usage: codex-app-server-driver [--config] <absolute-config.json>")); std::process::exit(2); } };
    let config = match Config::load(Path::new(path)) { Ok(c) => c, Err(e) => { emit(e); std::process::exit(2); } };
    let (tx, rx) = mpsc::channel();
    thread::spawn(move || { let _ = tx.send(craft_codex_bridge::config::read_bounded(io::stdin(), MAX_TASK)); });
    let bytes = match rx.recv_timeout(Duration::from_millis(config.deadlines.input_ms)) { Ok(Ok(b)) => b, Ok(Err(e)) => { emit(e); std::process::exit(2); }, Err(e) => { emit(Failure::new("input_deadline", e)); std::process::exit(2); } };
    let task = match String::from_utf8(bytes) { Ok(s) => s, Err(e) => { emit(Failure::new("invalid_task_utf8", e)); std::process::exit(2); } };
    let report = driver::run(config, task, io::stdout());
    std::process::exit(if report.success { 0 } else { 1 });
}
fn emit(e: Failure) { let _ = serde_json::to_writer(io::stdout(), &serde_json::json!({"type":"bridge_failure","code":e.code,"detail":e.detail})); }
