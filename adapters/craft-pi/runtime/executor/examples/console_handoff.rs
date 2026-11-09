//! Offline documented input example. Generates only hashed handoff/authority supplement files;
//! production prepare remains the real binary. No provider request or native fixture dependency.
use craft_anything_engine::{execution_policy::*, workspace::TargetRef};
use craft_pi_executor::{BACKEND_ID, PERMISSION, handoff::*, new_id, write_json};
use serde_json::json;
use std::{
    fs,
    path::{Path, PathBuf},
};
fn reference(path: &Path) -> Result<HashedRef, Box<dyn std::error::Error>> {
    Ok(HashedRef {
        path: fs::canonicalize(path)?,
        sha256: hash_file(path).map_err(|e| e.to_string())?,
    })
}
fn main() {
    if let Err(error) = run() {
        eprintln!("offline handoff example failed: {error}");
        std::process::exit(2);
    }
}
fn run() -> Result<(), Box<dyn std::error::Error>> {
    let args: Vec<_> = std::env::args_os().skip(1).collect();
    let [out, driver] = args.as_slice() else {
        return Err(
            "Usage: cargo run --example console_handoff -- ABS_FRESH_INPUT_DIR ABS_DRIVER".into(),
        );
    };
    let out = PathBuf::from(out);
    let driver = PathBuf::from(driver);
    if !out.is_absolute() || out.exists() || !driver.is_absolute() {
        return Err("Fresh absolute output and explicit driver required".into());
    }
    fs::create_dir_all(&out)?;
    let samples = Path::new(env!("CARGO_MANIFEST_DIR")).join("examples/console-inputs");
    for name in [
        "case.md",
        "scope.md",
        "workitem.md",
        "feature.md",
        "spec.md",
        "plan.md",
        "tasks.md",
        "acceptance.md",
        "lead.md",
        "instructions.md",
        "original-reference.txt",
    ] {
        fs::copy(samples.join(name), out.join(name))?;
    }
    let source = out.join("approved-source");
    fs::create_dir_all(source.join("src"))?;
    fs::copy(
        samples.join("approved-source/Cargo.toml"),
        source.join("Cargo.toml"),
    )?;
    fs::copy(
        samples.join("approved-source/src/main.rs"),
        source.join("src/main.rs"),
    )?;
    let authority = AuthorityRefs {
        case: reference(&out.join("case.md"))?,
        scope: reference(&out.join("scope.md"))?,
        workitem: reference(&out.join("workitem.md"))?,
        feature: reference(&out.join("feature.md"))?,
        spec: reference(&out.join("spec.md"))?,
        plan: reference(&out.join("plan.md"))?,
        tasks: reference(&out.join("tasks.md"))?,
        acceptance: reference(&out.join("acceptance.md"))?,
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
    write_json(&out.join("selection.json"), &selection).map_err(|e| e.to_string())?;
    let baseline = out.join("baseline");
    fs::create_dir(&baseline)?;
    let program = if cfg!(windows) {
        "target/debug/owned-console-sample.exe"
    } else {
        "target/debug/owned-console-sample"
    };
    fs::write(out.join("expected-state"), b"Ada")?;
    let scenario = json!({"version":2,"task_id":"T002","evidence_id":"owned-console-designed-observation","harness":"direct-exec-v1","reset":"fresh-copy-v1","program":program,"runtime_files":[],"seed_files":[{"relative_path":"state.txt","content":null}],"arguments":[],"stdin":"Ada\n","environment":{},"timeout_secs":10,"exit_code":0,"stdout":"saved: Ada\n","stderr":"","state_files":[{"relative_path":"state.txt","sha256":hash_file(&out.join("expected-state")).map_err(|e|e.to_string())?}]});
    write_json(&baseline.join("scenario.json"), &scenario).map_err(|e| e.to_string())?;
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
            baseline: Some("console".into()),
            kind: Some(BaselineKind::Scenario),
            depends_on: vec!["build".into()],
        },
    ];
    write_json(&out.join("check-plan.json"), &checks).map_err(|e| e.to_string())?;
    write_json(&out.join("observation.json"),&json!({"origin":"external/observation","authority":"raw-observation","designed":true,"behavior_ref":reference(&out.join("spec.md"))?,"limitations":["Owned designed test; no third-party capture; native REA claims unknown"]})).map_err(|e|e.to_string())?;
    // Deliberately synthetic provider definition for offline validation only; never an actual key.
    write_json(&out.join("models.offline.json"),&json!({"providers":{"fixture":{"api":"openai-responses","baseUrl":"https://example.invalid","apiKey":"${TASK_PROVIDER_KEY}","models":[{"id":"offline","api":"openai-responses","reasoning":true,"maxTokens":4096}]}}})).map_err(|e|e.to_string())?;
    let observation = reference(&out.join("observation.json"))?;
    let original_file = reference(&out.join("original-reference.txt"))?;
    let h=Handoff{version:1,authority:authority.clone(),lead_decision:reference(&out.join("lead.md"))?,selection:reference(&out.join("selection.json"))?,
        original:Original{target:TargetRef::Local{path:original_file.path.clone()},target_identity:original_file.sha256,bundle:observation.clone(),traceability:observation.clone(),scenarios:reference(&baseline.join("scenario.json"))?,qualifications:observation.clone(),environment:observation.clone()},
        baseline:ExternalBaseline{version:1,root:baseline.clone(),bundle_sha256:observation.sha256.clone(),artifacts:vec![ExternalArtifact{key:"console".into(),kind:BaselineKind::Scenario,origin_kind:ExternalOrigin::Observation,evidence_id:"owned-console-designed-observation".into(),operation:"designed-console-observation".into(),provider:"owned-fixture".into(),environment:"isolated local console".into(),authority:"raw-observation".into(),limitations:vec!["Designed fixture; no native REA claim".into()],source:observation,output:reference(&baseline.join("scenario.json"))?,converter_version:"identity-v1".into(),parameters:json!({}),field_mapping:json!({"state":"sha256"}),losses:vec![]}]},check_plan:reference(&out.join("check-plan.json"))?,workspace:out.join("workspace"),application:ApplicationSource::Copy{root:source.clone(),source_sha256:source_digest(&source).map_err(|e|e.to_string())?},owner_output:out.join("owner-batch"),writable_relative:vec![".".into()],protected_relative:vec!["Cargo.toml".into()],read_references:vec![],stack:"Rust (console)".into(),commands:vec![Command{command:"cargo build --offline --quiet".into(),timeout_secs:60}],build:BuildInvocation{command_index:0,artifacts:vec![program.into()]},model:ModelPermission{allowed:true,expected:ModelIdentity{provider:"fixture".into(),model:"offline".into(),effort:"high".into()},backend_id:BACKEND_ID.into(),permission_contract:PERMISSION.into()},driver:reference(&driver)?,instructions:reference(&out.join("instructions.md"))?,provider_manifest:reference(&out.join("models.offline.json"))?,credential_env_keys:vec!["TASK_PROVIDER_KEY".into()],owner_id:new_id(),budget:Budget{wall_secs:120,max_refinements:2,response_max_tokens:4096,aggregate:AggregateBudget::AuditOnly,coordination_usage:CoordinationUsage::Unknown{reason:"External coordinator usage not supplied".into()}},stop_marker:out.join("stop"),message:"Implement T002 only. Preserve original authority and independent fresh-copy expectations. Return missing evidence; do not research.".into()};
    let approved = ApprovedExecution {
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
    };
    let decision = LeadDecision {
        version: 1,
        decision: Decision::Accepted,
        authority,
        selection: h.selection.clone(),
        selected_task_ids: vec!["T002".into()],
        lead_ref: reference(&out.join("lead.md"))?,
        approved,
    };
    write_json(&out.join("lead-decision.json"), &decision).map_err(|e| e.to_string())?;
    let mut h = h;
    h.lead_decision = reference(&out.join("lead-decision.json"))?;
    write_json(&out.join("handoff.json"), &h).map_err(|e| e.to_string())?;
    println!(
        "{}",
        json!({"handoff":out.join("handoff.json"),"model_calls":0,"scope":"owned designed input example only; use real lead-reviewed provider/evidence for production"})
    );
    Ok(())
}
