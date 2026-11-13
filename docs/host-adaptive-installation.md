# Host adaptive installation flow

This document is the entry contract for an AI that installs the combined reverse workflow environment on a new computer. It selects an existing official integration for the detected host and records the result. It does not replace REA, Spec Kit, Craft Anything, Codex, Pi, Claude Desktop, or the enhanced reverse-skill repository.

The official sources used by this flow are [REA](https://github.com/morluto/rea) and its [`rea-agents` setup documentation](https://github.com/morluto/rea#quick-start), [GitHub Spec Kit Codex integration](https://github.github.com/spec-kit/integrations/codex.html), [Craft Anything Codex integration](https://github.com/storytold/craft-anything/blob/main/docs/codex.md), [Codex AGENTS.md discovery](https://developers.openai.com/codex/agent-configuration/agents-md), [Codex Skills](https://developers.openai.com/codex/build-skills), and [Codex MCP](https://developers.openai.com/codex/mcp). Verify the applicable upstream source at plan time; these links are navigation, not a substitute for the actual version and host checks.

The installer is an orchestrator. It discovers the machine, prepares a frozen plan, invokes the official package or setup entry for the selected component, preserves user configuration, writes only the selected host resources, verifies the transaction, and reports host loading and representative-task checks separately.

## 1. Establish the host and scope

Read `README.md`, `AGENTS.md`, this file, `components.json`, `docs/compatibility.md`, and the relevant official source documentation before planning. Determine the target host from an explicit user choice or strong configuration evidence:

| Host | Primary configuration evidence | Host-owned entry resources |
|---|---|---|
| Pi CLI / Pi Web | `PI_CODING_AGENT_DIR`, Pi configuration schema, or the running Pi Web agent directory | Pi package, `mcp.json`, `settings.json`, user `AGENTS.md`, Pi skills, optional Pi profiles/extensions |
| Codex CLI / Codex desktop / IDE | `CODEX_HOME` and `config.toml`, or an explicit Codex project | `CODEX_HOME/AGENTS.md`, `CODEX_HOME/config.toml`, `$HOME/.agents/skills`, project `.agents/skills`, project `.codex/config.toml` |
| Claude Desktop | explicit `claude_desktop_config.json` | JSON MCP entries, project `CLAUDE.md`, project skills |
| none | explicit `--client none` | no host configuration; only selected source/package checks |

Do not select a host from the presence of a command in `PATH`, a model name, a directory name, or an old receipt. If evidence is ambiguous, ask for `--client pi|codex|claude` and an explicit configuration/agent directory. Do not enumerate environment values; inspect names, schemas, and paths only.

Resolve paths on the target computer. Do not copy paths from this repository, an old receipt, an example, or another computer. The installer root, agent/config root, project root, package cache, runtime, and official source checkout must be separate where the selected contract requires separation. Preserve existing files and report same-path content conflicts before changing them.

## 2. Use the official upstream entry for each component

The combined installer owns selection, isolation, version identity, transaction journaling, configuration preservation, and verification. The upstream project owns its setup semantics and resource layout.

| Component | Official upstream route | Combined-installer boundary |
|---|---|---|
| REA | `npx rea-agents setup`; review the proposed host changes, approve them, and restart the host. Official setup adds the REA MCP server and matching workflow instructions. | Resolve the official `rea-agents` package and Node engine, run the selected official setup in an isolated transaction, merge only the selected host entry, preserve other configuration, record exact identity, then verify MCP handshake and tools separately. |
| Spec Kit | `specify init <project> --integration <pi|codex|claude>`; for an existing project use the official integration install command. | Invoke the selected official integration, keep the project outside the tool repository, preserve existing project files, and record the generated native skills/prompts. Do not generate a second Spec Kit workflow. |
| enhanced reverse-skill | The public enhanced repository's `RULES.md`, native router, `skills/config/routing.json`, and selected PRIMARY skill. | Record the exact release/main commit or an explicitly supplied read-only local source. Do not copy the router into the installer or create a second case/Evidence authority. |
| Craft Anything upstream | Use the upstream CLI/setup for the selected host. For Codex, the official route is `craft-anything-cli setup --client codex --yes`, followed by `craft-anything-cli doctor --client codex`; it writes the upstream Craft MCP entry and its Codex approval shape. | Treat this as an upstream Craft host integration. Preserve its approval/consent semantics and backup behavior. Do not represent it as the native Craft-Pi execution backend. |
| Craft-Pi execution backend | The combined installer's `craft-pi` bundle, entry contract, Pi RPC driver, and separate official Pi/Node distribution. | This is our optional Pi-specific bounded execution backend. It requires the explicit reverse/Spec contract, local verified bundle, standalone Pi/Node identity, owner/cleanup gates, and independent acceptance. It is not a generic Craft host adapter. |
| Pi-only extensions | Official Pi package/plugin or a separately pinned Pi extension source, such as shell-guard. | Install only for Pi when the component declares Pi support. Do not copy Pi package registrations, Pi profiles, or Pi extensions into Codex or Claude. |

Official source facts must be checked at the version used by the plan. A README, package directory, or existing local artifact does not by itself prove a supported host, an official source, a working provider, or a completed task.

## 3. Select host resources without mixing contracts

### Pi and Pi Web

Use the actual shared Pi agent directory. Pi Web and Pi CLI must point to the same agent directory when they are intended to share sessions and resources. Install the Pi skill/package and selected MCP entries. Install the short Pi user `AGENTS.md` and Pi-only profiles only when the user selected those Pi resources. `subagent`, `reverse-operator`, and `reverse-reviewer` are Pi profile templates; they are not required reverse-skill components and are not Codex or Claude resources.

The native Craft-Pi bundle and shell-guard are Pi-only selections. Keep their package registration, resource inventory, receipt pointer, and host verification in the Pi transaction. Do not enable them because a user selected the general Craft or reverse capability without selecting the Pi host and the required contract.

### Codex CLI, Codex desktop, and Codex IDE

These Codex surfaces share the Codex host configuration for the selected `CODEX_HOME`. Use the actual `CODEX_HOME/config.toml` for MCP and the Codex `AGENTS.md` discovery chain for concise host guidance. Use the official Codex skill locations:

- user Skills: `$HOME/.agents/skills/`;
- repository Skills: `.agents/skills/` from the current directory up to the repository root;
- project-scoped MCP: trusted project `.codex/config.toml` when the user selects that scope.

Keep the global Codex `AGENTS.md` short. It should point Codex to the reverse-workflow Skill, the installed receipt, the enhanced reverse `RULES.md`, the native router, and the applicable Spec Kit Skills. It must not duplicate all reverse rules, create a second router, or turn a technical method into a user decision. Write global guidance only when the user selected that scope and the existing file passes conflict/ownership checks; otherwise use project-level `AGENTS.md` or project Skills.

Install the Codex reverse-workflow Skill in a location Codex actually discovers. Do not treat `CODEX_HOME/skills` as the Codex user Skills directory unless the current Codex documentation explicitly supports that path. The project `.agents/skills/reverse-workflow` entry may be used for a portable project installation. The reverse Codex plugin is optional; its presence does not replace the project Skill, MCP registration, or the enhanced reverse repository.

Register REA through the official setup/registration path and preserve all unrelated Codex MCP tables. Install Spec Kit with the official Codex integration. If the user selects upstream Craft Anything for Codex, use its official Codex setup and doctor flow; preserve the `rebuild_start` approval and Craft consent boundaries. Do not install Pi profiles, shell-guard, or Craft-Pi native resources into Codex.

### Claude Desktop

Use the explicit `claude_desktop_config.json` and the project `CLAUDE.md`/Skills layout described by the official integration. Merge only the selected REA MCP entry and preserve unrelated JSON fields. Use the Claude project entry to point to the receipt, enhanced reverse router, and native workflow. Do not register Pi packages or Craft-Pi resources.

## 4. Plan, apply, and verify on the real machine

The AI must produce a readable plan before the first side effect. The plan must contain:

- detected host evidence and the user's selected host scope;
- OS, architecture, runtime and dependency checks without secret values;
- resolved installation/config/project/package paths;
- selected components and omitted host-incompatible options;
- official source URLs, refs, versions, package integrity and local source identity;
- exact official commands or setup operations to be used;
- files that will be created, merged, or preserved;
- conflicts, missing accounts, missing provider engines, and unverified items;
- rollback and recovery boundaries.

Apply only the frozen plan. Reject source, path, configuration, host, component, or version drift and require a new plan. Do not silently upgrade, shrink a previous component scope, overwrite user edits, reuse another computer's receipt, or invent a completed marker after a network/provider failure.

After apply, report four separate states:

1. **Installed:** package/source/config files and receipt have the expected identity.
2. **Loaded:** the selected host actually discovered the intended AGENTS, Skill, package/plugin, and MCP resources after restart or reload.
3. **Running:** MCP initialization, tool schema/catalog, native router, and official Spec Kit setup or doctor command actually ran.
4. **Task verified:** a bounded representative task produced the expected evidence or result under the selected scope.

An installer exit code, copied file, Skill listing, MCP registration, Craft project state, or model self-report cannot upgrade one state into the next. Preserve unknowns and host-specific limits in the receipt/report.

## 5. Stop conditions and recovery

Stop before a side effect when the host is ambiguous, the target path is not owned by the user-selected scope, an existing managed file has later user edits, an official source cannot be resolved, a required runtime/provider is missing, or an optional backend is incompatible with the host. Explain the smallest missing input or the exact conflict.

For a failed transaction, read the transaction journal and use the installer restore/conditional recovery rules. Preserve user edits and unknown cleanup. Do not restore Pi registrations into Codex, copy Codex configuration into Pi, or treat a Craft-Pi receipt as an upstream Craft Codex receipt.

The combined installer is complete when the selected official routes, host paths, resource identities, configuration ownership, transaction state, and verification limits are all explicit. It is not complete when every optional component is installed on every host.
