// Shared logic for the optional Pi grilling companion skills.
//
// This module is intentionally side-effect free: both the adapter and the
// verifier import it, and the offline tests import it directly.
//
// Scope: it checks the *local* structure of the Pi adapter only. It never
// claims that the official `grilling` / `domain-modeling` bodies are
// authentic or unmodified upstream, because no upstream baseline is stored.

import { existsSync, readFileSync } from "node:fs";
import { homedir } from "node:os";
import { join, resolve } from "node:path";

export const ADAPTER_MARKER = "<!-- pi-adapter:";

export const ADAPTER_NOTE =
  "<!-- pi-adapter: upstream body is a `Call the Skill tool ...` shim. Pi has no Skill tool; " +
  "skills compose by reading the other skill's SKILL.md. This body is generated locally by " +
  "pi-adapt-grill-skills.mjs and is not upstream text. Re-run the script after `npx skills update`. -->";

export const SCOPE_NOTE =
  "scope: local Pi adapter structure only; upstream skill body authenticity is not verified " +
  "(no upstream baseline is stored).";

export const OFFICIAL_NAMES = ["grilling", "domain-modeling"];
export const SHIM_NAMES = ["grill-me", "grill-with-docs"];
export const REQUIRED_NAMES = [...OFFICIAL_NAMES, ...SHIM_NAMES];

/** Real user home, so the default root never depends on the current directory. */
export function defaultSkillsRoot() {
  const home = homedir() || process.env.USERPROFILE || process.env.HOME || ".";
  return join(home, ".agents", "skills");
}

export function resolveSkillsRoot(explicitRoot) {
  return resolve(explicitRoot ?? defaultSkillsRoot());
}

/**
 * Parse a SKILL.md document. Returns null when there is no leading frontmatter.
 * The returned frontmatter block is kept verbatim so shims preserve it byte for
 * byte.
 */
export function parseSkillDocument(text) {
  const match = text.match(/^---\r?\n([\s\S]*?)\r?\n---[ \t]*\r?\n/);
  if (!match) return null;
  const header = match[1];
  const nameLine = header.match(/^name[ \t]*:(.*)$/m);
  const name = nameLine ? nameLine[1].trim().replace(/^(['"])(.*)\1$/, "$2") : "";
  return {
    frontmatter: match[0],
    header,
    name,
    body: text.slice(match[0].length),
  };
}

export function shimBody(name, root) {
  const grilling = join(root, "grilling", "SKILL.md");
  const domainModeling = join(root, "domain-modeling", "SKILL.md");

  if (name === "grill-me") {
    return `Read the \`grilling\` skill and follow it exactly.

- Path: \`${grilling}\` (relative: \`../grilling/SKILL.md\`, resolved from this skill's directory).
- Do not summarize it back to the user. Load it, then start the interview.

This skill exists only so you can invoke that discipline by name.`;
  }

  if (name === "grill-with-docs") {
    return `Read both of these skills, then follow them together:

1. \`grilling\` — \`${grilling}\` (relative: \`../grilling/SKILL.md\`)
2. \`domain-modeling\` — \`${domainModeling}\` (relative: \`../domain-modeling/SKILL.md\`)

Run the grilling interview as written, and while it runs apply the domain-modeling discipline: challenge terminology and invent edge-case scenarios. Write \`GLOSSARY.md\` / \`docs/adr/*\` only when that skill's own ADR thresholds call for it — do not record every decision or blindly write an ADR per discussion point. Do not summarize them back to the user. Load them, then start.`;
  }

  throw new Error(`no Pi shim body is defined for ${name}`);
}

/**
 * The only accepted adapted text for a shim. Building it from the shim's own
 * frontmatter keeps the original frontmatter intact, and comparing against it
 * exactly rejects stale root references, marker-only shims and dropped
 * domain-modeling references.
 */
export function expectedShimText(originalText, name, root) {
  const document = parseSkillDocument(originalText);
  if (!document) return null;
  return `${document.frontmatter}\n${ADAPTER_NOTE}\n\n${shimBody(name, root)}\n`;
}

/**
 * Preflight every required skill before anything is written.
 * Returns { ok, problems, documents } where documents maps name -> raw text.
 */
export function preflightSkills(root) {
  const problems = [];
  const documents = new Map();

  for (const name of REQUIRED_NAMES) {
    const file = join(root, name, "SKILL.md");
    if (!existsSync(file)) {
      problems.push(`missing dependency ${name}: ${file}`);
      continue;
    }

    let text;
    try {
      text = readFileSync(file, "utf8");
    } catch (error) {
      problems.push(`unreadable ${name}: ${file} (${error.message})`);
      continue;
    }

    const document = parseSkillDocument(text);
    if (!document) {
      problems.push(`malformed ${name}: no YAML frontmatter in ${file}`);
      continue;
    }
    if (!document.name) {
      problems.push(`malformed ${name}: frontmatter has no "name" field in ${file}`);
    } else if (document.name !== name) {
      problems.push(`malformed ${name}: frontmatter name "${document.name}" does not match directory ${file}`);
    }
    if (!document.body.trim()) {
      problems.push(`malformed ${name}: empty body after frontmatter in ${file}`);
    }

    if (OFFICIAL_NAMES.includes(name) && text.includes(ADAPTER_MARKER)) {
      problems.push(`official skill was rewritten by the Pi adapter: ${name} (${file}); reinstall the official skill`);
    }

    documents.set(name, text);
  }

  return { ok: problems.length === 0, problems, documents };
}

/** Verify the local adapter structure. Returns { ok, failures }. */
export function verifySkills(root) {
  const preflight = preflightSkills(root);
  if (!preflight.ok) return { ok: false, failures: preflight.problems };

  const failures = [];

  for (const name of SHIM_NAMES) {
    const text = preflight.documents.get(name);
    const expected = expectedShimText(text, name, root);

    if (!text.includes(ADAPTER_MARKER)) {
      failures.push(`Pi adapter note missing: ${name} (not adapted yet)`);
      continue;
    }
    if (text === expected) continue;

    if (!text.includes(join(root, "grilling", "SKILL.md"))) {
      failures.push(`stale or wrong grilling reference in ${name}: expected ${join(root, "grilling", "SKILL.md")}`);
    }
    if (name === "grill-with-docs" && !text.includes(join(root, "domain-modeling", "SKILL.md"))) {
      failures.push(`missing domain-modeling reference in ${name}: expected ${join(root, "domain-modeling", "SKILL.md")}`);
    }
    failures.push(`${name} adapter body is stale, marker-only or hand-edited; re-run pi-adapt-grill-skills.mjs`);
  }

  return { ok: failures.length === 0, failures };
}
