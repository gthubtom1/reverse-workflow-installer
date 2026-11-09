use craft_anything_ai::{
    AgentEvent,
    cli_agents::{AgentAdapters, StreamParser},
};
use craft_anything_engine::{
    execution_policy::*,
    workspace::{TargetRef, Workspace},
};
use craft_pi_bridge::config::PiCommand;
use craft_pi_executor::{execution::execute_with_runtime, *};
use serde_json::{Value, json};
use std::{
    fs,
    path::{Path, PathBuf},
    sync::Arc,
};

fn reference(path: &Path, bytes: &[u8]) -> HashedRef {
    fs::write(path, bytes).unwrap();
    HashedRef {
        path: path.into(),
        sha256: hash_file(path).unwrap(),
    }
}
fn fixture(root: &Path) -> ExecutionConfig {
    let original = reference(
        &root.join("original.txt"),
        b"Offline test original identity; not production Evidence.",
    );
    let mut ws = Workspace::create(
        &root.join("projects"),
        "fixture",
        "Persist a saved name",
        TargetRef::Local {
            path: original.path.clone(),
        },
    )
    .unwrap();
    ws.manifest.stack = "Rust (console)".into();
    ws.save().unwrap();
    fs::create_dir_all(ws.app_dir().join("src")).unwrap();
    fs::write(
        ws.app_dir().join("Cargo.toml"),
        "[package]\nname=\"offline-persistence-fixture\"\nversion=\"0.1.0\"\nedition=\"2024\"\n",
    )
    .unwrap();
    fs::write(
        ws.app_dir().join("rust-toolchain.toml"),
        "[toolchain]\nchannel=\"stable-x86_64-pc-windows-gnu\"\n",
    )
    .unwrap();
    fs::write(
        ws.app_dir().join("src/main.rs"),
        "fn main(){println!(\"unimplemented\");}",
    )
    .unwrap();
    // Explicit test-only external observation, never imported as Craft/REA native Evidence.
    let external = reference(
        &root.join("fixture-external.json"),
        b"{\"kind\":\"offline-test-observation\",\"expected_name\":\"Ada\"}",
    );
    let baseline = root.join("baseline");
    fs::create_dir(&baseline).unwrap();
    let state = reference(&root.join("expected-state.txt"), b"Ada");
    let scenario = json!({"version":2,"task_id":"T-persist","evidence_id":"offline-external-observation-1",
        "harness":"direct-exec-v1","reset":"fresh-copy-v1","runtime_files":[],"seed_files":[{"relative_path":"state.txt","content":null}],
        "program":"target/debug/offline-persistence-fixture.exe","arguments":[],"stdin":"Ada\n","environment":{},"timeout_secs":10,
        "exit_code":0,"stdout":"saved: Ada\n","stderr":"","state_files":[{"relative_path":"state.txt","sha256":state.sha256}]});
    let scenario = reference(
        &baseline.join("scenario.json"),
        &serde_json::to_vec(&scenario).unwrap(),
    );
    let checks = vec![
        PlannedCheck {
            id: "build".into(),
            implementation: "bounded-command-build-v1".into(),
            required: true,
            baseline: None,
            kind: None,
            depends_on: vec![],
        },
        PlannedCheck {
            id: "external-scenario".into(),
            implementation: "external-scenario-v2".into(),
            required: true,
            baseline: Some("persist".into()),
            kind: Some(BaselineKind::Scenario),
            depends_on: vec!["build".into()],
        },
    ];
    let plan = reference(
        &root.join("check-plan.json"),
        &serde_json::to_vec(&checks).unwrap(),
    );
    let cargo = std::env::var("CRAFT_TEST_CARGO").expect("CRAFT_TEST_CARGO must be explicit");
    assert!(!cargo.contains(['"', '\r', '\n']), "invalid explicit Cargo path");
    let portable_command = String::from("portable-fixture-build.cmd");
    fs::write(ws.app_dir().join(&portable_command), format!("@echo off\r\n\"{}\" build --quiet --offline\r\n", cargo)).unwrap();
    fs::write(ws.app_dir().join("portable-fixture-command.json"), serde_json::to_vec(&json!({"command": portable_command})).unwrap()).unwrap();
    let p = AcceptedResearch {
        version: 1,
        mode: ExecutionMode::Buildcheck,
        identity: Identity {
            case_ref: external.clone(),
            scope_ref: external.clone(),
            workitem_ref: external.clone(),
            feature_ref: external.clone(),
            acceptance_ref: external.clone(),
            task_ids: vec!["T-persist".into()],
        },
        original: Original {
            target: ws.manifest.target.clone(),
            target_identity: original.sha256,
            bundle: external.clone(),
            traceability: external.clone(),
            scenarios: external.clone(),
            qualifications: external.clone(),
            environment: external.clone(),
        },
        baseline: ExternalBaseline {
            version: 1,
            root: baseline,
            bundle_sha256: external.sha256.clone(),
            artifacts: vec![ExternalArtifact {
                key: "persist".into(),
                kind: BaselineKind::Scenario,
                origin_kind: ExternalOrigin::Observation,
                evidence_id: "offline-external-observation-1".into(),
                operation: "offline-test-export".into(),
                provider: "offline-fixture".into(),
                environment: "Windows GNU test fixture".into(),
                authority: "raw-observation".into(),
                limitations: vec!["No production Evidence or real model".into()],
                source: external.clone(),
                output: scenario,
                converter_version: "fixture-v1".into(),
                parameters: json!({}),
                field_mapping: json!({"state":"sha256"}),
                losses: vec![],
            }],
        },
        check_plan_ref: plan,
        checks,
        source_base_sha256: source_digest(&ws.app_dir()).unwrap(),
        app_root: ws.app_dir(),
        writable_roots: vec![ws.app_dir()],
        read_references: vec![],
        commands: vec![FrozenCommand {
            command: portable_command.clone(),
            cwd: ws.app_dir(),
            timeout_secs: 30,
        }],
        build: Some(BuildInvocation {
            command_index: 0,
            artifacts: vec![PathBuf::from(
                "target/debug/offline-persistence-fixture.exe",
            )],
        }),
        protected_paths: vec![
            ws.app_dir().join("Cargo.toml"),
            ws.app_dir().join("rust-toolchain.toml"),
        ],
        kind_id: "app".into(),
        stack: "Rust (console)".into(),
        model: ModelPermission {
            allowed: true,
            expected: ModelIdentity {
                provider: "fixture".into(),
                model: "offline".into(),
                effort: "high".into(),
            },
            backend_id: BACKEND_ID.into(),
            permission_contract: PERMISSION.into(),
        },
        owner_id: new_id(),
        max_wall_secs: 120,
        failed_feedback: None,
    };
    let policy = root.join("policy.json");
    write_json(&policy, &p).unwrap();
    let instructions = reference(&root.join("instructions.md"), b"Offline fixture Builder: implement persistence using only the supplied bounded tools. Do not delegate.");
    let driver = PathBuf::from(std::env::var_os("CRAFT_TEST_DRIVER").expect("CRAFT_TEST_DRIVER must be explicit"));
    ExecutionConfig {
        contract_version: 1,
        policy: policy.clone(),
        policy_sha256: hash_file(&policy).unwrap(),
        workspace: ws.root,
        create_workspace: false,
        run_root: root.join("run"),
        driver_sha256: hash_file(&driver).unwrap(),
        driver,
        credential_env_keys: vec![],
        provider_manifest: None,
        instructions: instructions.path,
        instructions_sha256: instructions.sha256,
        max_refinements: 2,
        stop_marker: root.join("stop"),
        message: "Save the input name, reopen the state file, and print the saved value.".into(),
        handoff_context: None,
    }
}
fn peer() -> PiCommand {
    PiCommand {
        program: std::env::var("CRAFT_TEST_NODE").expect("CRAFT_TEST_NODE must be explicit").into(),
        argv: vec![
            Path::new(env!("CARGO_MANIFEST_DIR"))
                .join("tests/fixtures/fake-pi.cjs")
                .display()
                .to_string(),
        ],
    }
}
fn retained_fixture_dir() -> PathBuf {
    let parent = PathBuf::from(std::env::var_os("CRAFT_TEST_ROOT").expect("CRAFT_TEST_ROOT must be explicit")).join("");
    fs::create_dir_all(&parent).unwrap();
    tempfile::Builder::new()
        .prefix("offline-run-")
        .tempdir_in(parent)
        .unwrap()
        .keep()
}
#[test]
fn authoritative_before_child_refusal_closes_failure_but_corrupt_receipts_keep_lease() {
    let mut cases = Vec::new();
    for mutation in [
        "intact",
        "root-false",
        "missing-root",
        "members-false",
        "missing-members",
        "wrong-scope",
        "job-unknown",
        "verified-none",
        "missing-usage",
        "success-true",
        "missing-failure",
        "missing-completion",
        "activity",
        "exit-zero",
    ] {
        let dir = retained_fixture_dir();
        let mut c = fixture(&dir);
        let real_driver = c.driver.clone();
        c.credential_env_keys = vec!["EXECUTOR_OFFLINE_TEST_KEY".into()];
        c.driver = env!("CARGO_BIN_EXE_offline-pi-peer").into();
        c.driver_sha256 = hash_file(&c.driver).unwrap();
        let instructions = format!(
            "Offline refusal receipt test. TEST_RECEIPT_CASE={mutation}|{}",
            real_driver.display()
        );
        fs::write(&c.instructions, instructions).unwrap();
        c.instructions_sha256 = hash_file(&c.instructions).unwrap();
        let result = execute_with_runtime(
            c.clone(),
            peer(),
            env!("CARGO_BIN_EXE_craft-pi-executor").into(),
        )
        .unwrap();
        assert_eq!(result["accepted"], false, "{mutation}");
        assert_eq!(result["cleanup"]["worker_joined"], true, "{mutation}");
        assert!(result["checks"].as_array().unwrap().is_empty());
        assert!(result["diff"].as_array().unwrap().is_empty());
        assert!(!c.run_root.join("turn-1/agent/fake-prompt-started").exists());
        assert_eq!(
            fs::read_dir(c.run_root.join("sessions")).unwrap().count(),
            0
        );
        let lease = c.workspace.join(".craft-pi-executor-owner.json");
        if mutation == "intact" {
            assert_eq!(
                result["cleanup"]["owner_resources"]["status"],
                "observed-empty"
            );
            assert_eq!(result["state"], "failed");
            assert_eq!(result["cleanup"]["closed"], true);
            assert_eq!(result["cleanup"]["all_driver_cleanups_closed"], true);
            assert_eq!(result["cleanup"]["all_driver_jobs_verified"], false);
            let turn = &result["actual_turns"][0];
            assert_eq!(turn["not_started_proved"], true);
            assert_eq!(turn["driver_exit"], 1);
            assert_eq!(turn["failure_code"], "credential_control_conflict");
            assert_eq!(turn["completion"]["childExit"], Value::Null);
            assert_eq!(turn["completion"]["usage"]["total_tokens"], 0);
            assert_eq!(turn["completion"]["cleanup"]["scope"], "none");
            assert!(!lease.exists());
        } else {
            // A negative may independently observe unknown ownership; it must remain blocked
            // and retain its lease. Only the intact positive requires observed-empty.
            assert!(matches!(
                result["cleanup"]["owner_resources"]["status"].as_str(),
                Some("observed-empty" | "unknown")
            ));
            assert_eq!(result["state"], "blocked-cleanup", "{mutation}");
            assert_eq!(result["cleanup"]["closed"], false, "{mutation}");
            assert_eq!(
                result["actual_turns"][0]["not_started_proved"], false,
                "{mutation}"
            );
            assert!(lease.is_file(), "{mutation}");
        }
        cases.push(json!({"case":mutation,"state":result["state"],"cleanup":result["cleanup"],"not_started_proved":result["actual_turns"][0]["not_started_proved"],"lease_retained":lease.exists(),"artifact":c.run_root.join("candidate.json")}));
    }
    write_json(
        &PathBuf::from(std::env::var_os("CRAFT_TEST_ROOT").expect("CRAFT_TEST_ROOT must be explicit")).join("preflight-cleanup-cases.json"),
        &cases,
    )
    .unwrap();
}
#[test]
fn real_craft_loop_mcp_write_failed_state_check_then_refine() {
    let dir = retained_fixture_dir();
    let c = fixture(&dir);
    let result = execute_with_runtime(
        c.clone(),
        peer(),
        PathBuf::from(env!("CARGO_BIN_EXE_craft-pi-executor")),
    )
    .unwrap();
    write_json(
        &PathBuf::from(std::env::var_os("CRAFT_TEST_ROOT").expect("CRAFT_TEST_ROOT must be explicit")).join("offline-result.json"),
        &result,
    )
    .unwrap();
    assert_eq!(result["state"], "candidate", "{}", result);
    assert_eq!(result["accepted"], false);
    let public = serde_json::to_string(&result).unwrap();
    assert!(!public.contains("PUBLIC-RECEIPT-CONTENT-SENTINEL"));
    assert!(!public.contains("fn main"));
    assert!(!public.contains("std::fs::write"));
    let checks = result["checks"].as_array().unwrap();
    assert!(
        checks
            .iter()
            .any(|c| c["check"] == "external-scenario" && c["passed"] == false)
    );
    assert!(
        checks
            .iter()
            .any(|c| c["check"] == "external-scenario" && c["passed"] == true)
    );
    let attempts = |round: u32| -> Vec<PathBuf> {
        fs::read_dir(c.workspace.join(format!("checks/round-{round}")))
            .unwrap()
            .map(|e| e.unwrap().path())
            .filter(|p| {
                p.is_dir()
                    && p.file_name()
                        .unwrap()
                        .to_string_lossy()
                        .starts_with("scenario-")
            })
            .collect()
    };
    let first = attempts(1);
    let second = attempts(2);
    assert_eq!(first.len(), 1);
    assert_eq!(second.len(), 1);
    assert!(!first[0].join("state.txt").exists());
    assert_eq!(
        fs::read_to_string(second[0].join("state.txt")).unwrap(),
        "Ada"
    );
    assert!(first[0].join("initial-seed-receipt.json").is_file());
    assert!(second[0].join("initial-seed-receipt.json").is_file());
    assert!(!c.workspace.join("capture").exists());
    assert!(!dir.join("escape.txt").exists());
    assert!(!c.workspace.join("app/tasks.md").exists());
    assert!(!c.workspace.join(".craft-pi-executor-owner.json").exists());
    let turns = result["actual_turns"].as_array().unwrap();
    assert_eq!(turns.len(), 2);
    for turn in turns {
        assert_eq!(turn["completion"]["usage"]["input"], 10);
        assert_eq!(turn["completion"]["usage"]["output"], 5);
        assert_eq!(turn["completion"]["cleanup"]["status"], "verified");
    }
    for n in 1..=2 {
        let gates: Value = serde_json::from_slice(
            &fs::read(
                c.run_root
                    .join(format!("turn-{n}/agent/fixture-gates.json")),
            )
            .unwrap(),
        )
        .unwrap();
        assert_eq!(gates["denials"].as_array().unwrap().len(), 5);
        assert_eq!(gates["resumed"], n == 2);
    }
}
#[test]
fn owner_stop_marker_drains_driver_and_keeps_candidate_unaccepted() {
    let dir = retained_fixture_dir();
    let mut c = fixture(&dir);
    c.message = "OFFLINE_HANG_FOR_CANCEL".into();
    let c2 = c.clone();
    let worker = std::thread::spawn(move || {
        execute_with_runtime(c2, peer(), env!("CARGO_BIN_EXE_craft-pi-executor").into())
    });
    let start = std::time::Instant::now();
    let prompted = c.run_root.join("turn-1/agent/fake-prompt-started");
    while !prompted.exists() && start.elapsed() < std::time::Duration::from_secs(15) {
        std::thread::sleep(std::time::Duration::from_millis(20));
    }
    fs::write(&c.stop_marker, b"stop owned run").unwrap();
    let result = worker.join().unwrap().unwrap();
    write_json(
        &PathBuf::from(std::env::var_os("CRAFT_TEST_ROOT").expect("CRAFT_TEST_ROOT must be explicit")).join("cancel-result.json"),
        &result,
    )
    .unwrap();
    assert!(prompted.exists());
    assert_eq!(result["state"], "stopped");
    assert_eq!(result["accepted"], false);
    let completion = &result["actual_turns"][0]["completion"];
    assert_eq!(completion["cancelAcknowledged"], true);
    assert_eq!(completion["queueCleared"], true);
    assert_eq!(completion["abortIdle"], true);
    assert_eq!(
        result["cleanup"]["owner_resources"]["status"],
        "observed-empty"
    );
    assert!(!c.workspace.join(".craft-pi-executor-owner.json").exists());
}
#[test]
fn source_drift_missing_policy_and_single_writer_fail_before_turn() {
    let dir = tempfile::tempdir().unwrap();
    let c = fixture(dir.path());
    fs::write(c.workspace.join("app/src/main.rs"), "drift").unwrap();
    assert!(
        execute_with_runtime(
            c.clone(),
            peer(),
            env!("CARGO_BIN_EXE_craft-pi-executor").into()
        )
        .is_err()
    );
    assert!(!c.run_root.exists());
    let dir = tempfile::tempdir().unwrap();
    let c = fixture(dir.path());
    fs::write(
        c.workspace.join(".craft-pi-executor-owner.json"),
        "other owner",
    )
    .unwrap();
    assert!(
        execute_with_runtime(
            c.clone(),
            peer(),
            env!("CARGO_BIN_EXE_craft-pi-executor").into()
        )
        .is_err()
    );
    assert!(!c.run_root.exists());
    fs::write(&c.policy, "{}").unwrap();
    assert!(c.policy().is_err());
}
#[test]
fn invalid_planned_admission_leaves_no_workspace_lease_run_root_or_model() {
    for variant in [
        "task",
        "command-root",
        "scenario-task",
        "reserved-key",
        "duplicate-key",
        "app-binding",
    ] {
        let dir = tempfile::tempdir().unwrap();
        let mut c = fixture(dir.path());
        let mut p = c.policy().unwrap();
        c.create_workspace = true;
        c.workspace = dir.path().join("not-created-workspace");
        p.app_root = c.workspace.join("app");
        p.writable_roots = vec![p.app_root.clone()];
        p.commands[0].cwd = p.app_root.clone();
        p.source_base_sha256 =
            "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855".into();
        match variant {
            "task" => p.identity.task_ids.clear(),
            "command-root" => p.commands[0].cwd = dir.path().to_path_buf(),
            "scenario-task" => {
                let output = &mut p.baseline.artifacts[0].output;
                let mut value: Value =
                    serde_json::from_slice(&fs::read(&output.path).unwrap()).unwrap();
                value["task_id"] = json!("not-selected");
                write_json(&output.path, &value).unwrap();
                output.sha256 = hash_file(&output.path).unwrap();
            }
            "reserved-key" => c.credential_env_keys = vec!["NODE_OPTIONS".into()],
            "duplicate-key" => c.credential_env_keys = vec!["TASK_KEY".into(), "task_key".into()],
            _ => p.app_root = dir.path().join("wrong-app"),
        }
        write_json(&c.policy, &p).unwrap();
        c.policy_sha256 = hash_file(&c.policy).unwrap();
        assert!(
            execute_with_runtime(
                c.clone(),
                peer(),
                env!("CARGO_BIN_EXE_craft-pi-executor").into()
            )
            .is_err(),
            "{variant}"
        );
        assert!(!c.workspace.exists(), "{variant}: workspace created");
        assert!(!c.run_root.exists(), "{variant}: run root created");
    }
}
#[test]
fn refine_threshold_mismatch_has_no_writes_and_matching_feedback_is_admitted() {
    let dir = tempfile::tempdir().unwrap();
    let mut c = fixture(dir.path());
    let mut p = c.policy().unwrap();
    p.mode = ExecutionMode::RefineOnly;
    let failed = craft_anything_engine::workspace::CheckResult::new(
        "external-scenario",
        1,
        false,
        "persistence check failed",
    );
    let mut feedback = RefineFeedback {
        version: 1,
        source_base_sha256: p.source_base_sha256.clone(),
        check_plan_sha256: p.check_plan_ref.sha256.clone(),
        task_ids: p.identity.task_ids.clone(),
        good_enough: 80.0,
        failed_checks: vec![FailedRequiredCheck {
            id: "external-scenario".into(),
            task_ids: p.identity.task_ids.clone(),
            result: failed,
        }],
    };
    let feedback_path = dir.path().join("reviewed-failure.json");
    write_json(&feedback_path, &feedback).unwrap();
    p.failed_feedback = Some(HashedRef {
        path: feedback_path.clone(),
        sha256: hash_file(&feedback_path).unwrap(),
    });
    write_json(&c.policy, &p).unwrap();
    c.policy_sha256 = hash_file(&c.policy).unwrap();
    let before = fs::read(c.workspace.join("craft.json")).unwrap();
    assert!(
        execute_with_runtime(
            c.clone(),
            peer(),
            env!("CARGO_BIN_EXE_craft-pi-executor").into()
        )
        .is_err()
    );
    assert_eq!(fs::read(c.workspace.join("craft.json")).unwrap(), before);
    assert!(!c.run_root.exists());
    assert!(!c.workspace.join(".craft-pi-executor-owner.json").exists());
    feedback.good_enough = GOOD_ENOUGH;
    write_json(&feedback_path, &feedback).unwrap();
    p.failed_feedback.as_mut().unwrap().sha256 = hash_file(&feedback_path).unwrap();
    write_json(&c.policy, &p).unwrap();
    c.policy_sha256 = hash_file(&c.policy).unwrap();
    c.validate_resources().unwrap();
    assert!(!c.run_root.exists());
    assert_eq!(fs::read(c.workspace.join("craft.json")).unwrap(), before);
}
#[test]
fn reviewed_provider_definition_is_minimal_env_reference_and_hash_bound() {
    let dir = tempfile::tempdir().unwrap();
    let c = fixture(dir.path());
    let p = c.policy().unwrap();
    let definition = json!({"providers":{"fixture":{"api":"openai-responses","baseUrl":"https://example.invalid","apiKey":"${FIXTURE_CREDENTIAL}","models":[{"id":"offline","api":"openai-responses","reasoning":true,"thinkingLevelMap":{"high":"high"},"maxTokens":4096}]}}});
    let reference = reference(
        &dir.path().join("provider.json"),
        &serde_json::to_vec(&definition).unwrap(),
    );
    let keys = vec!["FIXTURE_CREDENTIAL".into()];
    let approved = provider::validate(&reference, &p, &keys).unwrap();
    assert_eq!(
        approved["providers"]["fixture"]["models"][0]["thinkingLevelMap"]["high"],
        "high"
    );
    for mutation in 0..4 {
        let mut bad = definition.clone();
        match mutation {
            0 => bad["providers"]["fixture"]["apiKey"] = json!("literal-test-sentinel-not-a-key"),
            1 => bad["providers"]["fixture"]["headers"] = json!({"Authorization":"test-sentinel"}),
            2 => bad["providers"]["extra"] = json!({}),
            _ => bad["providers"]["fixture"]["models"][0]["maxTokens"] = json!(128),
        }
        write_json(&reference.path, &bad).unwrap();
        let changed = HashedRef {
            path: reference.path.clone(),
            sha256: hash_file(&reference.path).unwrap(),
        };
        assert!(provider::validate(&changed, &p, &keys).is_err());
        assert!(provider::validate(&reference, &p, &keys).is_err());
    }
}
#[test]
fn probe_drops_credentials_node_hooks_and_suppresses_failure_diagnostics() {
    use craft_anything_platform::Process;
    use std::time::Duration;
    let dir = tempfile::tempdir().unwrap();
    let script = dir.path().join("probe.cjs");
    let injection = dir.path().join("inject.cjs");
    let marker = dir.path().join("injected");
    fs::write(
        &injection,
        format!(
            "require('node:fs').writeFileSync({},'injected')",
            serde_json::to_string(&marker.display().to_string()).unwrap()
        ),
    )
    .unwrap();
    fs::write(&script,"if(process.env.FAKE_PROVIDER_KEY||process.env.NODE_OPTIONS||process.env.PI_CODING_AGENT_DIR)process.exit(8);console.log('1.5.0');").unwrap();
    let run = |ms: &str| {
        Process::new(env!("CARGO_BIN_EXE_probe-fixture"))
            .args([std::env::var("CRAFT_TEST_NODE").expect("CRAFT_TEST_NODE must be explicit").as_str(), script.to_str().unwrap(), ms])
            .env("FAKE_PROVIDER_KEY", "PUBLIC-PROBE-SENTINEL")
            .env("PI_CODING_AGENT_DIR", "PUBLIC-PROBE-SENTINEL")
            .env(
                "NODE_OPTIONS",
                format!("--require=\"{}\"", injection.display()),
            )
            .timeout(Duration::from_secs(5))
            .run()
            .unwrap()
    };
    let output = run("1000");
    assert!(output.success, "{}", output.stdout_text());
    assert!(!marker.exists());
    fs::write(&script,"console.log('PUBLIC-PROBE-SENTINEL');console.error('PUBLIC-PROBE-SENTINEL');process.exit(7);").unwrap();
    let output = run("1000");
    assert!(!output.success);
    assert!(!output.stdout_text().contains("PUBLIC-PROBE-SENTINEL"));
    assert!(output.stdout_text().contains("stdout_bytes"));
    fs::write(
        &script,
        "console.error('PUBLIC-PROBE-SENTINEL');setInterval(()=>{},1000);",
    )
    .unwrap();
    let output = run("100");
    assert!(!output.success);
    assert!(!output.stdout_text().contains("PUBLIC-PROBE-SENTINEL"));
    assert!(output.stdout_text().contains("process-error"));
}
#[test]
fn public_adapter_maps_session_tools_usage_and_error_without_turn_done() {
    let adapter = Arc::new(adapter::PiAdapter::new("explicit-config.json".into()));
    let mut adapters = AgentAdapters::built_in();
    adapters.register(adapter);
    let selected = adapters.for_agent("pi");
    assert!(!selected.plain_fallback());
    assert!(selected.prompt_on_stdin());
    let mut p = StreamParser::new(selected);
    assert!(p.line(r#"{"type":"bridge_session","sessionId":"exact","sessionFile":"exact.jsonl","headerVerified":true}"#).is_empty());
    assert_eq!(p.session_id.as_deref(), Some("exact"));
    assert_eq!(p.run_session, p.session_id);
    let e=p.line(r#"{"type":"tool_execution_start","toolCallId":"c1","toolName":"mcp__craft__build_file_write","args":{"path":"app/a"}}"#);
    assert!(matches!(e[0], AgentEvent::ToolStarted { .. }));
    let e =
        p.line(r#"{"type":"tool_execution_end","toolCallId":"c1","result":{},"isError":false}"#);
    assert!(matches!(e[0], AgentEvent::ToolFinished { ok: true, .. }));
    assert!(p.line(r#"{"type":"bridge_complete","usage":{"input":10,"cache_read":2,"cache_write":3,"output":4,"estimated_cost":0.1}}"#).is_empty());
    assert_eq!(p.input_tokens, 15);
    assert_eq!(p.output_tokens, 4);
    assert!(matches!(
        p.line(r#"{"type":"bridge_failure","code":"model_mismatch","detail":"wrong"}"#)[0],
        AgentEvent::Error { .. }
    ));
    assert!(p.failure.is_some());
}

fn production_handoff(root: &Path) -> handoff::Handoff {
    use handoff::*;
    let legacy = fixture(root);
    let p = legacy.policy().unwrap();
    let authority=AuthorityRefs {
        case:reference(&root.join("case.md"),b"Controlled console formatting case. Designed test authority; not official REA Evidence."),
        scope:reference(&root.join("scope.md"),b"Implement T002 only in the approved console source copy. Preserve original observations."),
        workitem:reference(&root.join("workitem.md"),b"W-console: persist supplied name; dependency T001 ready."),
        feature:reference(&root.join("feature.md"),b"F-console: local persisted console response."),
        spec:reference(&root.join("spec.md"),b"Designed contract: input Ada; ordered saved: Ada newline and persisted state bytes Ada. Invalid behavior is not accepted."),
        plan:reference(&root.join("plan.md"),b"Use supplied Rust project and frozen build command. Independent state hash oracle checks fresh copies."),
        tasks:reference(&root.join("tasks.md"),b"# Tasks
- [X] T001 Freeze designed console observation
- [ ] T002 Implement persistence
"),
        acceptance:reference(&root.join("acceptance.md"),b"Lead retains acceptance; candidate only. Original user TASK is the test-development authorization; third-party Evidence n/a: owned designed fixture."),
    };
    let selection = TaskSelection {
        version: 1,
        spec: authority.spec.clone(),
        tasks: authority.tasks.clone(),
        selected_tasks: vec![SelectedTask {
            id: "T002".into(),
            depends_on: vec!["T001".into()],
        }],
        dependencies_ready: vec!["T001".into()],
    };
    let selection_path = root.join("selection.json");
    write_json(&selection_path, &selection).unwrap();
    let selection_ref = HashedRef {
        path: selection_path.clone(),
        sha256: hash_file(&selection_path).unwrap(),
    };
    let provider=reference(&root.join("provider.json"),br#"{"providers":{"fixture":{"api":"openai-responses","baseUrl":"https://example.invalid","apiKey":"${TASK_PROVIDER_KEY}","models":[{"id":"offline","api":"openai-responses","reasoning":true,"thinkingLevelMap":{"high":"high"},"maxTokens":4096}]}}}"#);
    let mut scenario: Value =
        serde_json::from_slice(&fs::read(&p.baseline.artifacts[0].output.path).unwrap()).unwrap();
    scenario["task_id"] = json!("T002");
    write_json(&p.baseline.artifacts[0].output.path, &scenario).unwrap();
    let mut baseline = p.baseline.clone();
    baseline.artifacts[0].output.sha256 = hash_file(&baseline.artifacts[0].output.path).unwrap();
    let mut h=Handoff {version:1,authority,lead_decision:selection_ref.clone(),selection:selection_ref,original:p.original.clone(),baseline,check_plan:p.check_plan_ref.clone(),workspace:root.join("prepared-workspace"),application:ApplicationSource::Copy{root:p.app_root.clone(),source_sha256:p.source_base_sha256.clone()},owner_output:root.join("prepared-owner"),writable_relative:vec![".".into()],protected_relative:vec!["Cargo.toml".into(),"rust-toolchain.toml".into()],read_references:vec![],stack:p.stack.clone(),commands:p.commands.iter().map(|c|Command{command:c.command.clone(),timeout_secs:c.timeout_secs}).collect(),build:p.build.clone().unwrap(),model:p.model.clone(),driver:HashedRef{path:legacy.driver.clone(),sha256:legacy.driver_sha256.clone()},instructions:HashedRef{path:legacy.instructions.clone(),sha256:legacy.instructions_sha256.clone()},provider_manifest:provider,credential_env_keys:vec!["TASK_PROVIDER_KEY".into()],owner_id:new_id(),budget:Budget{wall_secs:120,max_refinements:2,response_max_tokens:4096,aggregate:AggregateBudget::AuditOnly,coordination_usage:CoordinationUsage::Unknown{reason:"External test coordinator not metered; no total-cost enforcement claim".into()}},stop_marker:root.join("prepared-stop"),message:"Implement T002 persistence in app/src/main.rs only; use frozen tools. Missing observations return to original case.".into()};
    bind_lead(root, &mut h);
    h
}
fn bind_lead(root: &Path, h: &mut handoff::Handoff) {
    use handoff::*;
    let selected: TaskSelection =
        serde_json::from_slice(&fs::read(&h.selection.path).unwrap()).unwrap();
    let lead=reference(&root.join("lead.md"),b"Controlled fixture lead decision: accept these designed source/behavior refs for T002 implementation only; not a user authorization password, no REA acceptance claim.");
    let decision = LeadDecision {
        version: 1,
        decision: Decision::Accepted,
        authority: h.authority.clone(),
        selection: h.selection.clone(),
        selected_task_ids: selected
            .selected_tasks
            .iter()
            .map(|t| t.id.clone())
            .collect(),
        lead_ref: lead,
        approved: ApprovedExecution {
            original: h.original.clone(),
            baseline: h.baseline.clone(),
            driver: h.driver.clone(),
            instructions: h.instructions.clone(),
            provider_manifest: h.provider_manifest.clone(),
            credential_env_keys: h.credential_env_keys.clone(),
            owner_output: h.owner_output.clone(),
            owner_id: h.owner_id.clone(),
            stop_marker: h.stop_marker.clone(),
            message: h.message.clone(),
            writable_relative: h.writable_relative.clone(),
            protected_relative: h.protected_relative.clone(),
            read_references: h.read_references.clone(),
            workspace: h.workspace.clone(),
            application: h.application.clone(),
            target: h.original.target.clone(),
            target_identity: h.original.target_identity.clone(),
            stack: h.stack.clone(),
            check_plan: h.check_plan.clone(),
            model: h.model.clone(),
            commands: h.commands.clone(),
            build: h.build.clone(),
            budget: h.budget.clone(),
        },
    };
    let path = root.join("lead-decision.json");
    write_json(&path, &decision).unwrap();
    h.lead_decision = HashedRef {
        sha256: hash_file(&path).unwrap(),
        path,
    };
}
#[test]
fn production_prepare_console_handoff_runs_actual_craft_without_native_fixture() {
    let dir = retained_fixture_dir();
    let h = production_handoff(&dir);
    let input = dir.join("handoff.json");
    write_json(&input, &h).unwrap();
    let dry = prepare::run(&input, false).unwrap();
    assert_eq!(dry["state"], "validated");
    assert!(!h.workspace.exists());
    assert!(!h.owner_output.exists());
    let cli = craft_anything_platform::Process::new(env!("CARGO_BIN_EXE_craft-pi-executor"))
        .args(["--prepare", input.to_str().unwrap()])
        .timeout(std::time::Duration::from_secs(10))
        .run()
        .unwrap();
    assert!(cli.success, "{}", cli.stderr_text());
    let prepared: Value = serde_json::from_slice(&cli.stdout).unwrap();
    assert_eq!(prepared["state"], "prepared");
    assert_eq!(prepared["model_calls"], 0);
    let ws = Workspace::open(&h.workspace).unwrap();
    assert_eq!(ws.manifest.target, h.original.target);
    assert!(!ws.capture_dir().exists());
    let c = ExecutionConfig::load(&h.owner_output.join("execution.json")).unwrap();
    // Tests run serially. Install only this synthetic name before any execution thread and
    // restore it after execute has joined/drained every owned thread. No real credential used.
    let previous = std::env::var_os("TASK_PROVIDER_KEY");
    unsafe {
        std::env::set_var("TASK_PROVIDER_KEY", "offline-synthetic-credential-Z7Q9");
    }
    let result = execute_with_runtime(
        c.clone(),
        peer(),
        env!("CARGO_BIN_EXE_craft-pi-executor").into(),
    );
    unsafe {
        if let Some(value) = previous {
            std::env::set_var("TASK_PROVIDER_KEY", value);
        } else {
            std::env::remove_var("TASK_PROVIDER_KEY");
        }
    }
    let result = result.unwrap();
    write_json(&dir.join("production-result.json"), &result).unwrap();
    assert_eq!(result["state"], "candidate", "{result}");
    assert_eq!(result["accepted"], false);
    assert_eq!(result["return_summary"], Value::Null);
    assert_eq!(
        result["external_qualifications"][0]["origin"],
        "external/observation"
    );
    assert_eq!(
        fs::read(&h.authority.tasks.path).unwrap(),
        b"# Tasks
- [X] T001 Freeze designed console observation
- [ ] T002 Implement persistence
"
    );
}
#[test]
fn production_prepare_admission_rejects_gaps_without_resources_then_accepts_repaired_refs() {
    for kind in [
        "missing-baseline",
        "missing-decision",
        "missing-acceptance",
        "wrong-task",
        "unfinished-dependency",
        "hash-drift",
        "model-permission",
        "target-scope",
        "strict-budget",
        "needs-spec",
        "needs-scope",
    ] {
        let d = tempfile::tempdir().unwrap();
        let mut h = production_handoff(d.path());
        match kind {
            "missing-baseline" => h.baseline.artifacts.clear(),
            "missing-decision" => h.lead_decision.path = d.path().join("missing.json"),
            "missing-acceptance" => {
                h.authority.acceptance.path = d.path().join("missing-acceptance.md")
            }
            "wrong-task" => {
                let mut s: handoff::TaskSelection =
                    serde_json::from_slice(&fs::read(&h.selection.path).unwrap()).unwrap();
                s.selected_tasks[0].id = "T999".into();
                write_json(&h.selection.path, &s).unwrap();
                h.selection.sha256 = hash_file(&h.selection.path).unwrap();
                bind_lead(d.path(), &mut h);
            }
            "unfinished-dependency" => {
                h.authority.tasks = reference(
                    &h.authority.tasks.path,
                    b"- [ ] T001 Freeze observation
- [ ] T002 Implement
",
                );
                let mut selection: handoff::TaskSelection =
                    serde_json::from_slice(&fs::read(&h.selection.path).unwrap()).unwrap();
                selection.tasks = h.authority.tasks.clone();
                write_json(&h.selection.path, &selection).unwrap();
                h.selection.sha256 = hash_file(&h.selection.path).unwrap();
                bind_lead(d.path(), &mut h);
            }
            "hash-drift" => {
                fs::write(&h.authority.case.path, b"drift").unwrap();
            }
            "model-permission" => {
                h.model.allowed = false;
                bind_lead(d.path(), &mut h);
            }
            "target-scope" => h.original.target_identity = "0".repeat(64),
            "strict-budget" => h.budget.aggregate = handoff::AggregateBudget::Strict,
            "needs-spec" | "needs-scope" => {
                let mut decision: handoff::LeadDecision =
                    serde_json::from_slice(&fs::read(&h.lead_decision.path).unwrap()).unwrap();
                decision.decision = if kind == "needs-spec" {
                    handoff::Decision::NeedsSpec
                } else {
                    handoff::Decision::NeedsScope
                };
                write_json(&h.lead_decision.path, &decision).unwrap();
                h.lead_decision.sha256 = hash_file(&h.lead_decision.path).unwrap();
            }
            _ => unreachable!(),
        }
        let input = d.path().join("handoff.json");
        write_json(&input, &h).unwrap();
        let err = prepare::run(&input, true).unwrap_err();
        assert!(
            err.details.as_ref().unwrap()["return_summary"].is_object(),
            "{kind}: {err:?}"
        );
        assert!(!h.workspace.exists(), "{kind}");
        assert!(!h.owner_output.exists(), "{kind}");
    }
    let d = tempfile::tempdir().unwrap();
    let mut h = production_handoff(d.path());
    h.budget.aggregate = handoff::AggregateBudget::Strict;
    let input = d.path().join("handoff.json");
    write_json(&input, &h).unwrap();
    assert!(prepare::run(&input, true).is_err());
    h.budget.aggregate = handoff::AggregateBudget::AuditOnly;
    bind_lead(d.path(), &mut h);
    write_json(&input, &h).unwrap();
    assert_eq!(prepare::run(&input, true).unwrap()["state"], "prepared");
}

#[test]
fn prepare_existing_and_explicit_empty_layouts_and_input_diagnostics_are_bounded() {
    let d = tempfile::tempdir().unwrap();
    let mut h = production_handoff(d.path());
    let source = match &h.application {
        handoff::ApplicationSource::Copy { root, .. } => root.clone(),
        _ => unreachable!(),
    };
    h.workspace = source.parent().unwrap().to_path_buf();
    h.application = handoff::ApplicationSource::ExistingWorkspace {
        source_sha256: source_digest(&source).unwrap(),
    };
    bind_lead(d.path(), &mut h);
    let input = d.path().join("existing.json");
    write_json(&input, &h).unwrap();
    let original = fs::read(h.workspace.join("craft.json")).unwrap();
    prepare::run(&input, true).unwrap();
    assert_eq!(fs::read(h.workspace.join("craft.json")).unwrap(), original);
    let d = tempfile::tempdir().unwrap();
    let mut h = production_handoff(d.path());
    h.application = handoff::ApplicationSource::Empty;
    bind_lead(d.path(), &mut h);
    let input = d.path().join("empty.json");
    write_json(&input, &h).unwrap();
    prepare::run(&input, true).unwrap();
    assert_eq!(
        source_digest(&h.workspace.join("app")).unwrap(),
        "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
    );
    let bad = d.path().join("bad.json");
    fs::write(
        &bad,
        br#"{"version":"PRIVATE-INPUT-SENTINEL","provider":{"apiKey":"PRIVATE-KEY-SENTINEL"}}"#,
    )
    .unwrap();
    let output = craft_anything_platform::Process::new(env!("CARGO_BIN_EXE_craft-pi-executor"))
        .args(["--prepare", bad.to_str().unwrap()])
        .run()
        .unwrap();
    assert!(!output.success);
    assert!(!output.stderr_text().contains("PRIVATE-INPUT-SENTINEL"));
    assert!(!output.stderr_text().contains("PRIVATE-KEY-SENTINEL"));
}
#[test]
fn typed_check_return_needs_evidence_and_cleanup_unknown_preserves_cause() {
    use craft_anything_ai::rebuild::*;
    let d = tempfile::tempdir().unwrap();
    let h = production_handoff(d.path());
    let input = d.path().join("handoff.json");
    write_json(&input, &h).unwrap();
    prepare::run(&input, true).unwrap();
    let c = ExecutionConfig::load(&h.owner_output.join("execution.json")).unwrap();
    let p = c.policy().unwrap();
    let refs = CheckSourceRefs {
        case_ref: p.identity.case_ref.clone(),
        scope_ref: p.identity.scope_ref.clone(),
        workitem_ref: p.identity.workitem_ref.clone(),
        feature_ref: p.identity.feature_ref.clone(),
        acceptance_ref: p.identity.acceptance_ref.clone(),
        bundle_ref: p.original.bundle.clone(),
        check_plan_ref: p.check_plan_ref.clone(),
        baseline_refs: p
            .baseline
            .artifacts
            .iter()
            .flat_map(|a| [a.source.clone(), a.output.clone()])
            .collect(),
        source_base_sha256: p.source_base_sha256.clone(),
    };
    let report = CheckPlanReport {
        version: CHECK_PLAN_REPORT_VERSION,
        owner: p.owner_id.clone(),
        round: 1,
        affected_tasks: p.identity.task_ids.clone(),
        source_refs: refs,
        qualifications: vec![],
        checks: vec![PlannedCheckRecord {
            id: "external-scenario".into(),
            round: 1,
            required: true,
            disposition: CheckDisposition::NeedsEvidence,
            return_to: CheckReturnTo::OriginalPrimary,
            reason_code: CheckReasonCode::MissingEvidence,
            reason: "PRIVATE-DIAGNOSTIC-SENTINEL".into(),
        }],
    };
    let summary = return_summary::from_execution(&c, &p, Some(&report), false, false)
        .unwrap()
        .unwrap();
    let json = serde_json::to_value(&summary).unwrap();
    assert_eq!(json["disposition"], "needs-evidence");
    assert_eq!(json["return_to"], "original-primary");
    assert_eq!(json["affected_tasks"], json!(["T002"]));
    assert!(!json.to_string().contains("PRIVATE-DIAGNOSTIC"));
    let outcome =
        json!({"state":"blocked-cleanup","cleanup":{"closed":false},"return_summary":summary});
    assert_eq!(outcome["return_summary"]["disposition"], "needs-evidence");
}

#[test]
fn required_missing_runtime_stops_after_one_real_builder_and_returns_original_refs() {
    let dir = retained_fixture_dir();
    let mut h = production_handoff(&dir);
    let artifact = &mut h.baseline.artifacts[0];
    let mut scenario: Value =
        serde_json::from_slice(&fs::read(&artifact.output.path).unwrap()).unwrap();
    scenario["runtime_files"] = json!(["required-but-unavailable.dll"]);
    write_json(&artifact.output.path, &scenario).unwrap();
    artifact.output.sha256 = hash_file(&artifact.output.path).unwrap();
    bind_lead(&dir, &mut h);
    let input = dir.join("handoff.json");
    write_json(&input, &h).unwrap();
    prepare::run(&input, true).unwrap();
    let c = ExecutionConfig::load(&h.owner_output.join("execution.json")).unwrap();
    let previous = std::env::var_os("TASK_PROVIDER_KEY");
    unsafe {
        std::env::set_var("TASK_PROVIDER_KEY", "offline-synthetic-credential-Z7Q9");
    }
    let result = execute_with_runtime(
        c.clone(),
        peer(),
        env!("CARGO_BIN_EXE_craft-pi-executor").into(),
    );
    unsafe {
        if let Some(value) = previous {
            std::env::set_var("TASK_PROVIDER_KEY", value);
        } else {
            std::env::remove_var("TASK_PROVIDER_KEY");
        }
    }
    let result = result.unwrap();
    write_json(&dir.join("return-result.json"), &result).unwrap();
    assert_eq!(
        result["actual_turns"].as_array().unwrap().len(),
        1,
        "{result}"
    );
    assert_ne!(result["state"], "candidate");
    assert_eq!(result["return_summary"]["disposition"], "needs-evidence");
    assert_eq!(result["return_summary"]["return_to"], "original-primary");
    assert_eq!(result["return_summary"]["affected_tasks"], json!(["T002"]));
    assert_eq!(
        result["return_summary"]["refs"]["authority"]["case"]["sha256"],
        h.authority.case.sha256
    );
    assert!(!c.run_root.join("turn-2").exists());
}

#[test]
fn original_decision_rejects_post_prepare_source_model_and_budget_rebinding() {
    for mutation in [
        "source",
        "model",
        "wall",
        "refinements",
        "context-self-rehash",
    ] {
        let d = tempfile::tempdir().unwrap();
        let h = production_handoff(d.path());
        let input = d.path().join("handoff.json");
        write_json(&input, &h).unwrap();
        prepare::run(&input, true).unwrap();
        let config = h.owner_output.join("execution.json");
        let mut c = ExecutionConfig::load(&config).unwrap();
        let mut p = c.policy().unwrap();
        match mutation {
            "source" => {
                fs::write(
                    h.workspace.join("app/src/main.rs"),
                    r#"fn main(){println!("unapproved");}"#,
                )
                .unwrap();
                p.source_base_sha256 = source_digest(&h.workspace.join("app")).unwrap();
            }
            "model" => p.model.expected.model = "other-model".into(),
            "wall" => p.max_wall_secs = 119,
            "refinements" => c.max_refinements = 1,
            _ => {
                let mut changed = h.clone();
                changed.budget.max_refinements = 1;
                write_json(&input, &changed).unwrap();
                let mut context: return_summary::Context = serde_json::from_slice(
                    &fs::read(&c.handoff_context.as_ref().unwrap().path).unwrap(),
                )
                .unwrap();
                context.handoff.as_mut().unwrap().sha256 = hash_file(&input).unwrap();
                write_json(&c.handoff_context.as_ref().unwrap().path, &context).unwrap();
                c.handoff_context.as_mut().unwrap().sha256 =
                    hash_file(&c.handoff_context.as_ref().unwrap().path).unwrap();
                c.max_refinements = 1;
            }
        }
        write_json(&c.policy, &p).unwrap();
        c.policy_sha256 = hash_file(&c.policy).unwrap();
        write_json(&config, &c).unwrap();
        let error = ExecutionConfig::load(&config).unwrap_err();
        assert!(
            error
                .details
                .as_ref()
                .is_some_and(|d| d["reason"] == "handoff-execution-mismatch"),
            "{mutation}: {error:?}"
        );
        assert!(!c.run_root.exists());
        assert!(!c.workspace.join(".craft-pi-executor-owner.json").exists());
    }
}
#[test]
fn invalid_execution_field_and_selection_ids_never_echo_private_sentinel() {
    let d = tempfile::tempdir().unwrap();
    let bad = d.path().join("execution.json");
    fs::write(&bad, br#"{"PRIVATE-FIELD-SENTINEL":"body"}"#).unwrap();
    let output = craft_anything_platform::Process::new(env!("CARGO_BIN_EXE_craft-pi-executor"))
        .args(["--run", bad.to_str().unwrap()])
        .run()
        .unwrap();
    assert!(!output.success);
    assert!(!output.stderr_text().contains("PRIVATE-FIELD-SENTINEL"));
    assert!(output.stderr_text().contains("invalid-execution-json"));
    let mut h = production_handoff(d.path());
    let mut selection: handoff::TaskSelection =
        serde_json::from_slice(&fs::read(&h.selection.path).unwrap()).unwrap();
    selection.selected_tasks[0].id = "PRIVATE-TASK-SENTINEL".into();
    write_json(&h.selection.path, &selection).unwrap();
    h.selection.sha256 = hash_file(&h.selection.path).unwrap();
    let input = d.path().join("handoff.json");
    write_json(&input, &h).unwrap();
    let output = craft_anything_platform::Process::new(env!("CARGO_BIN_EXE_craft-pi-executor"))
        .args(["--prepare", input.to_str().unwrap()])
        .run()
        .unwrap();
    assert!(!output.success);
    assert!(!output.stdout_text().contains("PRIVATE-TASK-SENTINEL"));
    assert!(!output.stderr_text().contains("PRIVATE-TASK-SENTINEL"));
    let json: Value = serde_json::from_str(output.stderr_text().trim()).unwrap();
    assert_eq!(json["return_summary"]["affected_tasks"], json!([]));
    assert_eq!(json["return_summary"]["refs"]["selected_tasks"], json!([]));
    assert!(!h.workspace.exists());
    assert!(!h.owner_output.exists());
}
