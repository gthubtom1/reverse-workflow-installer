// Offline tests. All fixtures and their recycle area stay in .local/tests/.
// No actual profile, npm/uv/setup/init, network, or destructive cleanup.
import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import {
  chmodSync, existsSync, linkSync, lstatSync, mkdirSync, mkdtempSync, readFileSync,
  readdirSync, readlinkSync, renameSync, statSync, symlinkSync, writeFileSync,
} from "node:fs";
import { homedir } from "node:os";
import { basename, join, resolve } from "node:path";
import test, { after } from "node:test";
import { fileURLToPath } from "node:url";
import {
  ADAPTER_MARKER, ALL_OFFICIAL_NAMES, MANIFEST_NAME, OWNER, PACKAGE_NAME, SHIM_NAMES,
  applyInstallation, assertPlainPath, defaultSkillsRoot, parseSkillDocument,
  planInstallation, resolveSkillsRoot, sha256, stableJson,
} from "../scripts/pi-grill-common.mjs";

const repository = fileURLToPath(new URL("..", import.meta.url));
const testBase = join(repository, ".local", "tests");
assertPlainPath(testBase);
mkdirSync(testBase, { recursive: true });
const suite = mkdtempSync(join(testBase, "pi-grill-"));
// Keep failure evidence without leaving active temporary roots or unlinking links.
after(() => {
  const recycle = join(testBase, ".recycle");
  assertPlainPath(recycle);
  mkdirSync(recycle, { recursive: true });
  renameSync(suite, join(recycle, basename(suite)));
});
const adaptScript = join(repository, "scripts", "pi-adapt-grill-skills.mjs");
const verifyScript = join(repository, "scripts", "verify-pi-grill-skills.mjs");
const frontmatter = (name) => `---\nname: ${name}\ndescription: Offline fixture for ${name}\n---\n`;
const fixtures = Object.fromEntries(ALL_OFFICIAL_NAMES.map((name) => [name,
  `${frontmatter(name)}\n# ${name}\n\nUnmodified official fixture body.\n`,
]));
function makeFixture({ skip = [], override = {} } = {}) {
  const directory = mkdtempSync(join(suite, "case-"));
  const root = join(directory, "official skills");
  const output = join(directory, "owned wrappers");
  mkdirSync(root);
  for (const [name, text] of Object.entries(fixtures)) {
    if (skip.includes(name)) continue;
    mkdirSync(join(root, name, "references"), { recursive: true });
    writeFileSync(join(root, name, "SKILL.md"), override[name] ?? text);
    writeFileSync(join(root, name, "references", "fixture.bin"), Buffer.from([0, 255, 13, 10, 42]));
  }
  return { directory, root, output };
}
const skillPath = (root, name) => join(root, name, "SKILL.md");
const readSkill = (root, name) => readFileSync(skillPath(root, name), "utf8");
function tree(root) {
  if (!existsSync(root)) return null;
  const entries = {};
  function visit(path, rel) {
    const st = lstatSync(path);
    if (st.isSymbolicLink()) entries[rel] = { link: readlinkSync(path) };
    else if (st.isDirectory()) {
      entries[rel] = "directory";
      for (const name of readdirSync(path).sort()) visit(join(path, name), `${rel}/${name}`);
    } else if (st.isFile()) entries[rel] = readFileSync(path).toString("hex");
    else entries[rel] = { specialFileMode: st.mode };
  }
  visit(root, ".");
  return entries;
}
function run(script, args) {
  const result = spawnSync(process.execPath, [script, ...args], { encoding: "utf8", timeout: 15000, cwd: repository });
  assert.ifError(result.error);
  return result;
}
function cli(script, fixture, extra = []) {
  return run(script, ["--skills-root", fixture.root, "--output-root", fixture.output, ...extra]);
}
function adapt(fixture) {
  const result = cli(adaptScript, fixture);
  assert.equal(result.status, 0, result.stderr + result.stdout);
  return result;
}
function verify(fixture) {
  const before = tree(fixture.directory);
  const result = cli(verifyScript, fixture);
  assert.deepEqual(tree(fixture.directory), before, "verifier is read-only");
  return result;
}
function rejectWithoutWrites(fixture, pattern) {
  const before = tree(fixture.directory);
  const result = cli(adaptScript, fixture);
  assert.equal(result.status, 1, result.stderr + result.stdout);
  assert.match(result.stderr, /no files were written/);
  if (pattern) assert.match(result.stderr, pattern);
  assert.deepEqual(tree(fixture.directory), before, "preflight failure writes no files or directories");
  const checked = verify(fixture);
  assert.equal(checked.status, 1);
  return result;
}
function makeLink(t, target, path, kind = "directory") {
  try { symlinkSync(target, path, kind === "directory" ? (process.platform === "win32" ? "junction" : "dir") : "file"); }
  catch (error) {
    if (["EPERM", "EACCES", "ENOTSUP", "ENOSYS"].includes(error.code)) {
      t.skip(`link unavailable on this host: ${error.code}`);
      return false;
    }
    throw error;
  }
  return true;
}

// A cold install, hashes and byte identity are checked independently of templates.
test("separate wrappers preserve every official file including companions and resources", () => {
  const fixture = makeFixture({ override: { grilling: fixtures.grilling.replaceAll("\n", "\r\n") } });
  const before = tree(fixture.root);
  adapt(fixture);
  assert.deepEqual(tree(fixture.root), before);
  const manifest = JSON.parse(readFileSync(join(fixture.output, MANIFEST_NAME), "utf8"));
  assert.equal(manifest.owner, OWNER);
  assert.match(manifest.provenance, /upstream-authentication-not-performed/);
  const { sha256: digest, ...payload } = manifest;
  assert.equal(digest, sha256(stableJson(payload)));
  for (const input of manifest.officialInputs) assert.equal(input.sha256, sha256(readFileSync(input.path)));
  for (const name of SHIM_NAMES) {
    const text = readSkill(fixture.output, name);
    assert.equal(parseSkillDocument(text).name, name);
    assert.ok(text.includes(ADAPTER_MARKER));
    assert.ok(text.includes(fixture.root.replaceAll("\\", "/")));
    assert.equal(sha256(Buffer.from(text)), manifest.files[`${name}/SKILL.md`]);
    assert.equal(existsSync(join(fixture.root, name)), false);
  }
  assert.ok(readSkill(fixture.output, "pi-grill-with-docs").includes("domain-modeling/SKILL.md"));
  assert.equal(verify(fixture).status, 0);
});

test("output package declares only the two exact skills and has its own managed hash", () => {
  const fixture = makeFixture();
  adapt(fixture);
  const bytes = readFileSync(join(fixture.output, PACKAGE_NAME));
  const pkg = JSON.parse(bytes);
  assert.deepEqual(pkg.pi, {
    skills: ["./pi-grill-me/SKILL.md", "./pi-grill-with-docs/SKILL.md"],
    extensions: [], prompts: [], themes: [],
  });
  assert.equal(pkg.private, true);
  assert.deepEqual(Object.keys(pkg).sort(), ["description", "keywords", "name", "pi", "private", "version"]);
  const manifest = JSON.parse(readFileSync(join(fixture.output, MANIFEST_NAME)));
  assert.equal(manifest.templateVersion, 2);
  assert.equal(manifest.files[PACKAGE_NAME], sha256(bytes));
  assert.deepEqual(Object.keys(manifest.files).sort(), ["package.json", "pi-grill-me/SKILL.md", "pi-grill-with-docs/SKILL.md"]);
  assert.equal(verify(fixture).status, 0);
});

function sealFixtureManifest(fixture, payload) {
  writeFileSync(join(fixture.output, MANIFEST_NAME), stableJson({ ...payload, sha256: sha256(stableJson(payload)) }));
}
function makeVersion1(fixture) {
  adapt(fixture);
  renameSync(join(fixture.output, PACKAGE_NAME), join(fixture.directory, "saved-package.json"));
  const { sha256: _digest, files, ...payload } = JSON.parse(readFileSync(join(fixture.output, MANIFEST_NAME)));
  sealFixtureManifest(fixture, {
    ...payload, templateVersion: 1,
    files: Object.fromEntries(Object.entries(files).filter(([file]) => file !== PACKAGE_NAME)),
  });
}

test("owned version 1 upgrades by adding the package without changing official bytes", () => {
  const fixture = makeFixture();
  makeVersion1(fixture);
  const before = tree(fixture.root);
  const wrappers = SHIM_NAMES.map((name) => readSkill(fixture.output, name));
  assert.equal(verify(fixture).status, 1, "old output is not a current package");
  const result = cli(adaptScript, fixture, ["--json"]);
  assert.equal(result.status, 0, result.stdout + result.stderr);
  assert.deepEqual(JSON.parse(result.stdout).changed, [PACKAGE_NAME, MANIFEST_NAME]);
  assert.deepEqual(SHIM_NAMES.map((name) => readSkill(fixture.output, name)), wrappers);
  assert.deepEqual(tree(fixture.root), before);
  assert.equal(verify(fixture).status, 0);
});

test("version 1 cannot adopt an existing package even when its bytes match", () => {
  const fixture = makeFixture();
  makeVersion1(fixture);
  writeFileSync(join(fixture.output, PACKAGE_NAME), readFileSync(join(fixture.directory, "saved-package.json")));
  rejectWithoutWrites(fixture, /not owned by the previous manifest/);
});

test("a standalone existing package does not establish installer ownership", () => {
  const fixture = makeFixture();
  mkdirSync(fixture.output);
  writeFileSync(join(fixture.output, PACKAGE_NAME), '{"name":"user-package"}\n');
  rejectWithoutWrites(fixture, /no manifest/);
});

test("second generation is byte/mtime idempotent, including deterministic manifest", () => {
  const fixture = makeFixture();
  adapt(fixture);
  const paths = [MANIFEST_NAME, PACKAGE_NAME, ...SHIM_NAMES.map((name) => `${name}/SKILL.md`)];
  const before = tree(fixture.directory);
  const mtimes = paths.map((file) => statSync(join(fixture.output, file), { bigint: true }).mtimeNs);
  assert.match(adapt(fixture).stdout, /already generated/);
  assert.deepEqual(tree(fixture.directory), before);
  assert.deepEqual(paths.map((file) => statSync(join(fixture.output, file), { bigint: true }).mtimeNs), mtimes);
});

test("missing optional companions are recorded without creating them", () => {
  const fixture = makeFixture({ skip: ["grill-me", "grill-with-docs"] });
  const before = tree(fixture.root);
  adapt(fixture);
  assert.deepEqual(tree(fixture.root), before);
  const inputs = JSON.parse(readFileSync(join(fixture.output, MANIFEST_NAME))).officialInputs;
  assert.equal(inputs.find((input) => input.name === "grill-me").sha256, null);
  assert.equal(verify(fixture).status, 0);
});

test("legacy companion drift is reported without rewriting or loading either companion", () => {
  const fixture = makeFixture({ override: {
    "grill-me": `${fixtures["grill-me"]}\n${ADAPTER_MARKER} legacy -->\n`,
    "grill-with-docs": `${fixtures["grill-with-docs"]}\n${ADAPTER_MARKER} legacy -->\n`,
  } });
  const before = tree(fixture.root);
  const result = cli(adaptScript, fixture, ["--json"]);
  assert.equal(result.status, 0, result.stdout + result.stderr);
  assert.equal(result.stderr, "");
  assert.equal(JSON.parse(result.stdout).warnings.length, 2);
  assert.match(verify(fixture).stderr, /legacy drift/);
  for (const name of SHIM_NAMES) {
    const text = readSkill(fixture.output, name);
    assert.ok(!text.includes("grill-me/SKILL.md"));
    assert.ok(!text.includes("grill-with-docs/SKILL.md"));
  }
  assert.deepEqual(tree(fixture.root), before);
});

for (const name of ["grilling", "domain-modeling"]) {
  test(`missing ${name} fails before output parents are created`, () => {
    const fixture = makeFixture({ skip: [name] });
    fixture.output = join(fixture.directory, "absent", "nested", "wrappers");
    rejectWithoutWrites(fixture, /missing official dependency/);
  });
  test(`legacy drift in loaded dependency ${name} is blocking`, () => {
    rejectWithoutWrites(makeFixture({ override: { [name]: `${fixtures[name]}\n${ADAPTER_MARKER} legacy -->\n` } }), /dependency has legacy adapter drift/);
  });
}
const malformed = [
  ["no frontmatter", "# no frontmatter\n"],
  ["wrong name", fixtures.grilling.replace("name: grilling", "name: other")],
  ["empty body", frontmatter("grilling")],
  ["missing description", "---\nname: grilling\n---\nBody\n"],
  ["empty description", "---\nname: grilling\ndescription: ''\n---\nBody\n"],
  ["unterminated quote", "---\nname: grilling\ndescription: 'unterminated\n---\nBody\n"],
  ["duplicate name", "---\nname: grilling\nname: grilling\ndescription: test\n---\nBody\n"],
  ["array description", "---\nname: grilling\ndescription: [test]\n---\nBody\n"],
  ["unsupported YAML", "---\nname: grilling\ndescription: test\nmetadata:\n  nested: test\n---\nBody\n"],
  ["invalid UTF-8", Buffer.from([0xff, 0xfe, 0x00])],
  ["binary control character", `${fixtures.grilling}\x00`],
];
for (const [label, text] of malformed) {
  test(`malformed input (${label}) yields nonzero and zero writes`, () => {
    rejectWithoutWrites(makeFixture({ override: { grilling: text } }));
  });
}

test("missing official root fails before any output write", () => {
  const fixture = makeFixture();
  fixture.root = join(fixture.directory, "missing-official-root");
  rejectWithoutWrites(fixture, /unreadable official skills root/);
});

test("a directory at an official SKILL.md path is rejected", () => {
  const fixture = makeFixture();
  const path = skillPath(fixture.root, "grilling");
  renameSync(path, join(fixture.directory, "saved-input.md"));
  mkdirSync(path);
  rejectWithoutWrites(fixture, /not a regular file/);
});

test("an existing optional companion directory with no SKILL.md is malformed", () => {
  const fixture = makeFixture();
  renameSync(skillPath(fixture.root, "grill-me"), join(fixture.directory, "saved-companion.md"));
  rejectWithoutWrites(fixture, /missing official companion/);
});

for (const kind of ["input", "output"]) test(`POSIX FIFO ${kind} is rejected without blocking`, { skip: process.platform === "win32" }, (t) => {
  const fixture = makeFixture();
  if (kind === "output") adapt(fixture);
  const path = kind === "input" ? skillPath(fixture.root, "grilling") : join(fixture.output, PACKAGE_NAME);
  renameSync(path, join(fixture.directory, "saved-file"));
  const result = spawnSync("mkfifo", [path], { encoding: "utf8", timeout: 5000 });
  if (result.error?.code === "ENOENT") { t.skip("mkfifo is unavailable"); return; }
  assert.ifError(result.error);
  assert.equal(result.status, 0, result.stderr);
  rejectWithoutWrites(fixture, /not a regular file|must be a file/);
});

test("supported quoted fields, BOM/CRLF and folded descriptions load", () => {
  const text = "\uFEFF---\r\nname: 'grilling'\r\ndescription: >-\r\n  First line\r\n  next line\r\n---\r\nBody\r\n";
  const fixture = makeFixture({ override: { grilling: text } });
  adapt(fixture);
  assert.equal(verify(fixture).status, 0);
});

test("malformed existing companion fails without silently excluding its bytes", () => {
  rejectWithoutWrites(makeFixture({ override: { "grill-with-docs": "not a skill" } }), /malformed grill-with-docs/);
});

test("changed input updates owned wrappers/manifest and remains byte-identical itself", () => {
  const fixture = makeFixture();
  adapt(fixture);
  const beforeWrapper = readSkill(fixture.output, "pi-grill-me");
  writeFileSync(skillPath(fixture.root, "grilling"), `${fixtures.grilling}\nUpstream fixture update.\n`);
  const before = tree(fixture.root);
  assert.equal(verify(fixture).status, 1);
  adapt(fixture);
  assert.deepEqual(tree(fixture.root), before);
  assert.notEqual(readSkill(fixture.output, "pi-grill-me"), beforeWrapper);
  assert.equal(verify(fixture).status, 0);
});

test("companion byte drift is detected even though wrappers do not load companions", () => {
  const fixture = makeFixture();
  adapt(fixture);
  writeFileSync(skillPath(fixture.root, "grill-me"), `${fixtures["grill-me"]}\nCompanion update.\n`);
  const before = tree(fixture.root);
  assert.equal(verify(fixture).status, 1);
  adapt(fixture);
  assert.deepEqual(tree(fixture.root), before);
  assert.equal(verify(fixture).status, 0);
});

for (const file of [MANIFEST_NAME, PACKAGE_NAME, ...SHIM_NAMES.map((name) => `${name}/SKILL.md`)]) {
  test(`user edits to ${file} block every output update`, () => {
    const fixture = makeFixture();
    adapt(fixture);
    writeFileSync(skillPath(fixture.root, "domain-modeling"), `${fixtures["domain-modeling"]}\nUpstream update\n`);
    writeFileSync(join(fixture.output, file), "User-owned notes\n");
    rejectWithoutWrites(fixture, /ownership conflict/);
  });
}

for (const file of [PACKAGE_NAME, ...SHIM_NAMES.map((name) => `${name}/SKILL.md`)]) {
  test(`resealing edited ${file} still cannot grant ownership of unknown templates`, () => {
    const fixture = makeFixture();
    adapt(fixture);
    if (file === PACKAGE_NAME) {
      const pkg = JSON.parse(readFileSync(join(fixture.output, file)));
      pkg.pi.extensions = ["./unexpected-extension.mjs"];
      writeFileSync(join(fixture.output, file), stableJson(pkg));
    } else writeFileSync(join(fixture.output, file), "User instructions\n");
    const { sha256: _digest, ...payload } = JSON.parse(readFileSync(join(fixture.output, MANIFEST_NAME)));
    payload.files[file] = sha256(readFileSync(join(fixture.output, file)));
    sealFixtureManifest(fixture, payload);
    rejectWithoutWrites(fixture, /does not describe a known generated file/);
  });
}

test("manifest byte edits cannot be silently normalized/overwritten", () => {
  const fixture = makeFixture();
  adapt(fixture);
  const path = join(fixture.output, MANIFEST_NAME);
  writeFileSync(path, `${readFileSync(path, "utf8")}\n`);
  rejectWithoutWrites(fixture, /manifest hash or canonical bytes changed/);
});

test("manifest hash tampering is detected", () => {
  const fixture = makeFixture();
  adapt(fixture);
  const path = join(fixture.output, MANIFEST_NAME);
  const manifest = JSON.parse(readFileSync(path));
  manifest.files["pi-grill-me/SKILL.md"] = "0".repeat(64);
  writeFileSync(path, stableJson(manifest));
  rejectWithoutWrites(fixture, /manifest hash or canonical bytes changed/);
});

for (const mutation of ["owner", "version", "extra-path", "missing-package-hash", "root", "input-provenance"]) {
  test(`malformed ownership identity (${mutation}) is rejected even with a matching digest`, () => {
    const fixture = makeFixture();
    adapt(fixture);
    const { sha256: _digest, ...payload } = JSON.parse(readFileSync(join(fixture.output, MANIFEST_NAME)));
    if (mutation === "owner") payload.owner = "someone-else";
    if (mutation === "version") payload.templateVersion = 999;
    if (mutation === "extra-path") payload.files["../outside.md"] = "0".repeat(64);
    if (mutation === "missing-package-hash") payload.files = Object.fromEntries(Object.entries(payload.files).filter(([file]) => file !== PACKAGE_NAME));
    if (mutation === "root") payload.officialRoot = fixture.directory;
    if (mutation === "input-provenance") payload.officialInputs[0].path = join(fixture.directory, "wrong-input.md");
    sealFixtureManifest(fixture, payload);
    rejectWithoutWrites(fixture, /ownership conflict/);
  });
}

test("legacy companion warnings survive an output conflict", () => {
  const fixture = makeFixture({ override: { "grill-me": `${fixtures["grill-me"]}\n${ADAPTER_MARKER} legacy -->\n` } });
  mkdirSync(fixture.output);
  writeFileSync(join(fixture.output, "user.txt"), "user bytes\n");
  const before = tree(fixture.directory);
  const result = cli(adaptScript, fixture, ["--json"]);
  assert.equal(result.status, 1);
  const record = JSON.parse(result.stdout);
  assert.equal(record.warnings.length, 1);
  assert.match(record.warnings[0], /legacy drift/);
  assert.equal(record.writePhaseStarted, false);
  assert.deepEqual(tree(fixture.directory), before);
});

test("a marker-only legacy draft does not grant ownership", () => {
  const fixture = makeFixture();
  mkdirSync(join(fixture.output, "pi-grill-me"), { recursive: true });
  writeFileSync(skillPath(fixture.output, "pi-grill-me"), `${frontmatter("pi-grill-me")}\n${ADAPTER_MARKER} draft -->\n`);
  rejectWithoutWrites(fixture, /no manifest/);
});

test("nonempty unrelated root is not adopted", () => {
  const fixture = makeFixture();
  mkdirSync(fixture.output);
  writeFileSync(join(fixture.output, "user.txt"), "user file");
  rejectWithoutWrites(fixture, /unexpected entry/);
});

test("extra user resources under managed wrappers are preserved and block updates", () => {
  const fixture = makeFixture();
  adapt(fixture);
  writeFileSync(join(fixture.output, "pi-grill-me", "notes.txt"), "user file");
  rejectWithoutWrites(fixture, /unexpected wrapper files/);
});

for (const file of [MANIFEST_NAME, PACKAGE_NAME, ...SHIM_NAMES.map((name) => `${name}/SKILL.md`)]) {
  test(`missing managed ${file} cannot be silently recreated`, () => {
    const fixture = makeFixture();
    adapt(fixture);
    renameSync(join(fixture.output, file), join(fixture.directory, "saved-output"));
    rejectWithoutWrites(fixture, /ownership conflict/);
  });
}

test("malformed input blocks updates to an existing installation", () => {
  const fixture = makeFixture();
  adapt(fixture);
  writeFileSync(skillPath(fixture.root, "grilling"), "malformed");
  rejectWithoutWrites(fixture, /malformed grilling/);
});

for (const kind of ["same", "descendant", "ancestor", "companion"]) {
  test(`output cannot overlap official paths (${kind})`, () => {
    const fixture = makeFixture();
    fixture.output = kind === "same" ? fixture.root : kind === "ancestor" ? fixture.directory :
      kind === "companion" ? join(fixture.root, "grill-me", "wrappers") : join(fixture.root, "wrappers");
    rejectWithoutWrites(fixture, /path conflict/);
  });
}

test("an output path that is a regular file is rejected", () => {
  const fixture = makeFixture();
  writeFileSync(fixture.output, "user file");
  rejectWithoutWrites(fixture, /must be a directory/);
});

test("an output path whose ancestor is a regular file is rejected without writes", () => {
  const fixture = makeFixture();
  const parent = join(fixture.directory, "file-parent");
  writeFileSync(parent, "user bytes");
  fixture.output = join(parent, "wrappers");
  rejectWithoutWrites(fixture, /must be a directory/);
});

test("control characters in output roots are rejected before creating directories", () => {
  const fixture = makeFixture();
  fixture.output = join(fixture.directory, "newline\nroot");
  rejectWithoutWrites(fixture, /control characters/);
});

test("case aliases of official paths also conflict on Windows", { skip: process.platform !== "win32" }, () => {
  const fixture = makeFixture();
  fixture.output = fixture.root.toUpperCase();
  rejectWithoutWrites(fixture, /path conflict/);
});

for (const component of ["NUL", "con.txt", "NUL .txt", "LPT1", "COM¹.log", "trailing.", "trailing ", "output:stream", "bad?name"]) {
  test(`Windows ambiguous output component fails before creating parents: ${component}`, { skip: process.platform !== "win32" }, () => {
    const fixture = makeFixture();
    fixture.output = join(fixture.directory, "absent-parent", component, "wrappers");
    rejectWithoutWrites(fixture, /ambiguous or reserved Windows output path/);
  });
}

test("Windows device namespace output is rejected", { skip: process.platform !== "win32" }, () => {
  const fixture = makeFixture();
  fixture.output = `\\\\?\\${fixture.output}`;
  rejectWithoutWrites(fixture, /device namespace output/);
});

test("an output sibling sharing the official directory prefix remains valid", () => {
  const fixture = makeFixture();
  fixture.output = `${fixture.root}-wrappers`;
  adapt(fixture);
  assert.equal(verify(fixture).status, 0);
});

test("official readonly directories and normal POSIX directory link counts work", () => {
  const fixture = makeFixture();
  const path = skillPath(fixture.root, "grilling");
  chmodSync(path, 0o444);
  if (process.platform !== "win32") {
    assert.ok(statSync(join(fixture.root, "grilling")).nlink > 1);
    chmodSync(fixture.root, 0o555);
  }
  try { adapt(fixture); assert.equal(verify(fixture).status, 0); }
  finally { chmodSync(fixture.root, 0o755); chmodSync(path, 0o644); }
});

test("official root may be a readonly directory link/junction", (t) => {
  const fixture = makeFixture();
  const alias = join(fixture.directory, "official-alias");
  if (!makeLink(t, fixture.root, alias)) return;
  const before = tree(fixture.root);
  adapt({ ...fixture, root: alias });
  assert.equal(verify({ ...fixture, root: alias }).status, 0);
  assert.deepEqual(tree(fixture.root), before);
});

test("npx-style linked individual official directories can be read", (t) => {
  const fixture = makeFixture();
  const original = fixture.root;
  fixture.root = join(fixture.directory, "npx skills");
  mkdirSync(fixture.root);
  for (const name of ALL_OFFICIAL_NAMES) if (!makeLink(t, join(original, name), join(fixture.root, name))) return;
  const before = tree(original);
  adapt(fixture);
  assert.equal(verify(fixture).status, 0);
  assert.deepEqual(tree(original), before);
  fixture.output = join(original, "grilling", "wrappers");
  rejectWithoutWrites(fixture, /path conflict/);
});

test("official SKILL.md can be a readonly file symlink", (t) => {
  const fixture = makeFixture();
  const original = skillPath(fixture.root, "grilling");
  const target = join(fixture.directory, "linked-source", "SKILL.md");
  mkdirSync(join(fixture.directory, "linked-source"));
  renameSync(original, target);
  if (!makeLink(t, target, original, "file")) return;
  const before = readFileSync(target);
  adapt(fixture);
  assert.equal(verify(fixture).status, 0);
  assert.deepEqual(readFileSync(target), before);
  fixture.output = join(fixture.directory, "linked-source", "wrappers");
  rejectWithoutWrites(fixture, /path conflict/);
});

for (const kind of ["root", "ancestor", "wrapper-directory", "wrapper-with-docs", "dangling-root", "dangling-ancestor", "dangling-wrapper", "dangling-wrapper-with-docs"]) {
  test(`output directory links/junctions are rejected (${kind})`, (t) => {
    const fixture = makeFixture();
    const target = kind.startsWith("dangling") ? join(fixture.directory, "missing-target") : join(fixture.root, "grilling");
    if (kind.includes("wrapper")) {
      mkdirSync(fixture.output);
      if (!makeLink(t, target, join(fixture.output, kind.endsWith("with-docs") ? "pi-grill-with-docs" : "pi-grill-me"))) return;
    } else {
      const alias = fixture.output;
      if (!makeLink(t, target, alias)) return;
      if (kind.includes("ancestor")) fixture.output = join(alias, "nested", "wrappers");
    }
    rejectWithoutWrites(fixture, /linked output path/);
  });
}

for (const file of [MANIFEST_NAME, PACKAGE_NAME, ...SHIM_NAMES.map((name) => `${name}/SKILL.md`)]) {
  for (const dangling of [false, true]) test(`output ${dangling ? "dangling " : ""}file symlink is rejected: ${file}`, (t) => {
    const fixture = makeFixture();
    adapt(fixture);
    const path = join(fixture.output, file);
    renameSync(path, join(fixture.directory, "original-output"));
    const target = dangling ? join(fixture.directory, "missing-file") : skillPath(fixture.root, "grilling");
    if (!makeLink(t, target, path, "file")) return;
    rejectWithoutWrites(fixture, /linked output path/);
  });
  test(`hardlinked output ${file} is rejected without altering its peer`, () => {
    const fixture = makeFixture();
    adapt(fixture);
    const path = join(fixture.output, file);
    renameSync(path, join(fixture.directory, "original-output"));
    linkSync(skillPath(fixture.root, "grilling"), path);
    rejectWithoutWrites(fixture, /hardlinked output file/);
  });
}

test("official input hardlinks are read-only and permitted", () => {
  const fixture = makeFixture();
  linkSync(skillPath(fixture.root, "grilling"), join(fixture.directory, "official-hardlink.md"));
  const before = tree(fixture.root);
  adapt(fixture);
  assert.equal(verify(fixture).status, 0);
  assert.deepEqual(tree(fixture.root), before);
});

test("dangling official link fails before any output write", (t) => {
  const fixture = makeFixture({ skip: ["domain-modeling"] });
  if (!makeLink(t, join(fixture.directory, "absent-input"), join(fixture.root, "domain-modeling"))) return;
  rejectWithoutWrites(fixture);
});

test("changed plan input is rejected on recheck before writes", () => {
  const fixture = makeFixture();
  const plan = planInstallation(fixture.root, fixture.output);
  writeFileSync(skillPath(fixture.root, "grilling"), `${fixtures.grilling}\nConcurrent input update\n`);
  const before = tree(fixture.directory);
  assert.throws(() => applyInstallation(plan), /changed during preflight/);
  assert.deepEqual(tree(fixture.directory), before);
});

test("changed plan output is rejected on recheck before writes", () => {
  const fixture = makeFixture();
  adapt(fixture);
  const plan = planInstallation(fixture.root, fixture.output);
  writeFileSync(skillPath(fixture.output, "pi-grill-me"), "User edit after preflight\n");
  const before = tree(fixture.directory);
  assert.throws(() => applyInstallation(plan), /ownership conflict/);
  assert.deepEqual(tree(fixture.directory), before);
});

test("CLI JSON exposes integration paths, drift warnings and validation limits", () => {
  const fixture = makeFixture();
  const result = cli(adaptScript, fixture, ["--json"]);
  assert.equal(result.status, 0, result.stderr + result.stdout);
  const record = JSON.parse(result.stdout);
  assert.equal(record.ok, true);
  assert.equal(record.changed.length, 4);
  assert.deepEqual(record.skillPaths, SHIM_NAMES.map((name) => skillPath(fixture.output, name)));
  assert.equal(record.manifestPath, join(fixture.output, MANIFEST_NAME));
  assert.equal(record.packagePath, join(fixture.output, PACKAGE_NAME));
  assert.equal(record.upstreamAuthentication, "not-performed");
  assert.equal(record.hostValidation, "not-performed");
  const checked = cli(verifyScript, fixture, ["--json"]);
  assert.equal(checked.status, 0);
  assert.equal(JSON.parse(checked.stdout).writePhaseStarted, false);
  assert.equal(result.stderr + checked.stderr, "");
});

test("positional official root remains supported with explicit separate output", () => {
  const fixture = makeFixture();
  const result = run(adaptScript, [fixture.root, "--output-root", fixture.output]);
  assert.equal(result.status, 0, result.stderr);
  assert.equal(verify(fixture).status, 0);
});

test("CLI argument failures are exit 2 and never write or fall back to real profile", () => {
  const fixture = makeFixture();
  for (const script of [adaptScript, verifyScript]) for (const args of [
    [], [fixture.root], ["--skills-root"], ["--output-root"], ["--help", "--json"],
    [fixture.root, "--output-root", fixture.output, "--force"],
    [fixture.root, "--skills-root", fixture.root, "--output-root", fixture.output],
    [fixture.root, "--output-root", fixture.output, "--output-root", fixture.output],
  ]) {
    const before = tree(fixture.directory);
    const result = run(script, [...args, "--json"]);
    assert.equal(result.status, 2, result.stdout + result.stderr);
    assert.equal(JSON.parse(result.stdout).writePhaseStarted, false);
    assert.deepEqual(tree(fixture.directory), before);
  }
});

test("help is read-only and defaults use the real home without reading it", () => {
  assert.equal(defaultSkillsRoot(), join(homedir(), ".agents", "skills"));
  assert.equal(resolveSkillsRoot(), resolve(defaultSkillsRoot()));
  for (const script of [adaptScript, verifyScript]) {
    const result = run(script, ["--help"]);
    assert.equal(result.status, 0);
    assert.match(result.stdout, /--output-root/);
  }
});
