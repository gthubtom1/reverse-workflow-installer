# Production prepare contract v1

Commands: `craft-pi-executor --validate /absolute/handoff.json` (read-only) and `--prepare /absolute/handoff.json` (new owner artifacts and, when requested, formal Workspace only; zero model calls). The typed Rust schema is `src/handoff.rs`; every object rejects unknown fields. Existing `Original`, `ExternalBaseline`, `PlannedCheck`, `BuildInvocation` and `ModelPermission` are reused from the accepted policy crate. This is a deterministic assembler, not evidence research or a second task owner.

Actual callable API: `prepare::run(path, false|true)`; execution JSON adds optional hashed `handoff_context`, revalidated before turns. `return_summary::Summary` is the public return contract, and policy check report v2 is consumed through `read_check_plan_report`. CLI `--inspect` advertises the real prepare/validate commands.

The handoff points to original case/scope/workitem/feature/spec/plan/tasks/acceptance files, a hashed lead decision and hashed supplemental task selection. Selection v1 points to the same spec/tasks and lists selected IDs + dependencies; only standard Spec `- [ ] T001 ...` / `- [X] T002 ...` records are supported. Dependencies must be present and completed in the actual tasks file. The lead decision binds the exact authority/selection hashes and selected IDs, and references the lead's existing decision authority document. Hash/structure validation proves identity, not that a decision is truthful or the evidence sufficient. Original lead and Spec runner retain acceptance/task updates.

The example helper `examples/console_handoff.rs` and original documents under `examples/console-inputs/` generate a complete runnable validation/preparation input set with actual hashes, lead decision, task selection, approved source, raw designed observations and exact scenario. `cargo run --example console_handoff -- ABS_NEW_INPUTS ABS_DRIVER` is a test-data constructor, not automatic acceptance of arbitrary user evidence.\n\nApplication input is `existing-workspace`, `empty`, or `copy` (approved root + source digest); copy uses an absent destination Workspace, rejects links/reparse escapes and preserves original source bytes. Commands are frozen with destination app cwd by the assembler. Control paths are generated under a fresh owner_output: accepted-policy.json, check-plan.json, execution.json, input-manifest.json, handoff-context.json and run/. No personal agent/resources/session/Evidence are copied. Original external artifact namespace/qualification remains unchanged.

Copy excludes generated `target`, `node_modules` and `.git` directories from managed source, consistently with source_digest. Active/unresolved source/Workspace writer marks cause owner-conflict. Preparation uses exclusive new Workspace creation and atomic sibling staging/publish of owner artifacts; errors remove only roots created by this invocation. Cleanup failure is reported as prepare-rollback-incomplete, never silently claimed zero artifacts.\n\nBudget explicitly freezes hard wall/refinement and configured per-response maxTokens, with aggregate `audit-only` and coordination usage recorded or unknown-with-reason. `strict` aggregate returns unsupported-budget before any writes; this executor does not enforce total tokens/cost.

Input illustration (all ABS and SHA values must be replaced with real current source identities; use the complete generated console fixture described in README for an executable example):

```json
{
  "version":1,
  "authority":{"case":{"path":"/ABS/case.md","sha256":"SHA"},"scope":{"path":"/ABS/scope.md","sha256":"SHA"},"workitem":{"path":"/ABS/workitem.md","sha256":"SHA"},"feature":{"path":"/ABS/feature.md","sha256":"SHA"},"spec":{"path":"/ABS/spec.md","sha256":"SHA"},"plan":{"path":"/ABS/plan.md","sha256":"SHA"},"tasks":{"path":"/ABS/tasks.md","sha256":"SHA"},"acceptance":{"path":"/ABS/acceptance.json","sha256":"SHA"}},
  "lead_decision":{"path":"/ABS/lead-decision.json","sha256":"SHA"},
  "selection":{"path":"/ABS/selection.json","sha256":"SHA"},
  "workspace":"/ABS/approved-workspace","owner_output":"/ABS/fresh-owner-batch",
  "application":{"mode":"copy","root":"/ABS/approved-console-project","source_sha256":"SOURCE_DIGEST"},
  "writable_relative":["."],"protected_relative":["Cargo.toml"],"read_references":[],
  "stack":"Rust (console)","commands":[{"command":"cargo build --offline","timeout_secs":30}],
  "build":{"command_index":0,"artifacts":["target/debug/console.exe"]},
  "model":{"allowed":true,"expected":{"provider":"fixture","model":"offline","effort":"high"},"backend_id":"craft-pi-rpc-v1","permission_contract":"pi-rpc-bounded-v1"},
  "driver":{"path":"/ABS/pi-rpc-driver.exe","sha256":"SHA"},"instructions":{"path":"/ABS/instructions.md","sha256":"SHA"},
  "provider_manifest":{"path":"/ABS/minimal-reviewed-models.json","sha256":"SHA"},"credential_env_keys":["TASK_PROVIDER_KEY"],
  "owner_id":"OWNER_GENERATED_16_PLUS_CHAR_ID","budget":{"wall_secs":120,"max_refinements":2,"response_max_tokens":4096,"aggregate":"audit-only","coordination_usage":{"status":"unknown","reason":"External coordinator usage not supplied"}},
  "stop_marker":"/ABS/owner-stop","message":"Implement T002 only; missing evidence returns to original route.",
  "original":"EXISTING_TYPED_ORIGINAL_OBJECT","baseline":"EXISTING_TYPED_EXTERNAL_BASELINE_OBJECT",
  "check_plan":{"path":"/ABS/reviewed-check-plan.json","sha256":"SHA"}
}
```

Decision record is `{version:1,decision:accepted|needs-scope|needs-spec,authority:<same refs>,selection:<exact ref>,selected_task_ids:[T002],lead_ref:<original lead document ref>,approved:{workspace,application,target,target_identity,stack,check_plan,model,commands,build,budget,writable_relative,protected_relative,read_references,original,baseline,driver,instructions,provider_manifest,credential_env_keys,owner_output,owner_id,stop_marker,message}}`. The approved fields must exactly match the handoff; target/source/layout mismatch returns needs-scope, other approved execution/Spec mismatch returns needs-spec. Decision needs-spec/needs-scope routes before any model. Selection is `{version:1,spec:<same ref>,tasks:<same ref>,selected_tasks:[{id:T002,depends_on:[T001]}],dependencies_ready:[T001]}`. None of these records updates tasks.md.

Prepared context retains the original handoff HashedRef. Before execution the same construction function rebuilds the entire allowed policy/config from that handoff and rechecks the original lead decision approved fields; caller-refreshed generated policy/config/context hashes cannot impersonate an amended decision. The context hash in execution.json is not itself new authority. Original and generated check-plan files may have different JSON formatting, but typed contents, original hash and exact managed output path are all bound. Legacy raw-policy execution without context is explicitly unqualified as a prepare handoff.

Typed return summaries carry disposition, affected task IDs, check IDs/reason codes, original refs and return_to original-primary/spec-runner/lead. Required external check NeedsEvidence/Unsupported dispositions come from the policy worker's public records, never inferred from note text. Unknown cleanup always remains blocked-cleanup even when the underlying cause is needs-evidence.
