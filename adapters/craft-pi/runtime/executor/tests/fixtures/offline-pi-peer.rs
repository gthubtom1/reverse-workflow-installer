//! OFFLINE FIXTURE ONLY. Direct-executable Pi protocol peer supported by the driver.
//! Node implements the scripted test protocol and invokes the real bounded MCP entry.
//! This does not qualify the driver's official Node-entry path handling.
use std::process::{Command, Stdio};
fn main() {
    let args: Vec<String> = std::env::args().skip(1).collect();
    if args.first().is_some_and(|arg| arg == "--config") {
        forward_preflight(&args);
        return;
    }
    let script =
        std::path::Path::new(env!("CARGO_MANIFEST_DIR")).join("tests/fixtures/fake-pi.cjs");
    match Command::new(std::env::var_os("CRAFT_TEST_NODE").expect("CRAFT_TEST_NODE must be explicit"))
        .arg(script)
        .args(std::env::args_os().skip(1))
        .stdin(Stdio::inherit())
        .stdout(Stdio::inherit())
        .stderr(Stdio::inherit())
        .status()
    {
        Ok(status) => std::process::exit(status.code().unwrap_or(1)),
        Err(e) => {
            eprintln!("offline peer unavailable: {e}");
            std::process::exit(2);
        }
    }
}

// Test-only transport: run the actual driver to its before-child refusal, then corrupt one
// receipt field. This exercises owner lock retention through the actual Craft callback.
fn forward_preflight(args: &[String]) {
    let config: serde_json::Value =
        serde_json::from_slice(&std::fs::read(&args[1]).unwrap()).unwrap();
    let marker = config["instructions"]
        .as_str()
        .unwrap()
        .split("TEST_RECEIPT_CASE=")
        .nth(1)
        .unwrap()
        .split_whitespace()
        .next()
        .unwrap();
    let (mutation, driver) = marker.split_once('|').unwrap();
    let output = Command::new(driver)
        .args(args)
        // Synthetic resource-path collision remains private even when the selected triple
        // is explicitly public. It must still fail before any Pi child starts.
        .env(
            "EXECUTOR_OFFLINE_TEST_KEY",
            config["agent_dir"].as_str().unwrap(),
        )
        .stdin(Stdio::inherit())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .output()
        .unwrap();
    if mutation == "activity" {
        println!("{}", serde_json::json!({"type":"agent_start"}));
    }
    for line in String::from_utf8_lossy(&output.stdout).lines() {
        let mut record: serde_json::Value = serde_json::from_str(line).unwrap();
        if record["type"] == "bridge_failure" && mutation == "missing-failure" {
            continue;
        }
        if record["type"] == "bridge_complete" {
            if mutation == "missing-completion" {
                continue;
            }
            match mutation {
                "root-false" => record["cleanup"]["root_exited"] = false.into(),
                "missing-root" => {
                    record["cleanup"]
                        .as_object_mut()
                        .unwrap()
                        .remove("root_exited");
                }
                "members-false" => record["cleanup"]["members_empty"] = false.into(),
                "missing-members" => {
                    record["cleanup"]
                        .as_object_mut()
                        .unwrap()
                        .remove("members_empty");
                }
                "wrong-scope" => record["cleanup"]["scope"] = "windows_job".into(),
                "job-unknown" => {
                    record["cleanup"]["scope"] = "windows_job".into();
                    record["cleanup"]["status"] = "unknown".into();
                }
                "verified-none" => record["cleanup"]["status"] = "verified".into(),
                "missing-usage" => {
                    record.as_object_mut().unwrap().remove("usage");
                }
                "success-true" => record["success"] = true.into(),
                _ => {}
            }
        }
        println!("{record}");
    }
    std::process::exit(if mutation == "exit-zero" {
        0
    } else {
        output.status.code().unwrap_or(2)
    });
}
