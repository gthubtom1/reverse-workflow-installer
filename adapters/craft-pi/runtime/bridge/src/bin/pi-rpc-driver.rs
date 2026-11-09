use craft_pi_bridge::{
    Failure,
    config::{Config, MAX_TASK, read_bounded},
    driver,
};
use std::{io, path::Path, sync::mpsc, thread, time::Duration};
fn execute() -> Result<bool, Failure> {
    let args: Vec<String> = std::env::args().skip(1).collect();
    let path = match args.as_slice() {
        [path] if !path.starts_with('-') => path,
        [flag, path] if flag == "--config" => path,
        _ => {
            return Err(Failure::new(
                "invalid_arguments",
                "usage: pi-rpc-driver [--config] <explicit-config.json>",
            ));
        }
    };
    let c = Config::load(Path::new(path))?;
    let (tx, rx) = mpsc::channel();
    thread::spawn(move || {
        let _ = tx.send(read_bounded(io::stdin(), MAX_TASK));
    });
    let bytes = rx
        .recv_timeout(Duration::from_millis(c.deadlines.input_ms))
        .map_err(|e| Failure::new("input_deadline", e))??;
    let task = String::from_utf8(bytes).map_err(|e| Failure::new("invalid_task_utf8", e))?;
    Ok(driver::run(c, task, io::stdout()).success)
}
fn main() {
    let code = match execute() {
        Ok(true) => 0,
        Ok(false) => 1,
        Err(e) => {
            let _ = driver::emit_preflight_failure(e, io::stdout());
            2
        }
    };
    std::process::exit(code);
}
