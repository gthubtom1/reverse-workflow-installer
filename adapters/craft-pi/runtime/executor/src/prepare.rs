//! Deterministic production assembler. All authority/input validation precedes creation.
use crate::{
    handoff::*,
    return_summary::{CheckReason, Context, Disposition, Summary},
    *,
};
use craft_anything_engine::{
    execution_policy::{
        self as policy, AcceptedResearch, ExecutionMode, FrozenCommand, HashedRef, Identity,
        real_parent, source_digest,
    },
    workspace::Workspace,
};
use serde_json::{Value, json};
use std::collections::{BTreeMap, BTreeSet};

fn decode<T: serde::de::DeserializeOwned>(r: &HashedRef) -> Result<T, ToolError> {
    serde_json::from_slice(&r.read_verified()?).map_err(|_| {
        refusal(
            "unsupported-format",
            "Referenced machine record has an unsupported structure.",
        )
    })
}
fn same<T: serde::Serialize>(a: &T, b: &T) -> bool {
    serde_json::to_value(a).ok() == serde_json::to_value(b).ok()
}
fn all_refs(a: &AuthorityRefs) -> [&HashedRef; 8] {
    [
        &a.case,
        &a.scope,
        &a.workitem,
        &a.feature,
        &a.spec,
        &a.plan,
        &a.tasks,
        &a.acceptance,
    ]
}
pub(crate) fn task_id(s: &str) -> bool {
    s.len() >= 4 && s.starts_with('T') && s[1..].bytes().all(|b| b.is_ascii_digit())
}
fn tasks(r: &HashedRef) -> Result<BTreeMap<String, bool>, ToolError> {
    let bytes = r.read_verified()?;
    let text = std::str::from_utf8(&bytes).map_err(|_| {
        refusal(
            "unsupported-tasks-format",
            "Tasks must be UTF-8 standard Spec checkbox records.",
        )
    })?;
    let mut out = BTreeMap::new();
    for line in text.lines().map(str::trim) {
        if line.starts_with("- [") {
            let (done, tail) = if let Some(t) = line.strip_prefix("- [ ] ") {
                (false, t)
            } else if let Some(t) = line
                .strip_prefix("- [X] ")
                .or_else(|| line.strip_prefix("- [x] "))
            {
                (true, t)
            } else {
                return Err(refusal(
                    "unsupported-tasks-format",
                    "Unsupported Spec checkbox syntax.",
                ));
            };
            let id = tail.split_whitespace().next().unwrap_or("");
            if !task_id(id) || out.insert(id.into(), done).is_some() {
                return Err(refusal(
                    "unsupported-tasks-format",
                    "Expected unique T### IDs immediately after Spec checkboxes.",
                ));
            }
        }
    }
    if out.is_empty() {
        return Err(refusal(
            "unsupported-tasks-format",
            "No standard Spec task IDs found.",
        ));
    }
    Ok(out)
}
fn safe_path(path: &Path) -> Result<PathBuf, ToolError> {
    if !path.is_absolute() {
        return Err(refusal("path-denied", "Absolute paths required."));
    }
    let mut current = PathBuf::new();
    for part in path.components() {
        if matches!(part, std::path::Component::ParentDir) {
            return Err(refusal("path-denied", "Parent traversal refused."));
        }
        current.push(part.as_os_str());
        if let Ok(m) = fs::symlink_metadata(&current) {
            #[cfg(windows)]
            let reparse = {
                use std::os::windows::fs::MetadataExt;
                m.file_attributes() & 0x400 != 0
            };
            #[cfg(not(windows))]
            let reparse = false;
            if m.file_type().is_symlink() || reparse {
                return Err(refusal("path-denied", "Links and reparse paths refused."));
            }
        }
    }
    real_parent(path)
}
fn relative(root: &Path, path: &Path) -> Result<PathBuf, ToolError> {
    if path.is_absolute()
        || path.components().any(|c| {
            !matches!(
                c,
                std::path::Component::Normal(_) | std::path::Component::CurDir
            )
        })
    {
        return Err(refusal("path-denied", "App-relative capability required."));
    }
    safe_path(&root.join(path))
}
fn source_files(root: &Path) -> Result<Vec<(PathBuf, String)>, ToolError> {
    let mut found = Vec::new();
    let mut pending = vec![root.to_path_buf()];
    let mut count = 0;
    while let Some(dir) = pending.pop() {
        for entry in fs::read_dir(&dir).map_err(|e| ToolError::io(dir.display(), e))? {
            let entry =
                entry.map_err(|_| refusal("source-read", "Cannot enumerate approved source."))?;
            count += 1;
            if count > 20000 {
                return Err(refusal(
                    "input-limit",
                    "Approved source exceeds 20000 entries.",
                ));
            }
            let path = entry.path();
            safe_path(&path)?;
            if entry.file_name() == ".craft-owner.lock" {
                return Err(refusal(
                    "owner-conflict",
                    "Approved source is owned by an active or unresolved writer.",
                ));
            }
            if ["target", "node_modules", ".git"]
                .iter()
                .any(|name| entry.file_name() == *name)
            {
                continue;
            }
            let m = entry
                .metadata()
                .map_err(|_| refusal("source-read", "Cannot stat approved source."))?;
            if m.is_dir() {
                pending.push(path);
            } else if m.is_file() {
                found.push((
                    path.strip_prefix(root)
                        .map_err(|_| refusal("path-denied", "Source escape."))?
                        .to_path_buf(),
                    hash_file(&path)?,
                ));
            } else {
                return Err(refusal("path-denied", "Special source file refused."));
            }
        }
    }
    found.sort();
    Ok(found)
}
fn context(h: &Handoff, ids: Vec<String>) -> Context {
    Context {
        version: 1,
        authority: h.authority.clone(),
        selected_tasks: if ids.iter().all(|id| task_id(id)) {
            ids
        } else {
            vec![]
        },
        handoff: None,
        check_plan: h.check_plan.clone(),
        baseline: h.original.bundle.clone(),
        lead_decision: h.lead_decision.clone(),
        selection: h.selection.clone(),
    }
}
fn gate(h: &Handoff, ids: &[String], d: Disposition, code: &str) -> ToolError {
    let summary = Summary::new(
        context(h, ids.to_vec()),
        d,
        vec![CheckReason {
            id: "handoff".into(),
            reason_code: code.into(),
        }],
    );
    refusal(
        code,
        "Handoff cannot be executed; return to the original authority.",
    )
    .with_details(json!({"reason":code,"return_summary":summary}))
}
pub(crate) fn approved(h: &Handoff) -> ApprovedExecution {
    ApprovedExecution {
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
    }
}

fn construct(
    h: &Handoff,
    ids: &[String],
    app: &Path,
    output: &Path,
    digest: &str,
) -> Result<(AcceptedResearch, ExecutionConfig), ToolError> {
    let checks: CheckPlan = decode(&h.check_plan)?;
    let p = AcceptedResearch {
        version: 1,
        mode: ExecutionMode::Buildcheck,
        identity: Identity {
            case_ref: h.authority.case.clone(),
            scope_ref: h.authority.scope.clone(),
            workitem_ref: h.authority.workitem.clone(),
            feature_ref: h.authority.feature.clone(),
            acceptance_ref: h.authority.acceptance.clone(),
            task_ids: ids.to_vec(),
        },
        original: h.original.clone(),
        baseline: h.baseline.clone(),
        check_plan_ref: h.check_plan.clone(),
        checks,
        source_base_sha256: digest.into(),
        app_root: app.to_path_buf(),
        writable_roots: h
            .writable_relative
            .iter()
            .map(|r| relative(&app, r))
            .collect::<Result<_, _>>()?,
        protected_paths: h
            .protected_relative
            .iter()
            .map(|r| relative(&app, r))
            .collect::<Result<_, _>>()?,
        read_references: h.read_references.clone(),
        commands: h
            .commands
            .iter()
            .map(|c| FrozenCommand {
                command: c.command.clone(),
                cwd: app.to_path_buf(),
                timeout_secs: c.timeout_secs,
            })
            .collect(),
        build: Some(h.build.clone()),
        kind_id: "app".into(),
        stack: h.stack.clone(),
        model: h.model.clone(),
        owner_id: h.owner_id.clone(),
        max_wall_secs: h.budget.wall_secs,
        failed_feedback: None,
    };
    let c = ExecutionConfig {
        contract_version: 1,
        policy: output.join("accepted-policy.json"),
        policy_sha256: String::new(),
        workspace: h.workspace.clone(),
        create_workspace: false,
        run_root: output.join("run"),
        driver: h.driver.path.clone(),
        driver_sha256: h.driver.sha256.clone(),
        instructions: h.instructions.path.clone(),
        instructions_sha256: h.instructions.sha256.clone(),
        provider_manifest: Some(h.provider_manifest.clone()),
        credential_env_keys: h.credential_env_keys.clone(),
        max_refinements: h.budget.max_refinements,
        stop_marker: h.stop_marker.clone(),
        message: h.message.clone(),
        handoff_context: None,
    };

    Ok((p, c))
}

/// Reconstruct the only legal execution identity from the original immutable handoff and
/// lead decision. No self-updated policy/context/config digest is treated as new approval.
pub(crate) fn validate_execution_binding(
    c: &ExecutionConfig,
    p: &AcceptedResearch,
) -> Result<(), ToolError> {
    let Some(reference) = &c.handoff_context else {
        return Ok(());
    };
    let ctx: Context = serde_json::from_slice(&reference.read_verified()?)
        .map_err(|_| refusal("invalid-context", "Invalid typed handoff context."))?;
    let fail = || {
        refusal("handoff-execution-mismatch","Execution differs from original lead-approved handoff.").with_details(json!({"reason":"handoff-execution-mismatch","return_summary":Summary::new(ctx.clone(),Disposition::NeedsScope,vec![CheckReason{id:"handoff".into(),reason_code:"approved-execution-mismatch".into()}])}))
    };
    let h: Handoff = decode(ctx.handoff.as_ref().ok_or_else(fail)?)?;
    let decision: LeadDecision = decode(&h.lead_decision)?;
    decision.lead_ref.verify()?;
    let selection: TaskSelection = decode(&h.selection)?;
    let ids: Vec<_> = selection
        .selected_tasks
        .iter()
        .map(|t| t.id.clone())
        .collect();
    if ids.iter().any(|id| !task_id(id))
        || decision.decision != Decision::Accepted
        || !same(&decision.approved, &approved(&h))
        || !same(&decision.authority, &h.authority)
        || decision.selection != h.selection
        || decision.selected_task_ids != ids
        || !same(&ctx.authority, &h.authority)
        || ctx.selected_tasks != ids
        || ctx.lead_decision != h.lead_decision
        || ctx.selection != h.selection
        || ctx.check_plan != h.check_plan
        || ctx.baseline != h.original.bundle
    {
        return Err(fail());
    }
    let digest = match &h.application {
        ApplicationSource::ExistingWorkspace { source_sha256 }
        | ApplicationSource::Copy { source_sha256, .. } => source_sha256.clone(),
        ApplicationSource::Empty => {
            "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855".into()
        }
    };
    let app = safe_path(&h.workspace)?.join("app");
    let output = safe_path(&h.owner_output)?;
    let (expected_policy, expected_config) = construct(&h, &ids, &app, &output, &digest)?;
    // Original plan and generated copy may differ in JSON whitespace; typed content must be
    // identical and both references are independently rehashed. No arbitrary plan is allowed.
    let original_plan: CheckPlan = decode(&h.check_plan)?;
    let generated_plan: CheckPlan = decode(&p.check_plan_ref)?;
    if !same(&original_plan, &generated_plan)
        || safe_path(&p.check_plan_ref.path)? != output.join("check-plan.json")
    {
        return Err(fail());
    }
    let mut actual_policy = p.clone();
    actual_policy.check_plan_ref = h.check_plan.clone();
    if !same(&actual_policy, &expected_policy) {
        return Err(fail());
    }
    let mut actual_config = c.clone();
    actual_config.handoff_context = None;
    actual_config.policy_sha256 = String::new();
    if !same(&actual_config, &expected_config) {
        return Err(fail());
    }
    Ok(())
}

struct Assembly {
    h: Handoff,
    p: AcceptedResearch,
    c: ExecutionConfig,
    ctx: Context,
    source: Option<PathBuf>,
    files: Vec<(PathBuf, String)>,
}
fn assemble(h: Handoff) -> Result<Assembly, ToolError> {
    let mut ids = Vec::new();
    let selection: TaskSelection = decode(&h.selection)?;
    if selection
        .selected_tasks
        .iter()
        .any(|task| !task_id(&task.id) || task.depends_on.iter().any(|id| !task_id(id)))
        || selection.dependencies_ready.iter().any(|id| !task_id(id))
    {
        return Err(gate(&h, &[], Disposition::NeedsSpec, "unsupported-task-id"));
    }
    ids.extend(selection.selected_tasks.iter().map(|t| t.id.clone()));
    for r in all_refs(&h.authority).into_iter().chain([
        &h.lead_decision,
        &h.selection,
        &h.check_plan,
        &h.driver,
        &h.instructions,
        &h.provider_manifest,
    ]) {
        r.verify()?;
        if r.read_verified()?.iter().all(u8::is_ascii_whitespace) {
            return Err(gate(&h, &ids, Disposition::NeedsEvidence, "missing-input"));
        }
    }
    if h.version != 1 || selection.version != 1 {
        return Err(gate(
            &h,
            &ids,
            Disposition::Unsupported,
            "unsupported-version",
        ));
    }
    let decision: LeadDecision = decode(&h.lead_decision)?;
    decision.lead_ref.verify()?;
    if decision
        .lead_ref
        .read_verified()?
        .iter()
        .all(u8::is_ascii_whitespace)
    {
        return Err(gate(
            &h,
            &ids,
            Disposition::NeedsEvidence,
            "missing-lead-authority",
        ));
    }
    if decision.version != 1
        || !same(&decision.authority, &h.authority)
        || !same(&decision.selection, &h.selection)
        || decision.selected_task_ids != ids
    {
        return Err(gate(
            &h,
            &ids,
            Disposition::NeedsScope,
            "decision-binding-mismatch",
        ));
    }
    match decision.decision {
        Decision::NeedsScope => {
            return Err(gate(&h, &ids, Disposition::NeedsScope, "lead-needs-scope"));
        }
        Decision::NeedsSpec => {
            return Err(gate(&h, &ids, Disposition::NeedsSpec, "lead-needs-spec"));
        }
        Decision::Accepted => {}
    }
    if h.budget.aggregate != AggregateBudget::AuditOnly {
        return Err(gate(
            &h,
            &ids,
            Disposition::Unsupported,
            "unsupported-budget",
        ));
    }
    let expected = approved(&h);
    if decision.approved.target != expected.target
        || decision.approved.target_identity != expected.target_identity
        || decision.approved.workspace != expected.workspace
        || !same(&decision.approved.application, &expected.application)
    {
        return Err(gate(
            &h,
            &ids,
            Disposition::NeedsScope,
            "approved-target-source-mismatch",
        ));
    }
    if !same(&decision.approved, &expected) {
        return Err(gate(
            &h,
            &ids,
            Disposition::NeedsSpec,
            "approved-execution-mismatch",
        ));
    }
    if !same(&selection.spec, &h.authority.spec) || !same(&selection.tasks, &h.authority.tasks) {
        return Err(gate(
            &h,
            &ids,
            Disposition::NeedsSpec,
            "spec-task-binding-mismatch",
        ));
    }
    let records = tasks(&h.authority.tasks)?;
    let unique: BTreeSet<_> = ids.iter().collect();
    if ids.is_empty()
        || unique.len() != ids.len()
        || ids.iter().any(|id| records.get(id) != Some(&false))
    {
        return Err(gate(
            &h,
            &ids,
            Disposition::NeedsSpec,
            "selected-task-unavailable",
        ));
    }
    let dependencies: BTreeSet<_> = selection
        .selected_tasks
        .iter()
        .flat_map(|t| t.depends_on.iter())
        .collect();
    let ready: BTreeSet<_> = selection.dependencies_ready.iter().collect();
    if ready.len() != selection.dependencies_ready.len()
        || dependencies != ready
        || ready.iter().any(|id| records.get(*id) != Some(&true))
    {
        return Err(gate(
            &h,
            &ids,
            Disposition::NeedsSpec,
            "dependency-not-ready",
        ));
    }
    if h.budget.aggregate != AggregateBudget::AuditOnly {
        return Err(gate(
            &h,
            &ids,
            Disposition::Unsupported,
            "unsupported-budget",
        ));
    }
    if h.budget.wall_secs == 0
        || h.budget.wall_secs > 3600
        || h.budget.max_refinements > 20
        || !(4096..=8192).contains(&h.budget.response_max_tokens)
    {
        return Err(gate(
            &h,
            &ids,
            Disposition::Unsupported,
            "unsupported-budget",
        ));
    }
    match &h.budget.coordination_usage {
        CoordinationUsage::Unknown { reason } if reason.trim().is_empty() => {
            return Err(gate(
                &h,
                &ids,
                Disposition::NeedsEvidence,
                "coordination-usage-missing",
            ));
        }
        CoordinationUsage::Recorded { record } => {
            record.verify()?;
        }
        _ => {}
    }
    let workspace = safe_path(&h.workspace)?;
    if workspace.join(".craft-pi-executor-owner.json").exists()
        || workspace.join("app/.craft-owner.lock").exists()
    {
        return Err(gate(&h, &ids, Disposition::NeedsScope, "owner-conflict"));
    }
    let app = workspace.join("app");
    let output = safe_path(&h.owner_output)?;
    if h.stop_marker == h.owner_output
        || h.stop_marker == h.workspace
        || h.stop_marker == output.join("accepted-policy.json")
        || h.stop_marker == output.join("execution.json")
    {
        return Err(gate(
            &h,
            &ids,
            Disposition::NeedsScope,
            "control-path-overlap",
        ));
    }
    if output.exists()
        || !output.parent().is_some_and(Path::is_dir)
        || workspace.starts_with(&output)
        || output.starts_with(&workspace)
    {
        return Err(gate(&h, &ids, Disposition::NeedsScope, "output-layout"));
    }
    safe_path(&h.stop_marker)?;
    for resource in [
        &h.stop_marker,
        &h.driver.path,
        &h.instructions.path,
        &h.provider_manifest.path,
    ] {
        if safe_path(resource)?.starts_with(&app) {
            return Err(gate(
                &h,
                &ids,
                Disposition::NeedsScope,
                "resource-write-overlap",
            ));
        }
    }
    let (source, digest) = match &h.application {
        ApplicationSource::ExistingWorkspace { source_sha256 } => {
            let ws = Workspace::open(&h.workspace)?;
            if ws.manifest.target != h.original.target
                || ws.manifest.stack != h.stack
                || ws.manifest.app_in_root
            {
                return Err(gate(
                    &h,
                    &ids,
                    Disposition::NeedsScope,
                    "workspace-target-stack-mismatch",
                ));
            }
            (None, source_sha256.clone())
        }
        ApplicationSource::Empty | ApplicationSource::Copy { .. } => {
            if workspace.exists() || !workspace.parent().is_some_and(Path::is_dir) {
                return Err(gate(
                    &h,
                    &ids,
                    Disposition::NeedsScope,
                    "workspace-not-fresh",
                ));
            }
            if !h.read_references.is_empty() {
                return Err(gate(
                    &h,
                    &ids,
                    Disposition::Unsupported,
                    "new-workspace-reference-staging",
                ));
            }
            match &h.application {
                ApplicationSource::Copy {
                    root,
                    source_sha256,
                } => {
                    let root = safe_path(root)?;
                    if !root.is_dir()
                        || root.starts_with(&workspace)
                        || workspace.starts_with(&root)
                        || output.starts_with(&root)
                        || root.starts_with(&output)
                    {
                        return Err(gate(&h, &ids, Disposition::NeedsScope, "source-layout"));
                    }
                    (Some(root), source_sha256.clone())
                }
                _ => (
                    None,
                    "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855".into(),
                ),
            }
        }
    };
    if let Some(root) = &source {
        if let craft_anything_engine::workspace::TargetRef::Local { path } = &h.original.target {
            let original = safe_path(path)?;
            if root.starts_with(&original) || original.starts_with(root) {
                return Err(gate(
                    &h,
                    &ids,
                    Disposition::NeedsScope,
                    "original-seed-overlap",
                ));
            }
        }
    }
    let files = if let Some(root) = &source {
        let files = source_files(root)?;
        if source_digest(root)? != digest {
            return Err(gate(&h, &ids, Disposition::NeedsEvidence, "source-drift"));
        }
        files
    } else {
        Vec::new()
    };
    let (p, c) = construct(&h, &ids, &app, &output, &digest)?;
    // The source copy is independently hashed/enumerated above. Validate the absent formal
    // app layout with the policy's explicit empty initial state; materialization must then
    // satisfy the real approved seed digest before publication. No source alias is made.
    let mut probe = p.clone();
    if source.is_some() {
        probe.source_base_sha256 =
            "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855".into();
    }
    if matches!(h.application, ApplicationSource::ExistingWorkspace { .. }) {
        p.preflight(&Workspace::open(&h.workspace)?)?;
    }
    c.validate_policy_resources(probe, Some(&app))?;
    let definition = provider::validate(&h.provider_manifest, &p, &h.credential_env_keys)?;
    if definition["providers"][&p.model.expected.provider]["models"][0]["maxTokens"].as_u64()
        != Some(h.budget.response_max_tokens)
    {
        return Err(gate(
            &h,
            &ids,
            Disposition::Unsupported,
            "response-budget-mismatch",
        ));
    }
    // Authoritative inputs may not overlap any newly managed writes.
    for r in all_refs(&h.authority)
        .into_iter()
        .chain(p.references())
        .chain([
            &h.lead_decision,
            &h.selection,
            &h.check_plan,
            &h.instructions,
            &h.driver,
            &h.provider_manifest,
            &decision.lead_ref,
        ])
    {
        let path = r.verify()?;
        if path.starts_with(&output)
            || (!matches!(h.application, ApplicationSource::ExistingWorkspace { .. })
                && path.starts_with(&workspace))
        {
            return Err(gate(
                &h,
                &ids,
                Disposition::NeedsScope,
                "authority-write-overlap",
            ));
        }
    }
    if let policy::Original {
        target: craft_anything_engine::workspace::TargetRef::Local { path },
        ..
    } = &h.original
    {
        if real_parent(path)?.starts_with(&workspace) {
            return Err(gate(
                &h,
                &ids,
                Disposition::NeedsScope,
                "original-write-overlap",
            ));
        }
    }
    let ctx = context(&h, ids);
    Ok(Assembly {
        h,
        p,
        c,
        ctx,
        source,
        files,
    })
}

pub fn run(path: &Path, write: bool) -> Result<Value, ToolError> {
    safe_path(path)?;
    let bytes = read_capped(path)?;
    let h: Handoff = serde_json::from_slice(&bytes).map_err(|_| {
        refusal(
            "invalid-handoff",
            "Expected typed handoff v1; unknown fields refused.",
        )
    })?;
    let input_real = safe_path(path)?;
    if input_real.starts_with(safe_path(&h.owner_output)?)
        || (!matches!(h.application, ApplicationSource::ExistingWorkspace { .. })
            && input_real.starts_with(safe_path(&h.workspace)?))
    {
        return Err(sanitize(
            refusal(
                "authority-write-overlap",
                "Input handoff overlaps managed output.",
            ),
            context(&h, vec![]),
        ));
    }
    let fallback = context(
        &h,
        decode::<TaskSelection>(&h.selection)
            .map(|s| {
                let valid = s
                    .selected_tasks
                    .iter()
                    .all(|t| task_id(&t.id) && t.depends_on.iter().all(|id| task_id(id)))
                    && s.dependencies_ready.iter().all(|id| task_id(id));
                if valid {
                    s.selected_tasks.into_iter().map(|t| t.id).collect()
                } else {
                    vec![]
                }
            })
            .unwrap_or_default(),
    );
    let mut assembly = assemble(h.clone()).map_err(|error| sanitize(error, fallback.clone()))?;
    let input_ref = HashedRef {
        path: path.to_path_buf(),
        sha256: hash_file(path)?,
    };
    assembly.ctx.handoff = Some(input_ref.clone());
    if !write {
        return Ok(
            json!({"ok":true,"state":"validated","contract_version":1,"model_calls":0,"authority_semantics":"Lead decision is hash/structure bound; original lead owns semantic acceptance.","refs":assembly.ctx}),
        );
    }
    // Re-run complete read-only admission immediately before exclusive managed creation.
    let mut assembly = assemble(h).map_err(|error| sanitize(error, fallback.clone()))?;
    assembly.ctx.handoff = Some(input_ref);
    materialize(assembly, path, &bytes).map_err(|error| sanitize(error, fallback))
}
fn sanitize(error: ToolError, ctx: Context) -> ToolError {
    if error
        .details
        .as_ref()
        .is_some_and(|d| d.get("return_summary").is_some())
    {
        return error;
    }
    let code = error
        .details
        .as_ref()
        .and_then(|d| d["reason"].as_str())
        .unwrap_or("missing-input");
    let disposition = if code.starts_with("unsupported") || code == "model-policy" {
        Disposition::Unsupported
    } else if code == "path-denied" || code == "identity-mismatch" {
        Disposition::NeedsScope
    } else {
        Disposition::NeedsEvidence
    };
    let summary = Summary::new(
        ctx,
        disposition,
        vec![CheckReason {
            id: "handoff".into(),
            reason_code: code.into(),
        }],
    );
    refusal(
        code,
        "Handoff admission failed; source content is not returned.",
    )
    .with_details(json!({"reason":code,"return_summary":summary}))
}
fn materialize(mut a: Assembly, input: &Path, input_bytes: &[u8]) -> Result<Value, ToolError> {
    let output = &a.h.owner_output;
    let stage = output.with_file_name(format!(".craft-prepare-{}", new_id()));
    fs::create_dir(&stage).map_err(|_| {
        refusal(
            "owner-conflict",
            "Cannot create exclusive preparation stage.",
        )
    })?;
    let mut output_published = false;
    let new_workspace = !matches!(a.h.application, ApplicationSource::ExistingWorkspace { .. });
    let mut workspace_created = false;
    let result = (|| {
        if new_workspace {
            // Exclusive mkdir before official create_at prevents overwriting somebody else's root.
            fs::create_dir(&a.h.workspace)
                .map_err(|_| refusal("owner-conflict", "Workspace changed after admission."))?;
            workspace_created = true;
            let mut ws = Workspace::create_at(
                &a.h.workspace,
                "Accepted implementation",
                &a.h.message,
                a.p.original.target.clone(),
                None,
            )?;
            fs::create_dir(ws.app_dir()).map_err(|e| ToolError::io(ws.app_dir().display(), e))?;
            if let Some(source) = &a.source {
                for (rel, expected) in &a.files {
                    let from = source.join(rel);
                    safe_path(&from)?;
                    if hash_file(&from)? != *expected {
                        return Err(refusal(
                            "source-drift",
                            "Approved source changed during managed copy.",
                        ));
                    }
                    let to = ws.app_dir().join(rel);
                    if let Some(parent) = to.parent() {
                        fs::create_dir_all(parent)
                            .map_err(|e| ToolError::io(parent.display(), e))?;
                    }
                    fs::copy(&from, &to).map_err(|e| ToolError::io(to.display(), e))?;
                    if hash_file(&to)? != *expected {
                        return Err(refusal("source-drift", "Managed source copy differs."));
                    }
                }
                if source_digest(source)? != a.p.source_base_sha256 {
                    return Err(refusal(
                        "source-drift",
                        "Approved source changed during copy.",
                    ));
                }
            }
            ws.manifest.stack = a.p.stack.clone();
            ws.save()?;
        }
        let ws = Workspace::open(&a.h.workspace)?;
        a.p.preflight(&ws)?;
        craft_anything_ai::rebuild::validate_external_inputs(&a.p)?;
        // Revalidate original authority, task decision and approved source after managed writes.
        for reference in all_refs(&a.h.authority).into_iter().chain([
            &a.h.lead_decision,
            &a.h.selection,
            &a.h.check_plan,
            &a.h.driver,
            &a.h.instructions,
            &a.h.provider_manifest,
        ]) {
            reference.verify()?;
        }
        let local_plan = stage.join("check-plan.json");
        write_json(&local_plan, &a.p.checks)?;
        a.p.check_plan_ref = HashedRef {
            path: output.join("check-plan.json"),
            sha256: hash_file(&local_plan)?,
        };
        write_json(&stage.join("accepted-policy.json"), &a.p)?;
        a.c.policy_sha256 = hash_file(&stage.join("accepted-policy.json"))?;
        let context_path = stage.join("handoff-context.json");
        write_json(&context_path, &a.ctx)?;
        a.c.handoff_context = Some(HashedRef {
            path: output.join("handoff-context.json"),
            sha256: hash_file(&context_path)?,
        });
        let execution = output.join("execution.json");
        write_json(&stage.join("execution.json"), &a.c)?;
        let input_manifest = output.join("input-manifest.json");
        write_json(
            &stage.join("input-manifest.json"),
            &json!({"version":1,"handoff": {"path":input,"sha256":hash_file(input)?},"authority":a.ctx,"budget":a.h.budget,"policy":{"path":a.c.policy,"sha256":a.c.policy_sha256},"execution":{"path":execution,"sha256":hash_file(&stage.join("execution.json"))?},"qualification":"hash/structure validated; semantic lead acceptance and native REA claims unchanged","source_base_sha256":a.p.source_base_sha256,"copied_files":a.files.iter().map(|(p,h)|json!({"path":p,"sha256":h})).collect::<Vec<_>>()}),
        )?;
        if read_capped(input)? != input_bytes {
            return Err(refusal(
                "identity-mismatch",
                "Handoff changed during preparation.",
            ));
        }
        if output.exists() {
            return Err(refusal(
                "owner-conflict",
                "Final owner output changed during preparation.",
            ));
        }
        fs::rename(&stage, output).map_err(|_| {
            refusal(
                "owner-conflict",
                "Cannot publish exclusive owner artifacts.",
            )
        })?;
        output_published = true;
        a.c.validate_resources()?;
        Ok(
            json!({"ok":true,"state":"prepared","contract_version":1,"model_calls":0,"accepted":false,"execution":{"path":execution,"sha256":hash_file(&execution)?},"policy":{"path":a.c.policy,"sha256":a.c.policy_sha256},"input_manifest":{"path":input_manifest,"sha256":hash_file(&input_manifest)?},"refs":a.ctx}),
        )
    })();
    if result.is_err() {
        // Only roots exclusively created by this invocation are rollback targets. Original
        // source/authority/existing Workspace and any previous run lease are never removed.
        let mut rollback_failed = false;
        if workspace_created {
            rollback_failed |= fs::remove_dir_all(&a.h.workspace).is_err();
        }
        rollback_failed |= if output_published {
            fs::remove_dir_all(output).is_err()
        } else {
            fs::remove_dir_all(&stage).is_err()
        };
        if rollback_failed {
            return Err(refusal(
                "prepare-rollback-incomplete",
                "Managed preparation failed and own staging cleanup is unconfirmed; preserve roots for owner review.",
            ));
        }
    }
    result
}
