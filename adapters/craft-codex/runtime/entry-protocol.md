# Craft Codex native entry protocol

This is the local process interface for the Codex execution owner. It connects the original Reverse R46/Spec runner to the existing Craft AcceptedResearch, prepare, RebuildRun, bounded Engine and independent acceptance chain. It is not a second research or task-management entry.

## Public owner commands

Invoke the managed `bin/craft-codex-executor.exe` through the installed `craft-codex/entry.py` receipt gate. Supply absolute paths; do not search for a latest run or select an ambient executable.

| Operation | Arguments | Effect |
|---|---|---|
| Metadata | `--inspect` or `--version` | Machine metadata only; no Builder/model call |
| Validate | `--validate HANDOFF.json` | Read and verify original authority, lead decision, task selection, source, baseline, checks and runtime refs; no model call or prepared workspace |
| Prepare | `--prepare HANDOFF.json` | Publish bound policy, return context and execution config into new approved owned roots; no model call |
| Run | `--run EXECUTION.json` | Revalidate the prepared binding, acquire the exclusive owner lease and execute one Builder with bounded checks/refinement |

The owner writes one machine JSON result on stdout. Admission/configuration errors use machine JSON diagnostics and a nonzero exit. Exit 0 means metadata, validation, preparation or an unaccepted candidate; exit 1 means executed failure/stopped/blocked cleanup; exit 2 means admission/configuration/runtime failure. Consumers must inspect the typed result and cleanup, rather than interpreting an exit code as semantic acceptance. `accepted` remains false.

The versioned JSON schemas are represented by deny-unknown Rust types in `executor/src/{handoff,prepare,lib,return_summary}.rs` and the machine command summary in `executor/entry-protocol.json`. A handoff binds original authority refs, accepted lead decision, selected Spec task/dependency IDs, target identity, source snapshot, external observations/baseline/check plan, exact engineering commands and roots, instructions, runtime profile, driver, owner ID and budget. Rewriting a local hash does not grant a new lead decision.

## Managed environment

The installer entry clears stale Pi/Codex server/ToolPolicy fields and derives these values from its installed receipt:

- `CRAFT_CODEX_CLI`, `CRAFT_CODEX_CLI_SHA256`, `CRAFT_CODEX_VERSION`;
- `CRAFT_CODEX_HOME` and `CODEX_HOME`, selecting the normal native account/config root;
- `CRAFT_CODEX_RUNTIME_PROFILE` and `CRAFT_CODEX_RUNTIME_PROFILE_SHA256`, selecting the installed reviewed raw profile;
- `CRAFT_BUNDLE_ROOT` and `CRAFT_BUILDER_INSTRUCTIONS`.

The native Codex core reads its selected account normally. The bridge does not export/copy authentication files or supply credential environment-name lists. Never persist the full inherited process environment or `config/read` response: either can contain secrets. Auditable identity records contain approved refs, paths, presence, digests and usage facts.

`codex-stock-bounded-v1` fixes the external Codex version/binary digest, `app-server --stdio`, official startup scalar/feature overrides, empty native environments, ephemeral thread, no approvals or fallback, and the dynamic tool contract. Codex is supplied externally and is not redistributed in this two-binary bundle. An unqualified executable or changed reviewed profile is refused.

## Driver and MCP separation

The owner starts `bin/codex-app-server-driver.exe --config DRIVER.json` with its bound task on stdin. The driver owns two distinct children: the selected stock Codex app-server, and the owner executable's `mcp --policy ... --sha256 ... --workspace ... --config-root ...` service. The latter exposes the original bounded Engine. The driver executable does not implement that MCP subcommand.

Native startup follows `initialize`, response, `initialized`, then `config/read(cwd, includeLayers=true)`. Effective MCP names and actual configuration identity are checked in memory. Every effective MCP ID is disabled through flat dotted `thread/start.config` overrides before its warmup. Query MCP status only with the returned thread ID: the global status API can eagerly start enabled servers. An empty `mcp_servers={}` table does not clear lower configuration layers.

Only the six dynamic operations are registered under namespace `craft_host`: `build_files_list`, `build_file_read`, `build_file_write`, `build_file_edit`, `build_command_run`, `build_checklist`. Schemas come from the real bounded MCP `tools/list`. `item/tool/call` is a reverse request, answered using its exact request ID and `success/contentItems`; MCP `isError` is failure. Engine path, protected-reference and frozen-command gates remain authoritative. Extra inactive/resource-only native declarations do not confer engineering permissions.

The bridge checks actual thread provider/model/effort/cwd and sandbox/approval state before a turn. It rejects routing changes, unknown requests, new native permissions and unapproved effects. Thread/turn IDs, early events, duplicate call IDs, terminal status and cumulative usage are correlated. The literal reviewed instructions must reach the actual native request. Configuration graph identity is shared across the batch's turns; changed source/version/presence or effective values cannot be silently recaptured as a new approved baseline.

## Cancellation, results and cleanup

A cancel marker binds run ID, turn ID, generation and token. Observing cancel/rejection/terminal permanently closes new effect dispatch. The driver sends a correlated `turn/interrupt` request and requires both its response and the matching interrupted terminal within a separate finite grace deadline. It does not implement Pi queue-clear semantics. Silent output must not prevent observing cancellation.

Cumulative usage snapshots replace earlier snapshots; cached input is a subset of input. Failed/interrupted paths retain the last observed snapshot. A missing observation remains unknown and must not be described as actual zero. Response-token and aggregate-token/cost hard caps are unsupported; explicitly accepted audit mode records actual usage and enforces the supported wall/refinement bounds.

Success requires typed required checks, actual model/usage/terminal evidence and bounded owned cleanup: root exited, owned Job members empty, stdout/stderr closed, owner worker joined and resource observer closed. Unknown cleanup retains the owner lease and blocks a replacement writer. No name-based process termination, unrelated Desktop shutdown or automatic PID takeover is permitted.

Candidates return to the original runner/lead for independent acceptance. Typed needs-evidence returns to original PRIMARY, needs-spec/implementation failure to Spec runner, and scope/unsupported/cancelled cases to lead as defined by the return schema. Evidence, tasks and acceptance authority remain with their original owners.

Source, artifact integrity, metadata discovery, offline native protocol/owner fixtures, real provider execution and business acceptance are distinct evidence. A qualification record only establishes its explicitly observed version, controls and scope.
