//! Typed return routing; check dispositions are consumed as types, never parsed from prose.
use crate::handoff::AuthorityRefs;
use craft_anything_engine::execution_policy::HashedRef;
use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "kebab-case")]
pub enum Disposition {
    NeedsEvidence,
    Unsupported,
    ImplementationFailed,
    Cancelled,
    NeedsScope,
    NeedsSpec,
}
#[derive(Debug, Clone, Copy, Serialize, Deserialize)]
#[serde(rename_all = "kebab-case")]
pub enum ReturnTo {
    OriginalPrimary,
    SpecRunner,
    Lead,
}
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct CheckReason {
    pub id: String,
    pub reason_code: String,
}
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Context {
    pub version: u32,
    #[serde(default)]
    pub handoff: Option<HashedRef>,
    pub authority: AuthorityRefs,
    pub selected_tasks: Vec<String>,
    pub check_plan: HashedRef,
    pub baseline: HashedRef,
    pub lead_decision: HashedRef,
    pub selection: HashedRef,
}
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Summary {
    pub disposition: Disposition,
    pub affected_tasks: Vec<String>,
    pub checks: Vec<CheckReason>,
    pub return_to: ReturnTo,
    pub refs: Context,
}
impl Context {
    pub fn validate(&self) -> Result<(), craft_anything_evidence::ToolError> {
        for r in [
            &self.authority.case,
            &self.authority.scope,
            &self.authority.workitem,
            &self.authority.feature,
            &self.authority.spec,
            &self.authority.plan,
            &self.authority.tasks,
            &self.authority.acceptance,
            &self.check_plan,
            &self.baseline,
            &self.lead_decision,
            &self.selection,
        ] {
            r.verify()?;
        }
        let decision: crate::handoff::LeadDecision =
            serde_json::from_slice(&self.lead_decision.read_verified()?).map_err(|_| {
                craft_anything_engine::execution_policy::refusal(
                    "invalid-context",
                    "Invalid original lead decision.",
                )
            })?;
        decision.lead_ref.verify()?;
        if serde_json::to_value(&decision.authority).ok()
            != serde_json::to_value(&self.authority).ok()
            || decision.selected_task_ids != self.selected_tasks
            || decision.selection != self.selection
        {
            return Err(craft_anything_engine::execution_policy::refusal(
                "identity-mismatch",
                "Return context differs from original decision.",
            ));
        }
        if self
            .selected_tasks
            .iter()
            .any(|id| !crate::prepare::task_id(id))
        {
            return Err(craft_anything_engine::execution_policy::refusal(
                "invalid-context",
                "Invalid public task IDs.",
            ));
        }
        if let Some(handoff) = &self.handoff {
            handoff.verify()?;
        }
        if self.version != 1 {
            return Err(craft_anything_engine::execution_policy::refusal(
                "unsupported",
                "Unknown handoff context.",
            ));
        }
        Ok(())
    }
}
impl Summary {
    pub fn new(context: Context, disposition: Disposition, checks: Vec<CheckReason>) -> Self {
        let return_to = match disposition {
            Disposition::NeedsEvidence => ReturnTo::OriginalPrimary,
            Disposition::ImplementationFailed | Disposition::NeedsSpec => ReturnTo::SpecRunner,
            _ => ReturnTo::Lead,
        };
        Self {
            affected_tasks: context.selected_tasks.clone(),
            refs: context,
            disposition,
            checks,
            return_to,
        }
    }
}

pub fn from_execution(
    c: &crate::ExecutionConfig,
    p: &craft_anything_engine::execution_policy::ExecutionPolicy,
    report: Option<&craft_anything_ai::rebuild::CheckPlanReport>,
    cancelled: bool,
    finished_ok: bool,
) -> Result<Option<Summary>, craft_anything_evidence::ToolError> {
    use craft_anything_ai::rebuild::{CheckReturnKind, CheckReturnTo};
    let Some(reference) = &c.handoff_context else {
        return Ok(None);
    };
    let context: Context = serde_json::from_slice(&reference.read_verified()?).map_err(|_| {
        craft_anything_engine::execution_policy::refusal(
            "invalid-context",
            "Invalid handoff return context.",
        )
    })?;
    // Revalidate authority identity; missing/changed original refs are a typed evidence return,
    // not permission to invent facts or continue another implementation round.
    if context.validate().is_err() {
        return Ok(Some(Summary::new(
            context,
            Disposition::NeedsEvidence,
            vec![CheckReason {
                id: "authority".into(),
                reason_code: "input-changed".into(),
            }],
        )));
    }
    if let Some(typed) = report.and_then(|r| {
        r.return_summary(
            c.workspace
                .join("checks")
                .join(format!("round-{}", r.round))
                .join("accepted-check-plan.json"),
        )
    }) {
        let disposition = match typed.kind {
            CheckReturnKind::NeedsEvidence => Disposition::NeedsEvidence,
            CheckReturnKind::Unsupported => Disposition::Unsupported,
            CheckReturnKind::Cancelled => Disposition::Cancelled,
            _ => Disposition::ImplementationFailed,
        };
        let checks = typed
            .records
            .iter()
            .map(|r| CheckReason {
                id: r.id.clone(),
                reason_code: serde_json::to_value(r.reason_code)
                    .ok()
                    .and_then(|v| v.as_str().map(str::to_owned))
                    .unwrap_or_else(|| "check-execution-error".into()),
            })
            .collect();
        let mut summary = Summary::new(context, disposition, checks);
        summary.return_to = match typed.return_to {
            CheckReturnTo::OriginalPrimary => ReturnTo::OriginalPrimary,
            CheckReturnTo::SpecRunner | CheckReturnTo::ImplementationWorker => ReturnTo::SpecRunner,
            _ => ReturnTo::Lead,
        };
        return Ok(Some(summary));
    }
    if report.is_none() && !cancelled {
        return Ok(Some(Summary::new(
            context,
            Disposition::Unsupported,
            vec![CheckReason {
                id: "check-plan".into(),
                reason_code: "unverified-result".into(),
            }],
        )));
    }
    if cancelled {
        return Ok(Some(Summary::new(context, Disposition::Cancelled, vec![])));
    }
    if !finished_ok
        || report.is_some_and(|r| {
            r.checks.iter().any(|c| {
                c.required
                    && c.disposition != craft_anything_ai::rebuild::CheckDisposition::Executed
            })
        })
    {
        return Ok(Some(Summary::new(
            context,
            Disposition::ImplementationFailed,
            vec![CheckReason {
                id: "implementation".into(),
                reason_code: "implementation-failed".into(),
            }],
        )));
    }
    if report.is_none() {
        return Ok(Some(Summary::new(
            context,
            Disposition::Unsupported,
            vec![CheckReason {
                id: "check-plan".into(),
                reason_code: "unverified-result".into(),
            }],
        )));
    }
    let _ = p;
    Ok(None)
}
