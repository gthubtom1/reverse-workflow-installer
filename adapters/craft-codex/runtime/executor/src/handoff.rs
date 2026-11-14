//! Production handoff schema. Supplemental selection/decision records reference the original
//! Spec/tasks; they do not become a second task database or prove semantic acceptance.
use craft_anything_engine::execution_policy::{
    BuildInvocation, ExternalBaseline, HashedRef, ModelPermission, Original, PlannedCheck,
};
use serde::{Deserialize, Serialize};
use std::path::PathBuf;

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct AuthorityRefs {
    pub case: HashedRef,
    pub scope: HashedRef,
    pub workitem: HashedRef,
    pub feature: HashedRef,
    pub spec: HashedRef,
    pub plan: HashedRef,
    pub tasks: HashedRef,
    pub acceptance: HashedRef,
}
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct TaskSelection {
    pub version: u32,
    pub spec: HashedRef,
    pub tasks: HashedRef,
    pub selected_tasks: Vec<SelectedTask>,
    pub dependencies_ready: Vec<String>,
}
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct SelectedTask {
    pub id: String,
    pub depends_on: Vec<String>,
}
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct LeadDecision {
    pub version: u32,
    pub decision: Decision,
    pub authority: AuthorityRefs,
    pub selection: HashedRef,
    pub selected_task_ids: Vec<String>,
    pub lead_ref: HashedRef,
    pub approved: ApprovedExecution,
}
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct ApprovedExecution {
    pub original: Original,
    pub baseline: ExternalBaseline,
    pub driver: HashedRef,
    pub instructions: HashedRef,
    pub provider_manifest: HashedRef,
    pub credential_env_keys: Vec<String>,
    pub owner_output: PathBuf,
    pub owner_id: String,
    pub stop_marker: PathBuf,
    pub message: String,
    pub writable_relative: Vec<PathBuf>,
    pub protected_relative: Vec<PathBuf>,
    pub read_references: Vec<HashedRef>,
    pub workspace: PathBuf,
    pub application: ApplicationSource,
    pub target: craft_anything_engine::workspace::TargetRef,
    pub target_identity: String,
    pub stack: String,
    pub check_plan: HashedRef,
    pub model: ModelPermission,
    pub commands: Vec<Command>,
    pub build: BuildInvocation,
    pub budget: Budget,
}
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "kebab-case")]
pub enum Decision {
    Accepted,
    NeedsScope,
    NeedsSpec,
}
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(tag = "mode", rename_all = "kebab-case", deny_unknown_fields)]
pub enum ApplicationSource {
    ExistingWorkspace {
        source_sha256: String,
    },
    Empty,
    Copy {
        root: PathBuf,
        source_sha256: String,
    },
}
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Command {
    pub command: String,
    pub timeout_secs: u64,
}
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "kebab-case")]
pub enum AggregateBudget {
    AuditOnly,
    Strict,
}
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Budget {
    pub wall_secs: u64,
    pub max_refinements: u32,
    pub response_max_tokens: u64,
    #[serde(default)]
    pub response_hard_cap: bool,
    pub aggregate: AggregateBudget,
    pub coordination_usage: CoordinationUsage,
}
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(tag = "status", rename_all = "kebab-case", deny_unknown_fields)]
pub enum CoordinationUsage {
    Unknown { reason: String },
    Recorded { record: HashedRef },
}
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Handoff {
    pub version: u32,
    pub authority: AuthorityRefs,
    pub lead_decision: HashedRef,
    pub selection: HashedRef,
    pub original: Original,
    pub baseline: ExternalBaseline,
    pub check_plan: HashedRef,
    pub workspace: PathBuf,
    pub application: ApplicationSource,
    pub owner_output: PathBuf,
    pub writable_relative: Vec<PathBuf>,
    pub protected_relative: Vec<PathBuf>,
    pub read_references: Vec<HashedRef>,
    pub stack: String,
    pub commands: Vec<Command>,
    pub build: BuildInvocation,
    pub model: ModelPermission,
    pub driver: HashedRef,
    pub instructions: HashedRef,
    pub provider_manifest: HashedRef,
    pub credential_env_keys: Vec<String>,
    pub owner_id: String,
    pub budget: Budget,
    pub stop_marker: PathBuf,
    pub message: String,
}
// Intentionally no accepted=true, inferred->observed conversion, or arbitrary failure text router.
pub type CheckPlan = Vec<PlannedCheck>;
