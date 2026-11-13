# Pi Web profile templates

This directory contains optional Pi Web agent profile templates: short user-level working principles and three task profiles. They use Pi Web's agent-profile loader; another Pi host needs equivalent profile support. The conversation chooses direct work or collaboration for the actual task; these templates do not prescribe a team or a fixed sequence. Preserve the target user’s existing profiles, built-in agent switches, model choices and tool configuration. Copy selected templates into the active Pi agent directory.

The explicit `load_skills` and `load_extensions` fields are boolean loading switches. Pi Web 0.15.0 also accepts boolean `skills` and `extensions` as compatibility switches; explicit `load_*` values take precedence. Resource-name strings/lists in `skills` and `extensions` can also select resources; these templates use boolean values. The existing redundant boolean compatibility fields in the reverse profiles are preserved; they are not resource names or an additional runtime schema. Check the target host's loader when using a different version.

- Copy AGENTS.md to <agent-dir>/AGENTS.md.
- Copy only agents/subagent.md, agents/reverse-operator.md, and agents/reverse-reviewer.md to <agent-dir>/agents/.
- When upgrading the former eight-template set, move only ui-implementer.md, ui-reviewer.md, backend-worker.md, requirements-planner.md, and scout.md out of profile discovery paths using the available trash mechanism. Do not leave .new or disabled Markdown copies there. Preserve and report any other custom profiles; do not delete unknown user files. See the installation guide for conflict handling.
- The templates intentionally omit provider and model pins. Choose models in Pi Web on the target machine.
- Do not copy credentials, models.json, settings.json, sessions, memory or other local state from the source computer.
