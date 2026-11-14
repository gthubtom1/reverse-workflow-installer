# craft-codex-executor

This is the new Codex app-server backend identity. It reuses the patched Craft implementation/check/refine worker and bounded `Engine::bounded_builder`; it does not add a research loop or a second coding owner.

Backend constants are:

- `backend_id: craft-codex-app-server-v1`
- `permission_contract: codex-dynamic-bounded-v1`
- Codex `0.167.0-alpha.4.1`, app-server protocol, native profile authentication

`--validate` is read-only and `--prepare` performs zero model calls. `--run` accepts only the prepared execution JSON with original handoff context. The owner, source digest, workspace, build/check/refine, typed return, lease and descendant cleanup gates are retained from the forked executor implementation. Candidate output always has `accepted: false`.

The Codex profile is the `provider_manifest` hashed reference. It contains no API key and no copied auth. Its shape is:

```json
{
  "version": 1,
  "backend_id": "craft-codex-app-server-v1",
  "permission_contract": "codex-dynamic-bounded-v1",
  "cli": {"path":"ABSOLUTE_CODEX_HOST_CLI","sha256":"64_HEX","version":"0.167.0-alpha.4.1"},
  "server": {"path":"ABSOLUTE_CODEX_BOUNDED_APP_SERVER","sha256":"64_HEX","version":"0.167.0-alpha.4.1","mode":"codex-bounded-app-server-stdio","args":["--listen","stdio://"],"source_sha256":"64_HEX","tool_policy_tag":"codex-bounded-tool-policy-v1","allow_tools":["mcp__craft__build_files_list","mcp__craft__build_file_read","mcp__craft__build_file_write","mcp__craft__build_file_edit","mcp__craft__build_command_run","mcp__craft__build_checklist"]},
  "auth": {"mode":"native-codex-home","config_root":"ABSOLUTE_CANONICAL_CODEX_HOME","config_source":{"path":"ABSOLUTE_CANONICAL_CODEX_HOME/config.toml","sha256":"64_HEX"},"mcp_inventory":{"path":"ABSOLUTE_SECRET_FREE_MCP_INVENTORY_JSON","sha256":"64_HEX"}},
  "model": {"model_provider":null,"model":"gpt/gpt-6.1-sol","effort":"high"},
  "budget": {"response_token_cap": null,"usage_mode":"audit-only"}
}
```

`response_token_cap: null` is mandatory. Audit-only mode records actual usage and enforces wall/refinement limits. A handoff that sets `response_hard_cap: true` is always rejected because this Codex profile has no qualified native per-response cap; a self-declared `response_token_cap` is also rejected. No `maxTokens` is invented and missing usage is never changed to zero.

The native execution entry requires these non-secret environment identities:

- `CRAFT_CODEX_CLI`: absolute path equal to the profile host CLI path;
- `CRAFT_CODEX_SERVER`: absolute path equal to the dedicated bounded server path;
- `CRAFT_CODEX_SERVER_SHA256`: exact server artifact SHA-256;
- `CRAFT_CODEX_SERVER_SOURCE_SHA256`: exact approved joint source/profile SHA;
- `CRAFT_CODEX_VERSION`: exact `0.167.0-alpha.4.1`;
- `CRAFT_CODEX_HOME` or `CODEX_HOME`: absolute path equal to profile `auth.config_root`; the CLI reads its normal selected profile/auth itself;
- `CRAFT_BUNDLE_ROOT`: existing absolute bundle root;
- `CRAFT_BUILDER_INSTRUCTIONS`: absolute path equal to the prepared instructions file.

`auth.config_root` must be an existing canonical directory with no link component. If its direct `config.toml` exists, `auth.config_source` is mandatory and must point to exactly that canonical file; its SHA-256 is checked again on every profile load. If the file is absent, `config_source` must be omitted and a later appearance rejects the profile. The file is hashed as raw bytes only; it is never parsed, copied, logged, or treated as auth data. It exposes only the six bounded MCP tools through a driver-owned MCP proxy. Built-in filesystem/shell/REA/research/native tools, plugins, hooks, skills, code mode and rerouting are not accepted by this contract.

The exact native app-server event spelling remains a qualification input. The driver accepts only the typed v1 normalized exchange documented by the bridge README and fails closed on unknown event shapes. The offline app-server/canned-response fixture is a protocol fixture, not a provider/model or business acceptance.
