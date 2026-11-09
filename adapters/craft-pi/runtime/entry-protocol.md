# Native execution entry protocol

Minimum installer0.7.0; Craft contract/min_reader1; adapter protocol0.2.0. Native build includes validate/prepare/run as declared below. Production handoff contract is `source/executor/docs/prepare-contract.md`; Rust schema is `source/executor/src/handoff.rs`, typed return is `source/executor/src/return_summary.rs`, and maintained owned console input examples are `source/executor/examples/console_handoff.rs` plus `source/executor/examples/console-inputs/`. Examples are designed fixtures, not external target Evidence. Candidate is never accepted. Official Pi/Node is acquired separately and excluded; no personal resources or provider calls. Validate is admission only; prepare writes new owner artifacts/Workspace; run invokes the separately qualified runtime.

```json
{
  "name": "craft-pi-executor-entry",
  "contract_version": 1,
  "version": "0.1.0",
  "transport": "local-native-process",
  "commands": {
    "inspect": ["--inspect"],
    "version": ["--version"],
    "execute": ["--run", "ABSOLUTE_ACCEPTED_CONFIG_JSON"],
    "validate": ["--validate", "ABSOLUTE_HANDOFF_JSON"],
    "prepare": ["--prepare", "ABSOLUTE_HANDOFF_JSON"]
  },
  "stdout": "one machine JSON result; candidate is never accepted",
  "stderr": "machine JSON admission error",
  "exit_codes": {"0": "inspect/version/validated/prepared or candidate", "1": "executed failed/stopped/blocked-cleanup", "2": "admission/config/runtime failure"},
  "required_environment": ["CRAFT_PI_NODE", "CRAFT_PI_ENTRY"],
  "provider": "ExecutionConfig.provider_manifest is one reviewed target-model JSON reference plus SHA256. apiKey must be ${ENV_NAME}; values are never execution-config fields. credential_env_keys declares names only.",
  "policy": "Hashed AcceptedResearch policy version 1; patched Craft RebuildRun, injected PolicyRuntime and public pi AgentAdapter",
  "handoff": "Typed deny-unknown v1; original authority/lead-decision/task-selection HashedRefs; read-only admission before new owner artifacts or official Workspace; zero model calls during prepare/validate.",
  "return_summary": "Typed disposition + affected_tasks + check reason codes + original source refs + original-primary/spec-runner/lead; no diagnostic/source body. Check report v2 required. Cleanup unknown remains blocked-cleanup and preserves return cause.",
  "resume": "within-run exact verified session only; cross-run reuse unsupported",
  "stop": "accepted execution config stop_marker; owner writes driver cancellation identity before hard stop",
  "runtime": {"entry": "bin/craft-pi-executor.exe", "entry_kind": "native", "driver": "bin/pi-rpc-driver.exe", "driver_kind": "native", "entry_protocol": "entry-protocol.json"},
  "qualification": "development integration; independent acceptance and packaged runtime verification required"
}

```
