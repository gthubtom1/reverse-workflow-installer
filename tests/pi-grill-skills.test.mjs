// Offline fixture tests for the optional Pi grilling adapter + verifier.
//
// No network, no installation, no real user profile: every case builds a
// throwaway skills root under the OS temp directory and passes it explicitly.
//
// Run with: node --test tests/pi-grill-skills.test.mjs

import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { existsSync, mkdirSync, mkdtempSync, readFileSync, writeFileSync } from "node:fs";
import { homedir, tmpdir } from "node:os";
import { dirname, join, resolve } from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

import {
  ADAPTER_MARKER,
  ADAPTER_NOTE,
  defaultSkillsRoot,
  resolveSkillsRoot,
} from "../scripts/pi-grill-common.mjs";

const here = dirname(fileURLToPath(import.meta.url));
const adaptScript = join(here, "..", "scripts", "pi-adapt-grill-skills.mjs");
const verifyScript = join(here, "..", "scripts", "verify-pi-grill-skills.mjs");

const frontmatter = (name) => `---\nname: ${name}\ndescription: offline fixture for ${name}\n---\n`;

// Stand-ins for the installed upstream skills. Their bodies are deliberately
// unique so "official bytes unchanged" can be asserted exactly.
const fixtures = {
  grilling: `${frontmatter("grilling")}\n# Grilling\n\nOfficial grilling fixture body: ask one question at a time.\n`,
  "domain-modeling": `${frontmatter("domain-modeling")}\n# Domain modeling\n\nOfficial domain-modeling fixture body: open an ADR only when the thresholds are met.\n`,
  "grill-me": `${frontmatter("grill-me")}\n# Grill me\n\nCall the Skill tool with skill: grilling.\n`,
  "grill-with-docs": `${frontmatter("grill-with-docs")}\n# Grill with docs\n\nCall the Skill tool with skills: grilling, domain-modeling.\n`,
};

function makeRoot({ skip = [], override = {} } = {}) {
  const root = mkdtempSync(join(tmpdir(), "pi-grill-fixture-"));
  for (const [name, text] of Object.entries(fixtures)) {
    if (skip.includes(name)) continue;
    const dir = join(root, name);
    mkdirSync(dir, { recursive: true });
    writeFileSync(join(dir, "SKILL.md"), override[name] ?? text);
  }
  return root;
}

const skillPath = (root, name) => join(root, name, "SKILL.md");
const read = (root, name) => readFileSync(skillPath(root, name), "utf8");
const snapshot = (root) =>
  Object.fromEntries(
    ["grilling", "domain-modeling", "grill-me", "grill-with-docs"].map((n) => [
      n,
      existsSync(skillPath(root, n)) ? readFileSync(skillPath(root, n)) : null,
    ]),
  );

function run(script, root) {
  return spawnSync(process.execPath, [script, root], { encoding: "utf8" });
}

test("adapts both shims against a custom root and keeps official bytes", () => {
  const root = makeRoot();
  const before = snapshot(root);

  const result = run(adaptScript, root);
  assert.equal(result.status, 0, result.stderr);
  assert.equal(result.stderr, "");

  // Official skills must be byte-identical.
  assert.deepEqual(readFileSync(skillPath(root, "grilling")), before.grilling);
  assert.deepEqual(readFileSync(skillPath(root, "domain-modeling")), before["domain-modeling"]);

  for (const name of ["grill-me", "grill-with-docs"]) {
    const text = read(root, name);
    assert.ok(text.startsWith(frontmatter(name)), `${name} keeps its original frontmatter`);
    assert.ok(text.includes(ADAPTER_MARKER), `${name} carries the adapter note`);
    assert.ok(text.includes(join(root, "grilling", "SKILL.md")), `${name} points at the custom root`);
    assert.ok(text.includes("../grilling/SKILL.md"), `${name} keeps the relative reference`);
  }

  const withDocs = read(root, "grill-with-docs");
  assert.ok(withDocs.includes(join(root, "domain-modeling", "SKILL.md")));
  assert.ok(withDocs.includes("../domain-modeling/SKILL.md"));
  assert.match(withDocs, /only when that skill's own ADR thresholds/);

  const verified = run(verifyScript, root);
  assert.equal(verified.status, 0, verified.stderr);
  assert.match(verified.stdout, /adapter structure verified/);
  assert.match(verified.stdout, /not verified/);
});

test("adaptation is idempotent", () => {
  const root = makeRoot();
  const first = run(adaptScript, root);
  assert.equal(first.status, 0, first.stderr);
  const afterFirst = snapshot(root);

  const second = run(adaptScript, root);
  assert.equal(second.status, 0, second.stderr);
  assert.match(second.stdout, /already adapted/);
  assert.match(second.stdout, /nothing to do/);

  assert.deepEqual(snapshot(root), afterFirst);
});

test("missing dependency aborts nonzero before any write", () => {
  const root = makeRoot({ skip: ["domain-modeling"] });
  const before = snapshot(root);

  const result = run(adaptScript, root);
  assert.notEqual(result.status, 0);
  assert.match(result.stderr, /missing dependency domain-modeling/);
  assert.match(result.stderr, /no files were written/);
  assert.deepEqual(snapshot(root), before);

  const verified = run(verifyScript, root);
  assert.notEqual(verified.status, 0);
  assert.match(verified.stderr, /missing dependency domain-modeling/);
});

test("malformed frontmatter or empty body aborts nonzero before any write", () => {
  const cases = [
    {
      name: "no frontmatter",
      override: { "grill-me": "# Grill me\n\nCall the Skill tool.\n" },
      pattern: /malformed grill-me: no YAML frontmatter/,
    },
    {
      name: "missing name field",
      override: { "grill-with-docs": "---\ndescription: no name\n---\n\nCall the Skill tool.\n" },
      pattern: /malformed grill-with-docs: frontmatter has no "name" field/,
    },
    {
      name: "empty body",
      override: { grilling: "---\nname: grilling\ndescription: empty\n---\n\n" },
      pattern: /malformed grilling: empty body/,
    },
  ];

  for (const { name, override, pattern } of cases) {
    const root = makeRoot({ override });
    const before = snapshot(root);
    const result = run(adaptScript, root);
    assert.notEqual(result.status, 0, name);
    assert.match(result.stderr, pattern, name);
    assert.deepEqual(snapshot(root), before, name);

    const verified = run(verifyScript, root);
    assert.notEqual(verified.status, 0, name);
    assert.match(verified.stderr, pattern, name);
  }
});

test("official skills carrying the adapter marker are rejected", () => {
  const root = makeRoot();
  const adapted = run(adaptScript, root);
  assert.equal(adapted.status, 0, adapted.stderr);

  writeFileSync(skillPath(root, "grilling"), fixtures.grilling + `\n${ADAPTER_MARKER} rewritten -->\n`);
  const before = snapshot(root);

  const again = run(adaptScript, root);
  assert.notEqual(again.status, 0);
  assert.match(again.stderr, /official skill was rewritten by the Pi adapter: grilling/);
  assert.deepEqual(snapshot(root), before);

  const verified = run(verifyScript, root);
  assert.notEqual(verified.status, 0);
  assert.match(verified.stderr, /official skill was rewritten by the Pi adapter: grilling/);
});

test("verifier detects stale custom-root references", () => {
  const root = makeRoot();
  assert.equal(run(adaptScript, root).status, 0);

  const staleRoot = join(root, "previous-skills-root");
  const text = read(root, "grill-me").replaceAll(root, staleRoot);
  writeFileSync(skillPath(root, "grill-me"), text);

  const result = run(verifyScript, root);
  assert.notEqual(result.status, 0);
  assert.match(result.stderr, /stale or wrong grilling reference in grill-me/);
  assert.ok(result.stderr.includes(join(root, "grilling", "SKILL.md")));
});

test("verifier detects marker-only shims", () => {
  const root = makeRoot();
  assert.equal(run(adaptScript, root).status, 0);

  writeFileSync(skillPath(root, "grill-me"), `${frontmatter("grill-me")}\n${ADAPTER_NOTE}\n`);

  const result = run(verifyScript, root);
  assert.notEqual(result.status, 0);
  assert.match(result.stderr, /grill-me adapter body is stale, marker-only or hand-edited/);
});

test("verifier detects a dropped domain-modeling reference", () => {
  const root = makeRoot();
  assert.equal(run(adaptScript, root).status, 0);

  const text = read(root, "grill-with-docs")
    .split("\n")
    .filter((line) => !line.includes("domain-modeling"))
    .join("\n");
  writeFileSync(skillPath(root, "grill-with-docs"), text);

  const result = run(verifyScript, root);
  assert.notEqual(result.status, 0);
  assert.match(result.stderr, /missing domain-modeling reference in grill-with-docs/);
});

test("default root resolves from the real home, not the working directory", () => {
  assert.equal(defaultSkillsRoot(), join(homedir(), ".agents", "skills"));
  assert.equal(resolveSkillsRoot(undefined), join(homedir(), ".agents", "skills"));
  assert.equal(resolveSkillsRoot("fixture-root"), resolve("fixture-root"));
  assert.notEqual(resolveSkillsRoot("fixture-root"), defaultSkillsRoot());
});
