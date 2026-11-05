#!/usr/bin/env node
// Re-apply the Pi adapter to Matt Pocock's grill-me / grill-with-docs skills.
//
// The upstream shims assume a harness with a Skill tool. Pi composes skills by
// reading SKILL.md files instead, so run this after installing or updating the
// official skills.
//
// Usage: node scripts/pi-adapt-grill-skills.mjs [skillsRoot]

import { readFileSync, writeFileSync, existsSync } from "node:fs";
import { join, resolve } from "node:path";

const root = resolve(
  process.argv[2] ?? join(process.env.USERPROFILE ?? process.env.HOME ?? ".", ".agents", "skills"),
);

const ADAPTER_NOTE =
  "<!-- pi-adapter: upstream body is a `Call the Skill tool ...` shim. Pi has no Skill tool; " +
  "skills compose by reading the other skill's SKILL.md. Re-run pi-adapt-grill-skills.mjs after `npx skills update`. -->";

const patches = {
  "grill-me": `Read the \`grilling\` skill and follow it exactly.

- Path: \`${join(root, "grilling", "SKILL.md")}\` (relative: \`../grilling/SKILL.md\`, resolved from this skill's directory).
- Do not summarize it back to the user. Load it, then start the interview.

This skill exists only so you can invoke that discipline by name.`,
  "grill-with-docs": `Read both of these skills, then follow them together:

1. \`grilling\` — \`${join(root, "grilling", "SKILL.md")}\` (relative: \`../grilling/SKILL.md\`)
2. \`domain-modeling\` — \`${join(root, "domain-modeling", "SKILL.md")}\` (relative: \`../domain-modeling/SKILL.md\`)

Run the grilling interview as written, and while it runs apply the domain-modeling discipline: challenge terminology, invent edge-case scenarios, and write \`GLOSSARY.md\` / \`docs/adr/*\` the moment a decision crystallises. Do not summarize them back to the user. Load them, then start.`,
};

let changed = 0;
for (const [name, body] of Object.entries(patches)) {
  const file = join(root, name, "SKILL.md");
  if (!existsSync(file)) {
    console.log(`skip ${name}: not installed at ${file}`);
    continue;
  }
  const text = readFileSync(file, "utf8");
  const match = text.match(/^---\r?\n([\s\S]*?)\r?\n---\r?\n/);
  if (!match) {
    console.log(`skip ${name}: no frontmatter`);
    continue;
  }
  const next = `${text.slice(0, match[0].length)}\n${ADAPTER_NOTE}\n\n${body}\n`;
  if (next === text) {
    console.log(`ok   ${name}: already adapted`);
    continue;
  }
  writeFileSync(file, next);
  changed += 1;
  console.log(`adapt ${name}: wrote ${file}`);
}
if (!changed) console.log("nothing to do");
