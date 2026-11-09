use crate::public_result::{check as public_check, event as public_event};
use crate::runtime::PiRuntime;
use crate::*;
use craft_anything_ai::cli_agents::AgentAdapters;
use craft_anything_ai::rebuild::{RebuildRun, RunEvent, RunOptions};
use craft_anything_ai::{
    AiHub, BackendConfig, BackendEntry, BackendKind, BackendOptions, KeyStore,
};
use craft_anything_engine::{
    Engine, Session,
    execution_policy::{real, source_digest},
    workspace::Workspace,
};
use craft_pi_bridge::config::PiCommand;
use serde_json::{Value, json};
use std::{
    collections::BTreeMap,
    io::Write,
    sync::{Arc, Mutex},
    time::{Duration, Instant},
};

/// The lease remains on disk on any unproved cleanup path. No PID-only automatic takeover.
struct Lease {
    path: PathBuf,
    bytes: Vec<u8>,
}
impl Lease {
    fn acquire(c: &ExecutionConfig, p: &ExecutionPolicy) -> Result<Self, ToolError> {
        let path = c.workspace.join(".craft-pi-executor-owner.json");
        let started = std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .map_err(|e| ToolError::internal(e.to_string()))?
            .as_millis();
        let bytes = serde_json::to_vec(&json!({"pid": std::process::id(), "owner_id": p.owner_id, "source_base_sha256": p.source_base_sha256,
            "policy_sha256": c.policy_sha256, "run_root": c.run_root, "started_unix_ms": started})).map_err(|e| ToolError::internal(e.to_string()))?;
        // If writing/syncing fails, retain this exclusive file as unknown ownership. Do not
        // remove it and permit a competing writer after partial lease persistence.
        let mut f = fs::OpenOptions::new()
            .create_new(true)
            .write(true)
            .open(&path)
            .map_err(|e| refusal("owner-conflict", e.to_string()))?;
        f.write_all(&bytes)
            .and_then(|_| f.sync_all())
            .map_err(|e| ToolError::io(path.display(), e))?;
        Ok(Self { path, bytes })
    }
    fn verify(&self) -> Result<(), ToolError> {
        if read_capped(&self.path)? != self.bytes {
            return Err(refusal(
                "owner-conflict",
                "Source ownership mark changed; replacement work is blocked.",
            ));
        }
        Ok(())
    }
    fn release(self) -> Result<(), ToolError> {
        self.verify()?;
        fs::remove_file(&self.path).map_err(|e| ToolError::io(self.path.display(), e))
    }
}
fn snapshot(root: &Path) -> Result<BTreeMap<String, String>, ToolError> {
    fn walk(base: &Path, dir: &Path, out: &mut BTreeMap<String, String>) -> Result<(), ToolError> {
        for item in fs::read_dir(dir).map_err(|e| ToolError::io(dir.display(), e))? {
            let item = item.map_err(|e| ToolError::internal(e.to_string()))?;
            let path = item.path();
            let kind = item
                .file_type()
                .map_err(|e| ToolError::io(path.display(), e))?;
            if ["target", "node_modules", ".git", ".craft-owner.lock"]
                .iter()
                .any(|n| item.file_name() == *n)
            {
                continue;
            }
            if kind.is_symlink() {
                return Err(refusal(
                    "path-denied",
                    "Source snapshot refuses symbolic links.",
                ));
            }
            if kind.is_dir() {
                walk(base, &path, out)?;
            } else if kind.is_file() {
                let relative = path
                    .strip_prefix(base)
                    .map_err(|e| ToolError::internal(e.to_string()))?;
                out.insert(
                    relative.to_string_lossy().replace('\\', "/"),
                    hash_file(&path)?,
                );
            }
            if out.len() > 10000 {
                return Err(refusal(
                    "output-limit",
                    "Source snapshot exceeds 10000 files.",
                ));
            }
        }
        Ok(())
    }
    let mut out = BTreeMap::new();
    walk(root, root, &mut out)?;
    Ok(out)
}
/// Production entry fixes Node/official Pi from installer-provided, hash-checked runtime paths.
pub fn execute(c: ExecutionConfig) -> Result<Value, ToolError> {
    c.validate_resources()?;
    if c.provider_manifest.is_none() {
        return Err(refusal(
            "provider-manifest",
            "A reviewed target provider manifest is required for production execution.",
        ));
    }
    let node = std::env::var_os("CRAFT_PI_NODE")
        .map(PathBuf::from)
        .ok_or_else(|| refusal("runtime-unavailable", "Explicit CRAFT_PI_NODE is required."))?;
    let entry = std::env::var_os("CRAFT_PI_ENTRY")
        .map(PathBuf::from)
        .ok_or_else(|| {
            refusal(
                "runtime-unavailable",
                "Explicit CRAFT_PI_ENTRY is required.",
            )
        })?;
    if !node.is_absolute() || !entry.is_absolute() || !node.is_file() || !entry.is_file() {
        return Err(refusal(
            "runtime-unavailable",
            "Explicit Node/entry files must be absolute and available.",
        ));
    }
    for key in &c.credential_env_keys {
        if std::env::var_os(key).is_none_or(|v| v.is_empty()) {
            return Err(refusal(
                "credential-env-missing",
                "An explicitly named credential environment variable is absent.",
            ));
        }
    }
    probe_runtime(&node, &entry, Duration::from_secs(30))?;
    execute_with_runtime(
        c,
        PiCommand {
            program: node,
            argv: vec![entry.display().to_string()],
        },
        std::env::current_exe().map_err(|e| ToolError::internal(e.to_string()))?,
    )
}
/// Probe an explicit runtime with no inherited Node hooks, provider credentials or profile
/// variables. Public failures contain only fixed status/code/byte counts, never diagnostics.
pub fn probe_runtime(node: &Path, entry: &Path, timeout: Duration) -> Result<(), ToolError> {
    let mut process = craft_anything_platform::Process::new(node)
        .arg(entry)
        .arg("--version")
        .env_clear()
        .timeout(timeout)
        .stdout_cap(1024)
        .stderr_cap(1024);
    for key in ["SystemRoot", "WINDIR", "TEMP", "TMP"] {
        if let Some(value) = std::env::var_os(key) {
            process = process.env(key, value);
        }
    }
    let output = process.run().map_err(|error| refusal("runtime-probe-failed", "Explicit runtime version probe failed.")
        .with_details(json!({"reason":"runtime-probe-failed","status":"process-error","error_code":format!("{:?}",error.code)})))?;
    if !output.success
        || output.stdout_truncated
        || output.stderr_truncated
        || output.stdout_text().trim() != "1.5.0"
    {
        return Err(refusal("runtime-probe-failed", "Explicit runtime version probe did not match the fixed contract.")
            .with_details(json!({"reason":"runtime-probe-failed","status":"rejected","exit_code":output.code,"stdout_bytes":output.stdout.len(),"stderr_bytes":output.stderr.len(),"stdout_truncated":output.stdout_truncated,"stderr_truncated":output.stderr_truncated})));
    }
    Ok(())
}
/// The test harness injects a real offline subprocess here. CLI execution always uses execute().
pub fn execute_with_runtime(
    c: ExecutionConfig,
    pi: PiCommand,
    executable: PathBuf,
) -> Result<Value, ToolError> {
    c.validate_resources()?;
    let p = Arc::new(c.policy()?);
    p.validate_model()?;
    if hash_file(&c.driver)? != c.driver_sha256 {
        return Err(refusal(
            "identity-mismatch",
            "Built RPC driver hash differs.",
        ));
    }
    if p.owner_id.len() < 16
        || p.owner_id
            .chars()
            .any(|c| !c.is_ascii_alphanumeric() && c != '-' && c != '_')
        || p.max_wall_secs > 3600
    {
        return Err(refusal(
            "invalid-owner",
            "Owner identity must fit the driver contract and execution is capped at one hour.",
        ));
    }
    if p.kind_id != "app"
        || !p.checks.iter().any(|k| k.id == "build" && k.required)
        || !p
            .checks
            .iter()
            .any(|k| k.id == "external-scenario" && k.required)
    {
        return Err(refusal(
            "unsupported",
            "This entry requires app kind, an actual required source build and required external business scenario.",
        ));
    }
    if c.create_workspace {
        if c.workspace.exists()
            && fs::read_dir(&c.workspace)
                .map_err(|e| ToolError::io(c.workspace.display(), e))?
                .next()
                .is_some()
        {
            return Err(refusal(
                "workspace-conflict",
                "New workspace requires an empty owned directory.",
            ));
        }
        let initial = if p.app_root.exists() {
            source_digest(&p.app_root)?
        } else {
            "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855".into()
        };
        if initial != p.source_base_sha256 {
            return Err(refusal(
                "source-drift",
                "New workspace must explicitly accept its empty initial source digest.",
            ));
        }
        if craft_anything_engine::execution_policy::real_parent(&p.app_root)?
            != craft_anything_engine::execution_policy::real_parent(&c.workspace.join("app"))?
        {
            return Err(refusal(
                "path-denied",
                "New workspace app identity differs from accepted policy.",
            ));
        }
    }
    let mut ws = if c.create_workspace {
        let mut ws = Workspace::create_at(
            &c.workspace,
            "Accepted implementation",
            &c.message,
            p.original.target.clone(),
            None,
        )?;
        fs::create_dir_all(ws.app_dir()).map_err(|e| ToolError::io(ws.app_dir().display(), e))?;
        ws.manifest.stack = p.stack.clone();
        ws.save()?;
        ws
    } else {
        Workspace::open(&c.workspace)?
    };
    p.preflight(&ws)?;
    if ws.manifest.agent_session.is_some() {
        return Err(refusal(
            "unsupported",
            "Cross-run session/history reuse is not qualified.",
        ));
    }
    let app = real(&p.app_root)?;
    // Owned config/control roots are never reachable through app path capabilities.
    let parent = real(
        c.run_root
            .parent()
            .ok_or_else(|| refusal("invalid-config", "run root parent missing"))?,
    )?;
    if parent.starts_with(&app)
        || app.starts_with(
            &parent.join(
                c.run_root
                    .file_name()
                    .ok_or_else(|| refusal("invalid-config", "run root name missing"))?,
            ),
        )
    {
        return Err(refusal("path-denied", "Run resources overlap the app."));
    }
    if c.stop_marker.starts_with(&app) {
        return Err(refusal(
            "path-denied",
            "Stop marker must be outside Builder roots.",
        ));
    }
    if c.stop_marker.exists() {
        return Err(refusal("cancel-requested", "Stop marker already present."));
    }
    let instructions = read_instructions(&c)?;
    let before = snapshot(&app)?;
    let lease = Lease::acquire(&c, &p)?;
    let observer = observation::Descendants::start()?;
    // From here all errors retain lease and resources, for explicit owner diagnosis.
    p.preflight(&ws)?;
    fs::create_dir(&c.run_root).map_err(|e| ToolError::io(c.run_root.display(), e))?;
    fs::create_dir(c.run_root.join("sessions"))
        .map_err(|e| ToolError::io(c.run_root.display(), e))?;
    fs::create_dir(c.run_root.join("owner-config"))
        .map_err(|e| ToolError::io(c.run_root.display(), e))?;
    let policy_bytes = read_capped(&c.policy)?;
    fs::write(c.run_root.join("accepted-policy.json"), policy_bytes)
        .map_err(|e| ToolError::io(c.run_root.display(), e))?;
    let adapter = adapter::PiAdapter::new(c.run_root.join("not-a-turn.json"));
    let mut adapters = AgentAdapters::built_in();
    adapters.register(Arc::new(adapter.clone()));
    let receipts: Arc<Mutex<Vec<Value>>> = Default::default();
    let runtime = Arc::new(PiRuntime {
        execution: c.clone(),
        pi,
        executable,
        adapter,
        receipts: receipts.clone(),
        instructions,
    });
    ws.manifest.stack = p.stack.clone();
    ws.save()?;
    let session = Session::isolated(&c.run_root.join("owner-config"));
    let engine = Arc::new(Engine::new(session));
    let hub = AiHub::with_stores(
        engine,
        c.run_root.join("owner-config/config.toml"),
        KeyStore::file_only(c.run_root.join("owner-config/unused-keys.toml")),
    );
    hub.add_backend_with(
        BackendEntry {
            config: BackendConfig {
                name: BACKEND_ID.into(),
                kind: BackendKind::AgentCli,
                model: "pi".into(),
                base_url: None,
                ssh_host: None,
                enabled: true,
            },
            options: BackendOptions {
                command: Some(c.driver.display().to_string()),
                cli_model: Some(p.model.expected.model.clone()),
                timeout_secs: Some(p.max_wall_secs),
                acp: Some(false),
                ..Default::default()
            },
        },
        None,
    )?;
    let opts = RunOptions {
        backend: Some(BACKEND_ID.into()),
        message: Some(c.message.clone()),
        max_rounds: c.max_refinements,
        good_enough: GOOD_ENOUGH,
        adapters,
        policy: Some(p.clone()),
        policy_runtime: Some(runtime),
        clean_room: Some(true),
        ..Default::default()
    };
    let mut run = match RebuildRun::start(&hub, ws, opts) {
        Ok(r) => r,
        Err(e) => {
            lease.release()?;
            return Err(e);
        }
    };
    let start = Instant::now();
    let mut cancelled = false;
    let mut checked = Vec::new();
    let mut events = Vec::new();
    let mut finished = None;
    while run.is_running() {
        if c.stop_marker.exists() || start.elapsed() > Duration::from_secs(p.max_wall_secs) {
            cancelled = true;
            run.stop();
            if start.elapsed() > Duration::from_secs(p.max_wall_secs + 25) {
                break;
            }
        }
        collect(run.poll(), &mut checked, &mut events, &mut finished);
        std::thread::sleep(Duration::from_millis(20));
    }
    if run.is_running() {
        run.stop();
    }
    let joined = run.wait_for_completion(Duration::from_secs(20))?;
    collect(run.poll(), &mut checked, &mut events, &mut finished);
    drop(run);
    let turns = receipts
        .lock()
        .unwrap_or_else(std::sync::PoisonError::into_inner)
        .clone();
    let all_driver_jobs_verified = !turns.is_empty()
        && turns.iter().all(|turn| {
            turn["completion"]["cleanup"]["status"] == "verified"
                && crate::runtime::turn_cleanup_closed(turn)
        });
    let all_cleanup = !turns.is_empty() && turns.iter().all(crate::runtime::turn_cleanup_closed);
    let all_turns = !turns.is_empty() && turns.iter().all(|t| t["successful"] == true);
    let latest_round = checked
        .iter()
        .filter_map(|c: &Value| c["round"].as_u64())
        .max();
    let typed_report = latest_round
        .map(|round| {
            craft_anything_ai::rebuild::read_check_plan_report(&p, &c.workspace, round as u32)
        })
        .transpose();
    let mut return_summary = crate::return_summary::from_execution(
        &c,
        &p,
        typed_report.as_ref().ok().and_then(Option::as_ref),
        cancelled,
        finished == Some(true),
    )?;
    let typed_report_valid = typed_report.is_ok();
    let required_passed = typed_report_valid
        && typed_report
            .as_ref()
            .ok()
            .and_then(Option::as_ref)
            .is_some_and(|report| {
                report.checks.iter().filter(|c| c.required).all(|c| {
                    c.disposition == craft_anything_ai::rebuild::CheckDisposition::Executed
                })
            })
        && latest_round.is_some()
        && p.checks.iter().filter(|c| c.required).all(|plan| {
            checked.iter().any(|r| {
                r["round"].as_u64() == latest_round
                    && r["check"] == plan.id
                    && serde_json::from_value::<craft_anything_engine::workspace::CheckResult>(
                        r.clone(),
                    )
                    .is_ok_and(|check| check.good(GOOD_ENOUGH))
            })
        });
    let owner_resources = observer.finish();
    let clean = joined && all_cleanup && owner_resources["status"] == "observed-empty";
    let inputs_valid = p
        .revalidate_builder_inputs()
        .and_then(|_| validate_original(&p))
        .is_ok();
    if !inputs_valid && return_summary.is_none() {
        if let Some(reference) = &c.handoff_context {
            let context: crate::return_summary::Context =
                serde_json::from_slice(&reference.read_verified()?)
                    .map_err(|_| refusal("invalid-context", "Invalid typed context."))?;
            return_summary = Some(crate::return_summary::Summary::new(
                context,
                crate::return_summary::Disposition::NeedsEvidence,
                vec![crate::return_summary::CheckReason {
                    id: "authority".into(),
                    reason_code: "input-changed".into(),
                }],
            ));
        }
    }
    let candidate = clean
        && all_turns
        && required_passed
        && !cancelled
        && finished == Some(true)
        && inputs_valid
        && return_summary.is_none();
    let after = snapshot(&app)?;
    let mut paths: std::collections::BTreeSet<_> = before.keys().cloned().collect();
    paths.extend(after.keys().cloned());
    let diff: Vec<Value> = paths
        .into_iter()
        .filter(|k| before.get(k) != after.get(k))
        .map(|k| json!({"path": k, "before_sha256": before.get(&k), "after_sha256": after.get(&k)}))
        .collect();
    lease.verify()?;
    let result = json!({"contract_version": CONTRACT_VERSION, "state": if !clean {"blocked-cleanup"} else if cancelled {"stopped"} else if candidate {"candidate"} else {"failed"},
        "accepted": false, "handoff_qualification":if c.handoff_context.is_some(){"prepare-bound-original-authority"}else{"raw-policy-unqualified-handoff; independent lead validation required"}, "owner_id": p.owner_id, "pid": std::process::id(), "policy_sha256": c.policy_sha256,
        "source_before_sha256": p.source_base_sha256, "source_after_sha256": source_digest(&app)?, "diff": diff,
        "checks": checked.iter().map(public_check).collect::<Vec<_>>(), "unknowns": checked.iter().filter_map(|r| {
            let count=r["unknowns"].as_array().map_or(0,Vec::len);
            (count>0).then(||json!({"check":r["check"],"round":r["round"],"count":count,"status":"unverified"}))
        }).collect::<Vec<_>>(),
        "actual_turns": turns, "events": events, "return_summary":return_summary, "typed_check_report_valid":typed_report_valid, "craft_finished_ok": finished, "cleanup": {"closed": clean, "worker_joined": joined, "all_driver_jobs_verified": all_driver_jobs_verified, "all_driver_cleanups_closed": all_cleanup, "owner_resources": owner_resources},
        "external_qualifications": p.baseline.artifacts.iter().map(|a|json!({"key":a.key,"origin":a.origin_kind,"qualification":a.qualification(),"limitations":a.limitations})).collect::<Vec<_>>(),
        "source_qualification": "External provenance retained; bounded call policy is not a Clean Room origin qualification",
        "limits": ["Candidate only; independent lead acceptance required", "No OS account isolation claim", "Cross-run history unsupported", "No hard aggregate token/cost enforcement; per-response maxTokens is configured and actual usage is audited"]});
    write_json(&c.run_root.join("candidate.json"), &result)?;
    if clean {
        lease.release()?;
    }
    Ok(result)
}
fn collect(
    batch: Vec<RunEvent>,
    checks: &mut Vec<Value>,
    events: &mut Vec<Value>,
    finished: &mut Option<bool>,
) {
    for event in batch {
        match event {
            RunEvent::Checked(c) => match serde_json::to_value(c) {
                Ok(value) => checks.push(value),
                Err(_) => events.push(json!({"error":"check-serialization-failed"})),
            },
            RunEvent::Finished {
                ok,
                message,
                paused,
            } => {
                *finished = Some(ok);
                events.push(json!({"event": "finished", "ok": ok, "message_bytes": message.len(), "paused": paused}));
            }
            other => {
                if events.len() < 10000 {
                    events.push(public_event(other));
                }
            }
        }
    }
}
