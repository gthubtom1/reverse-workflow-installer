//! Owned deterministic entry for the patched Craft loop. No research or second coding loop.
pub mod adapter;
pub mod credential_names;
pub mod execution;
pub mod handoff;
pub mod observation;
pub mod prepare;
pub mod provider;
pub mod public_result;
pub mod return_summary;
pub mod runtime;

use craft_anything_engine::execution_policy::{ExecutionPolicy, hash_file, read_capped, refusal};
use craft_anything_evidence::ToolError;
use serde::{Deserialize, Serialize};
use std::{
    fs,
    path::{Path, PathBuf},
};

pub const CONTRACT_VERSION: u32 = 1;
pub const GOOD_ENOUGH: f64 = 90.0;
pub const BACKEND_ID: &str = "craft-pi-rpc-v1";
pub const PERMISSION: &str = "pi-rpc-bounded-v1";

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct ExecutionConfig {
    pub contract_version: u32,
    pub policy: PathBuf,
    pub policy_sha256: String,
    pub workspace: PathBuf,
    pub create_workspace: bool,
    /// Must not exist before admission. An interrupted owner leaves this directory for review.
    pub run_root: PathBuf,
    pub driver: PathBuf,
    pub driver_sha256: String,
    /// Explicit environment names only; values are resolved by the driver.
    #[serde(default)]
    pub credential_env_keys: Vec<String>,
    pub provider_manifest: Option<craft_anything_engine::execution_policy::HashedRef>,
    pub instructions: PathBuf,
    pub instructions_sha256: String,
    pub max_refinements: u32,
    pub stop_marker: PathBuf,
    pub message: String,
    #[serde(default)]
    pub handoff_context: Option<craft_anything_engine::execution_policy::HashedRef>,
}
impl ExecutionConfig {
    pub fn load(path: &Path) -> Result<Self, ToolError> {
        let c: Self = serde_json::from_slice(&read_capped(path)?).map_err(|_| {
            refusal(
                "invalid-execution-json",
                "Invalid typed execution JSON; unknown fields are refused.",
            )
        })?;
        if c.contract_version != CONTRACT_VERSION
            || c.message.trim().is_empty()
            || c.max_refinements > 20
        {
            return Err(refusal(
                "invalid-config",
                "Unsupported version, empty message or excessive refinement budget.",
            ));
        }
        for p in [
            &c.policy,
            &c.workspace,
            &c.run_root,
            &c.driver,
            &c.instructions,
            &c.stop_marker,
        ] {
            if !p.is_absolute() {
                return Err(refusal(
                    "invalid-config",
                    "All execution paths must be absolute.",
                ));
            }
        }
        if hash_file(&c.driver)? != c.driver_sha256
            || hash_file(&c.policy)? != c.policy_sha256
            || hash_file(&c.instructions)? != c.instructions_sha256
        {
            return Err(refusal(
                "identity-mismatch",
                "Policy/instructions hash differs from accepted execution config.",
            ));
        }
        c.validate_resources()?;
        Ok(c)
    }
    pub fn validate_resources(&self) -> Result<(), ToolError> {
        self.validate_policy_resources(self.policy()?, None)
    }
    /// Prepare validates the identical contract against the approved source before copying.
    /// Destination layout/ownership is independently checked by the assembler.
    pub(crate) fn validate_policy_resources(
        &self,
        p: ExecutionPolicy,
        approved_source: Option<&Path>,
    ) -> Result<(), ToolError> {
        if self.contract_version != CONTRACT_VERSION
            || self.message.trim().is_empty()
            || self.max_refinements > 20
        {
            return Err(refusal(
                "invalid-config",
                "Invalid execution version/message/refinement budget.",
            ));
        }
        for p in [
            &self.policy,
            &self.workspace,
            &self.run_root,
            &self.driver,
            &self.instructions,
            &self.stop_marker,
        ] {
            if !p.is_absolute() {
                return Err(refusal(
                    "invalid-config",
                    "All execution paths must be absolute.",
                ));
            }
        }
        if self.run_root.exists() {
            return Err(refusal(
                "owner-conflict",
                "Owned run root already exists; review its prior owner before reuse.",
            ));
        }
        if approved_source.is_none() && !self.run_root.parent().is_some_and(Path::is_dir) {
            return Err(refusal(
                "missing-input",
                "Run root parent must already exist.",
            ));
        }
        if hash_file(&self.driver)? != self.driver_sha256
            || hash_file(&self.instructions)? != self.instructions_sha256
        {
            return Err(refusal(
                "identity-mismatch",
                "Driver/instructions identity changed.",
            ));
        }
        if p.model.backend_id != BACKEND_ID || p.model.permission_contract != PERMISSION {
            return Err(refusal("unsupported", "Policy selects another transport."));
        }
        p.validate_model()?;
        let model = &p.model.expected;
        if model.provider.is_empty()
            || !model
                .provider
                .bytes()
                .all(|b| b.is_ascii_alphanumeric() || b == b'-' || b == b'_')
            || model.model.is_empty()
            || model.model.contains([':', '*', '\n', '\r', ','])
            || model.model.chars().any(char::is_whitespace)
            || !["off", "minimal", "low", "medium", "high", "xhigh", "max"]
                .contains(&model.effort.as_str())
        {
            return Err(refusal(
                "model-policy",
                "Model identity does not fit the fixed Pi RPC contract.",
            ));
        }
        craft_anything_ai::rebuild::validate_external_inputs(&p)?;
        if p.refine_feedback()?
            .is_some_and(|feedback| feedback.good_enough != GOOD_ENOUGH)
        {
            return Err(refusal(
                "check-plan",
                "Refine feedback threshold differs from the fixed execution threshold.",
            ));
        }
        let expected_app = craft_anything_engine::execution_policy::real_parent(
            approved_source.unwrap_or(&self.workspace.join("app")),
        )?;
        if expected_app != craft_anything_engine::execution_policy::real_parent(&p.app_root)? {
            return Err(refusal(
                "identity-mismatch",
                "Execution workspace/app differs from the accepted planned root.",
            ));
        }
        if approved_source.is_some() {
            // Planned copy/empty path: no Workspace exists yet. Same pure policy admission
            // above checked source/baseline/commands; prepare checks destination binding.
        } else if self.create_workspace {
            if self.workspace.exists()
                && std::fs::read_dir(&self.workspace)
                    .map_err(|e| ToolError::io(self.workspace.display(), e))?
                    .next()
                    .is_some()
            {
                return Err(refusal(
                    "workspace-conflict",
                    "New workspace must be absent or empty before admission.",
                ));
            }
        } else {
            let ws = craft_anything_engine::workspace::Workspace::open(&self.workspace)?;
            p.preflight(&ws)?;
            if ws.manifest.agent_session.is_some() {
                return Err(refusal(
                    "unsupported",
                    "Cross-run native history is unsupported.",
                ));
            }
        }
        if p.owner_id.len() < 16
            || p.owner_id.len() > 256
            || !p
                .owner_id
                .bytes()
                .all(|b| b.is_ascii_alphanumeric() || b == b'-' || b == b'_')
            || p.max_wall_secs > 3600
        {
            return Err(refusal(
                "invalid-owner",
                "Unsupported owner identity or wall budget.",
            ));
        }
        if p.kind_id != "app"
            || !p.checks.iter().any(|c| c.required && c.id == "build")
            || !p
                .checks
                .iter()
                .any(|c| c.required && c.id == "external-scenario")
        {
            return Err(refusal(
                "unsupported",
                "A required explicit build and external business scenario are mandatory.",
            ));
        }
        validate_original(&p)?;
        let app = craft_anything_engine::execution_policy::real_parent(&p.app_root)?;
        for resource in [
            &self.driver,
            &self.instructions,
            &self.policy,
            &self.stop_marker,
            &self.run_root,
        ] {
            let resource = craft_anything_engine::execution_policy::real_parent(resource)?;
            if resource.starts_with(&app) {
                return Err(refusal(
                    "path-denied",
                    "Control/runtime resources must remain outside the Builder app root.",
                ));
            }
        }
        if let Some(reference) = &self.provider_manifest {
            if reference.verify()?.starts_with(&app) {
                return Err(refusal(
                    "path-denied",
                    "Private provider manifest must be outside the app root.",
                ));
            }
            provider::validate(reference, &p, &self.credential_env_keys)?;
        }
        credential_names::validate(&self.credential_env_keys)?;
        if self.message.trim().is_empty() {
            return Err(refusal(
                "invalid-config",
                "A bounded implementation message is required.",
            ));
        }
        let instructions = read_instructions(self)?;
        if instructions.trim().is_empty() || instructions.len() > 60000 {
            return Err(refusal(
                "invalid-instructions",
                "Reviewed literal instructions must be nonempty and bounded.",
            ));
        }
        Ok(())
    }
    pub fn policy(&self) -> Result<ExecutionPolicy, ToolError> {
        if let Some(context) = &self.handoff_context {
            let value: return_summary::Context = serde_json::from_slice(&context.read_verified()?)
                .map_err(|_| refusal("invalid-context", "Invalid typed handoff context."))?;
            value.validate()?;
        }
        if hash_file(&self.policy)? != self.policy_sha256 {
            return Err(refusal("identity-mismatch", "Policy changed."));
        }
        let p: ExecutionPolicy = serde_json::from_slice(&read_capped(&self.policy)?)
            .map_err(|_| refusal("invalid-policy", "Invalid typed policy JSON."))?;
        if let Some(reference) = &self.handoff_context {
            let context: return_summary::Context =
                serde_json::from_slice(&reference.read_verified()?)
                    .map_err(|_| refusal("invalid-context", "Invalid typed context."))?;
            if context.selected_tasks != p.identity.task_ids
                || context.authority.case != p.identity.case_ref
                || context.authority.scope != p.identity.scope_ref
                || context.authority.workitem != p.identity.workitem_ref
                || context.authority.feature != p.identity.feature_ref
                || context.authority.acceptance != p.identity.acceptance_ref
                || context.baseline != p.original.bundle
            {
                return Err(refusal(
                    "identity-mismatch",
                    "Execution policy differs from original handoff context.",
                ));
            }
        }
        crate::prepare::validate_execution_binding(self, &p)?;
        if p.model.backend_id != BACKEND_ID || p.model.permission_contract != PERMISSION {
            return Err(refusal(
                "unsupported",
                "The selected policy is for a different transport.",
            ));
        }
        Ok(p)
    }
}
pub fn write_json(path: &Path, value: &impl Serialize) -> Result<(), ToolError> {
    let bytes = serde_json::to_vec_pretty(value).map_err(|e| ToolError::internal(e.to_string()))?;
    craft_anything_platform::fs::write_atomic_private(path, &bytes)
}
pub fn validate_original(p: &ExecutionPolicy) -> Result<(), ToolError> {
    use craft_anything_engine::{
        execution_policy::{real, source_digest},
        workspace::TargetRef,
    };
    match &p.original.target {
        TargetRef::Local { path } => {
            let path = real(path)?;
            let actual = if path.is_dir() {
                source_digest(&path)?
            } else {
                hash_file(&path)?
            };
            if actual != p.original.target_identity {
                return Err(refusal("identity-mismatch", "Original target changed."));
            }
        }
        TargetRef::None => {
            return Err(refusal(
                "missing-input",
                "A genuine original target identity is required.",
            ));
        }
        _ => {}
    }
    Ok(())
}
pub fn new_id() -> String {
    uuid::Uuid::new_v4().simple().to_string()
}
pub fn read_instructions(c: &ExecutionConfig) -> Result<String, ToolError> {
    if hash_file(&c.instructions)? != c.instructions_sha256 {
        return Err(refusal("identity-mismatch", "Instructions drift."));
    }
    fs::read_to_string(&c.instructions).map_err(|e| ToolError::io(c.instructions.display(), e))
}
