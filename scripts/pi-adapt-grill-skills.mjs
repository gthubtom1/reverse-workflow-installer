#!/usr/bin/env node
// Re-apply the Pi adapter to Matt Pocock's grill-me / grill-with-docs skills.
//
// The upstream shims assume a harness with a Skill tool. Pi composes skills by
// reading SKILL.md files instead, so run this after installing or updating the
// official skills.
//
// All four skills are preflighted before anything is written, so a missing or
// malformed dependency aborts with a nonzero exit and no partial edits.
//
// Usage: node scripts/pi-adapt-grill-skills.mjs [skillsRoot]

import { writeFileSync } from "node:fs";
import { join } from "node:path";

import {
  SCOPE_NOTE,
  SHIM_NAMES,
  expectedShimText,
  preflightSkills,
  resolveSkillsRoot,
} from "./pi-grill-common.mjs";

const root = resolveSkillsRoot(process.argv[2]);
const preflight = preflightSkills(root);

if (!preflight.ok) {
  console.error("Pi grilling adaptation aborted; no files were written:");
  for (const problem of preflight.problems) console.error(`- ${problem}`);
  console.error(SCOPE_NOTE);
  process.exitCode = 1;
} else {
  // Compute every expected body first, then write. Nothing is touched until
  // the whole plan is known to be valid.
  const plan = SHIM_NAMES.map((name) => {
    const file = join(root, name, "SKILL.md");
    const original = preflight.documents.get(name);
    const next = expectedShimText(original, name, root);
    if (next === null) throw new Error(`preflighted ${name} has no frontmatter`);
    return { name, file, original, next };
  });

  const pending = plan.filter((entry) => entry.next !== entry.original);
  for (const entry of pending) writeFileSync(entry.file, entry.next);

  for (const entry of plan) {
    if (entry.next === entry.original) {
      console.log(`ok   ${entry.name}: already adapted`);
    } else {
      console.log(`adapt ${entry.name}: wrote ${entry.file}`);
    }
  }
  if (!pending.length) console.log("nothing to do");
  console.log(SCOPE_NOTE);
}
