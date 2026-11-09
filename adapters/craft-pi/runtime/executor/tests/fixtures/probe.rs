//! Offline subprocess used to test the version probe's inherited-environment boundary.
use std::{path::PathBuf, time::Duration};
fn main() {
    let args: Vec<_> = std::env::args().skip(1).collect();
    if args.len() != 3 {
        std::process::exit(2);
    }
    let ms = args[2].parse::<u64>().unwrap_or(1000);
    match craft_pi_executor::execution::probe_runtime(
        &PathBuf::from(&args[0]),
        &PathBuf::from(&args[1]),
        Duration::from_millis(ms),
    ) {
        Ok(()) => println!("{{\"ok\":true}}"),
        Err(e) => {
            println!("{}", serde_json::json!({"ok":false,"error":e}));
            std::process::exit(1);
        }
    }
}
