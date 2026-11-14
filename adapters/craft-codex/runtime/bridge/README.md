# craft-codex-bridge

This crate owns one bounded Codex app-server v2 turn. It does not read, copy, print, or persist auth contents. Production execution uses the main-owned `codex-profile.json`, the actual stock `codex.exe`, and the normal selected `CODEX_HOME`.

`codex-app-server-driver --config /ABS/driver.json` reads one UTF-8 task and writes bounded JSONL. The config binds the raw runtime profile SHA, actual CLI SHA/version, fixed `app-server --stdio` argv and its fixed feature controls, empty environments, canonical configuration-layer hashes, and the six `craft_host` dynamic operations.

Before `thread/start`, the driver sends `config/read` with `cwd` and `includeLayers: true`. It extracts effective MCP IDs and layer metadata in memory, then sends one dotted `mcp_servers.<name>.enabled=false` override per ID in `thread/start.config`. It never calls the eager global `mcpServerStatus/list`. After thread creation it queries MCP status with the returned thread ID and requires every effective server to report `runtimeStatus: disabled` and `toolsError: null`.

The wire lifecycle is `initialize`, `initialized`, `config/read`, `thread/start`, `turn/start`, `item/tool/call`, latest cumulative `thread/tokenUsage/updated`, and `turn/completed.params.turn.status`. Early turn identity, tool requests and usage are retained while waiting for matching responses. Duplicate call IDs, native effect requests, unknown requests and unknown notifications fail closed. The six dynamic calls are forwarded to the original bounded Engine MCP executable supplied by the executor.

Cancellation sends one correlated `turn/interrupt`, waits for its successful response and an interrupted terminal event within an independent grace deadline, then verifies Codex/MCP owned cleanup, Job members and pipes. Response token hard caps remain unsupported; missing usage or actual model identity never becomes zero or a synthetic value.
