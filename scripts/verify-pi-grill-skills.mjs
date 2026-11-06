#!/usr/bin/env node
// Offline verification for the optional Pi grilling companion skills.
//
// This checks the local adapter structure only: every dependency must exist
// with valid frontmatter, the official skills must not carry the Pi adapter
// marker, and both shims must match the exact body the adapter generates for
// this skills root. Stale roots, marker-only shims and dropped
// domain-modeling references therefore fail.
//
// It cannot prove the official bodies are authentic upstream text because no
// upstream baseline is stored here.
//
// Usage: node scripts/verify-pi-grill-skills.mjs [skillsRoot]

import { SCOPE_NOTE, resolveSkillsRoot, verifySkills } from "./pi-grill-common.mjs";

const root = resolveSkillsRoot(process.argv[2]);
const result = verifySkills(root);

if (!result.ok) {
  console.error("Pi grilling verification failed:");
  for (const failure of result.failures) console.error(`- ${failure}`);
  console.error(SCOPE_NOTE);
  process.exitCode = 1;
} else {
  console.log(`Pi grilling adapter structure verified: ${root}`);
  console.log(SCOPE_NOTE);
}
