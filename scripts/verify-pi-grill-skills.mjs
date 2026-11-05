#!/usr/bin/env node
// Offline verification for the optional Pi grilling companion skills.
// Usage: node scripts/verify-pi-grill-skills.mjs [skillsRoot]

import { readFileSync, existsSync } from "node:fs";
import { join, resolve } from "node:path";

const root = resolve(
  process.argv[2] ?? join(process.env.USERPROFILE ?? process.env.HOME ?? ".", ".agents", "skills"),
);

const required = ["grilling", "grill-me", "grill-with-docs", "domain-modeling"];
const failures = [];

for (const name of required) {
  const file = join(root, name, "SKILL.md");
  if (!existsSync(file)) {
    failures.push(`missing ${name}: ${file}`);
  }
}

const read = (name) => readFileSync(join(root, name, "SKILL.md"), "utf8");
if (!failures.length) {
  const official = ["grilling", "domain-modeling"];
  for (const name of official) {
    if (read(name).includes("<!-- pi-adapter:")) {
      failures.push(`official skill appears adapted: ${name}`);
    }
  }
  for (const name of ["grill-me", "grill-with-docs"]) {
    const text = read(name);
    if (!text.includes("<!-- pi-adapter:")) failures.push(`Pi adapter note missing: ${name}`);
    if (!text.includes("../grilling/SKILL.md")) failures.push(`grilling reference missing: ${name}`);
  }
}

if (failures.length) {
  console.error("Pi grilling verification failed:");
  for (const failure of failures) console.error(`- ${failure}`);
  process.exitCode = 1;
} else {
  console.log(`Pi grilling skills verified: ${root}`);
}
