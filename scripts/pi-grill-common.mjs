// Installer-owned Pi wrappers. Official skills are read-only local inputs.
// No network, package manager, profile mutation, or third-party dependency.

import { createHash } from "node:crypto";
import {
  closeSync, constants, fstatSync, fsyncSync, ftruncateSync, lstatSync,
  mkdirSync, openSync, readFileSync, readdirSync, realpathSync, statSync, writeSync,
} from "node:fs";
import { homedir } from "node:os";
import { dirname, isAbsolute, join, parse, relative, resolve, sep } from "node:path";

export const ADAPTER_MARKER = "<!-- pi-adapter:";
export const ADAPTER_NOTE = "<!-- pi-adapter: installer-owned Pi wrapper; official inputs are never modified. -->";
export const SCOPE_NOTE = "scope: official skill files are read-only local inputs; verification checks local hashes, not upstream authenticity or Pi host behavior.";
export const OFFICIAL_NAMES = ["grilling", "domain-modeling"];
export const OFFICIAL_COMPANION_NAMES = ["grill-me", "grill-with-docs"];
export const ALL_OFFICIAL_NAMES = [...OFFICIAL_NAMES, ...OFFICIAL_COMPANION_NAMES];
export const REQUIRED_NAMES = OFFICIAL_NAMES;
export const SHIM_NAMES = ["pi-grill-me", "pi-grill-with-docs"];
export const MANIFEST_NAME = "pi-grilling-manifest.json";
export const PACKAGE_NAME = "package.json";
export const OWNER = "reverse-workflow-installer/pi-grilling";
export const TEMPLATE_VERSION = 2;
const WRAPPER_FILES = SHIM_NAMES.map((name) => `${name}/SKILL.md`);
const ARTIFACT_FILES = [...WRAPPER_FILES, PACKAGE_NAME];
const HASH = /^[a-f0-9]{64}$/;
const NOFOLLOW = constants.O_NOFOLLOW ?? 0;

export const sha256 = (bytes) => createHash("sha256").update(bytes).digest("hex");
export const defaultSkillsRoot = () => join(homedir(), ".agents", "skills");
export const resolveSkillsRoot = (root) => resolve(root ?? defaultSkillsRoot());

function fail(message, warnings = []) { throw Object.assign(new Error(message), { warnings }); }
function maybeStat(path) {
  try { return lstatSync(path); }
  catch (error) { if (error.code === "ENOENT") return null; throw error; }
}
function utf8(bytes) { return new TextDecoder("utf-8", { fatal: true }).decode(bytes); }
function stableValue(value) {
  if (Array.isArray(value)) return value.map(stableValue);
  if (value && typeof value === "object") {
    return Object.fromEntries(Object.keys(value).sort().map((key) => [key, stableValue(value[key])]));
  }
  return value;
}
export const stableJson = (value) => `${JSON.stringify(stableValue(value), null, 2)}\n`;

// Deliberately bounded YAML subset: flat scalar fields and indented |/> blocks.
// Reject unsupported syntax rather than silently accepting a malformed dependency.
function scalar(value) {
  if (value.startsWith('"')) {
    const match = value.match(/^("(?:[^"\\]|\\.)*")(?:\s+#.*)?$/);
    if (!match) fail("invalid quoted scalar");
    return JSON.parse(match[1]);
  }
  if (value.startsWith("'")) {
    const match = value.match(/^'((?:[^']|'')*)'(?:\s+#.*)?$/);
    if (!match) fail("invalid quoted scalar");
    return match[1].replaceAll("''", "'");
  }
  const plain = value.replace(/\s+#.*$/, "").trim();
  if (!plain || /^[\[\]{}&*!|>@`%#?,]/.test(plain) || /:\s/.test(plain)) fail("unsupported scalar");
  if (/^(?:null|~|true|false|[-+]?\d+(?:\.\d+)?)$/i.test(plain)) return null;
  return plain;
}

export function parseSkillDocument(text) {
  if (/[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]/.test(text)) return null;
  const match = text.replace(/^\uFEFF/, "").match(/^---\r?\n([\s\S]*?)\r?\n---[ \t]*\r?\n([\s\S]*)$/);
  if (!match) return null;
  const fields = Object.create(null);
  const lines = match[1].split(/\r?\n/);
  try {
    for (let i = 0; i < lines.length; i++) {
      if (!lines[i].trim() || /^\s*#/.test(lines[i])) continue;
      const entry = lines[i].match(/^([a-z][a-z0-9-]*):[ \t]*(.*)$/);
      if (!entry || Object.hasOwn(fields, entry[1])) return null;
      let value = entry[2].trim();
      if (/^[|>][-+]?(?:\s+#.*)?$/.test(value)) {
        const block = [];
        while (i + 1 < lines.length && (/^ +\S/.test(lines[i + 1]) || !lines[i + 1].trim())) {
          block.push(lines[++i].trim());
        }
        value = block.join(value[0] === ">" ? " " : "\n").trim();
      } else value = scalar(value);
      fields[entry[1]] = value;
    }
  } catch { return null; }
  return { name: fields.name, description: fields.description, body: match[2] };
}

// Unlike existsSync, lstat detects dangling links. Directory nlink is deliberately
// ignored: POSIX directories normally have multiple links.
export function assertPlainPath(path, leafKind = "directory") {
  const absolute = resolve(path);
  const base = parse(absolute).root;
  const parts = relative(base, absolute).split(sep).filter(Boolean);
  if (process.platform === "win32") {
    if (/^\\\\[?.]\\/.test(absolute)) fail(`device namespace output paths are not supported: ${absolute}`);
    for (const part of parts) {
      if (/[<>:"|?*]/.test(part) || /[ .]$/.test(part) || /^(?:con|prn|aux|nul|com[1-9¹²³]|lpt[1-9¹²³])(?: *\.| *$)/i.test(part)) {
        fail(`ambiguous or reserved Windows output path component: ${part}`);
      }
    }
  }
  let cursor = base;
  for (let i = -1; i < parts.length; i++) {
    if (i >= 0) cursor = join(cursor, parts[i]);
    const st = maybeStat(cursor);
    if (!st) continue;
    const kind = i === parts.length - 1 ? leafKind : "directory";
    if (st.isSymbolicLink()) fail(`linked output path is not allowed: ${cursor}`);
    if (kind === "directory" ? !st.isDirectory() : !st.isFile()) fail(`output path must be a ${kind}: ${cursor}`);
    if (st.isFile() && st.nlink !== 1) fail(`hardlinked output file is not allowed: ${cursor}`);
  }
}

function projectedRealPath(path) {
  let ancestor = path;
  const tail = [];
  while (!maybeStat(ancestor)) {
    tail.unshift(parse(ancestor).base);
    const parent = dirname(ancestor);
    if (parent === ancestor) fail(`no existing ancestor for ${path}`);
    ancestor = parent;
  }
  return join(realpathSync(ancestor), ...tail);
}
function contains(parent, child) {
  // Win32 path comparison is case-insensitive; relative also handles drive roots.
  const rel = relative(parent, child);
  return rel === "" || (!isAbsolute(rel) && rel !== ".." && !rel.startsWith(`..${sep}`));
}
function overlaps(a, b) { return contains(a, b) || contains(b, a); }
function codePath(path) {
  const value = sep === "\\" ? path.replaceAll("\\", "/") : path;
  const fence = "`".repeat(Math.max(0, ...[...value.matchAll(/`+/g)].map((m) => m[0].length)) + 1);
  return `${fence} ${value} ${fence}`;
}

export function preflightSkills(root) {
  root = resolveSkillsRoot(root);
  const documents = new Map();
  const inputs = [];
  const protectedPaths = [root];
  const problems = [];
  const warnings = [];
  let realRoot;
  try {
    if (!statSync(root).isDirectory()) fail(`official skills root must be a directory: ${root}`);
    realRoot = realpathSync(root);
    protectedPaths.push(realRoot);
  } catch (error) { problems.push(`unreadable official skills root: ${root} (${error.message})`); }

  if (!problems.length) for (const name of ALL_OFFICIAL_NAMES) {
    const directory = join(root, name);
    const path = join(directory, "SKILL.md");
    const required = OFFICIAL_NAMES.includes(name);
    protectedPaths.push(directory);
    try {
      const dirStat = maybeStat(directory);
      if (dirStat) {
        if (!statSync(directory).isDirectory()) fail("skill directory is not a directory");
        protectedPaths.push(realpathSync(directory));
      }
      const entry = maybeStat(path);
      if (!entry) {
        if (required || dirStat) fail(`missing official ${required ? "dependency" : "companion"} ${name}: ${path}`);
        inputs.push({ name, required, path, realPath: null, sha256: null, legacyAdapterMarker: false });
        continue;
      }
      const realPath = realpathSync(path); // Read-only symlinked npx installations are valid.
      protectedPaths.push(realPath, dirname(realPath));
      if (!statSync(realPath).isFile()) fail("SKILL.md is not a regular file");
      // O_NONBLOCK also prevents a raced FIFO replacement from blocking on POSIX.
      const fd = openSync(realPath, constants.O_RDONLY | NOFOLLOW | (constants.O_NONBLOCK ?? 0));
      let bytes;
      try {
        if (!fstatSync(fd).isFile()) fail("SKILL.md is not a regular file");
        bytes = readFileSync(fd);
      } finally { closeSync(fd); }
      const text = utf8(bytes);
      const document = parseSkillDocument(text);
      if (!document || document.name !== name || typeof document.description !== "string" ||
          !document.description.trim() || document.description.length > 1024 || !document.body.trim()) {
        fail(`malformed ${name}: expected matching name, nonempty description/body and supported YAML frontmatter`);
      }
      const legacyAdapterMarker = text.includes(ADAPTER_MARKER);
      if (legacyAdapterMarker && required) fail(`official dependency has legacy adapter drift: ${name}`);
      if (legacyAdapterMarker) warnings.push(`legacy drift: official companion ${name} carries a pi-adapter marker; left untouched and not loaded by these wrappers`);
      inputs.push({ name, required, path, realPath, sha256: sha256(bytes), legacyAdapterMarker });
      documents.set(name, text);
    } catch (error) { problems.push(`${name}: ${error.message}`); }
  }
  return { ok: problems.length === 0, root, realRoot, documents, inputs, protectedPaths, problems, warnings };
}

export function expectedShimText(_originalText, name, root, inputs = []) {
  if (!SHIM_NAMES.includes(name)) fail(`unknown Pi wrapper: ${name}`);
  const names = name === "pi-grill-me" ? ["grilling"] : OFFICIAL_NAMES;
  const description = name === "pi-grill-me"
    ? "Interview a plan or decision using the locally installed official grilling skill. Use when the user requests a grilling interview."
    : "Interview a plan using the locally installed official grilling and domain-modeling skills. Use when the user requests an interview with glossary and ADR work.";
  const references = names.map((dependency, index) => {
    const input = inputs.find((item) => item.name === dependency);
    return `${index + 1}. Read ${codePath(join(root, dependency, "SKILL.md"))} (${dependency}).` +
      (input ? `\n   Local input SHA-256: ${input.sha256}.` : "");
  }).join("\n");
  return `---\nname: ${name}\ndescription: ${description}\n---\n\n${ADAPTER_NOTE}\n\n` +
    `Load the following official skill ${names.length === 1 ? "body" : "bodies"} from these absolute paths before starting:\n\n${references}\n\n` +
    "Follow the loaded instructions together with the user's request and applicable higher-priority instructions. " +
    "Do not summarize the skill bodies back to the user; start the requested interview.\n" +
    (names.length === 2 ? "Apply domain-modeling's own rules for glossary entries and ADRs; they have different creation thresholds.\n" : "") +
    "\nThese references and hashes describe observed local inputs. They do not authenticate upstream content. " +
    "The official grill-me and grill-with-docs companions are not loaded by this wrapper.\n";
}

export function expectedPackageText() {
  return stableJson({
    name: "@reverse-workflow-installer/pi-grilling-wrappers",
    version: "0.1.0",
    private: true,
    description: "Installer-owned Pi wrappers for locally installed grilling skills.",
    keywords: ["pi-package"],
    pi: {
      skills: WRAPPER_FILES.map((file) => `./${file}`),
      extensions: [], prompts: [], themes: [],
    },
  });
}

function sealManifest(payload) { return { ...payload, sha256: sha256(stableJson(payload)) }; }
function exactKeys(value, keys) {
  return value && typeof value === "object" && !Array.isArray(value) &&
    Object.keys(value).sort().join("\0") === [...keys].sort().join("\0");
}
function readManifest(bytes, root, outputRoot) {
  let manifest;
  try { manifest = JSON.parse(utf8(bytes)); } catch { fail("ownership conflict: malformed manifest"); }
  if (!exactKeys(manifest, ["schemaVersion", "owner", "generator", "templateVersion", "officialRoot", "realOfficialRoot", "outputRoot", "provenance", "officialInputs", "files", "sha256"])) {
    fail("ownership conflict: unsupported manifest shape");
  }
  const { sha256: digest, ...payload } = manifest;
  const ownedFiles = manifest.templateVersion === 1 ? WRAPPER_FILES : ARTIFACT_FILES;
  if (digest !== sha256(stableJson(payload)) || !bytes.equals(Buffer.from(stableJson(manifest)))) {
    fail("ownership conflict: manifest hash or canonical bytes changed");
  }
  if (manifest.schemaVersion !== 1 || manifest.owner !== OWNER || manifest.generator !== "pi-adapt-grill-skills.mjs" ||
      !Number.isInteger(manifest.templateVersion) || manifest.templateVersion < 1 || manifest.templateVersion > TEMPLATE_VERSION ||
      manifest.officialRoot !== root || manifest.outputRoot !== outputRoot || typeof manifest.realOfficialRoot !== "string" ||
      manifest.provenance !== "observed-local-files; upstream-authentication-not-performed" ||
      !exactKeys(manifest.files, ownedFiles) || !Object.values(manifest.files).every((hash) => typeof hash === "string" && HASH.test(hash)) ||
      !Array.isArray(manifest.officialInputs) || manifest.officialInputs.length !== ALL_OFFICIAL_NAMES.length) {
    fail("ownership conflict: manifest identity, paths or hashes do not match this installation");
  }
  for (const [i, input] of manifest.officialInputs.entries()) {
    const name = ALL_OFFICIAL_NAMES[i];
    if (!exactKeys(input, ["name", "required", "path", "realPath", "sha256", "legacyAdapterMarker"]) ||
        input.name !== name || input.required !== OFFICIAL_NAMES.includes(name) || input.path !== join(root, name, "SKILL.md") ||
        typeof input.legacyAdapterMarker !== "boolean" ||
        !(typeof input.sha256 === "string" && HASH.test(input.sha256) && typeof input.realPath === "string" ||
          !input.required && input.sha256 === null && input.realPath === null && !input.legacyAdapterMarker)) {
      fail("ownership conflict: malformed input provenance");
    }
  }
  return manifest;
}

function inspectOutput(root, outputRoot, source) {
  assertPlainPath(outputRoot);
  const realOutput = projectedRealPath(outputRoot);
  for (const protectedPath of source.protectedPaths) {
    if (overlaps(outputRoot, protectedPath) || overlaps(realOutput, protectedPath)) {
      fail(`path conflict: output root overlaps official inputs: ${protectedPath}`);
    }
  }
  const current = new Map();
  const rootStat = maybeStat(outputRoot);
  if (!rootStat) return { realOutput, current, manifest: null };
  const entries = readdirSync(outputRoot).sort();
  const allowed = [...SHIM_NAMES, PACKAGE_NAME, MANIFEST_NAME];
  if (entries.some((entry) => !allowed.includes(entry))) fail("ownership conflict: unexpected entry in output root");
  for (const file of [MANIFEST_NAME, ...ARTIFACT_FILES]) {
    assertPlainPath(join(outputRoot, file), "file");
  }
  if (!maybeStat(join(outputRoot, MANIFEST_NAME))) {
    if (entries.length) fail("ownership conflict: existing output has no manifest; legacy marker alone does not establish ownership");
    return { realOutput, current, manifest: null };
  }
  const manifestBytes = readFileSync(join(outputRoot, MANIFEST_NAME));
  const manifest = readManifest(manifestBytes, root, realOutput);
  current.set(MANIFEST_NAME, manifestBytes);
  for (const file of ARTIFACT_FILES) {
    if (!Object.hasOwn(manifest.files, file)) {
      if (maybeStat(join(outputRoot, file))) fail(`ownership conflict: existing file is not owned by the previous manifest: ${file}`);
      continue; // Version 1 had no package.json; only an absent file may be added.
    }
    if (WRAPPER_FILES.includes(file)) {
      const directory = dirname(join(outputRoot, file));
      if (!maybeStat(directory) || readdirSync(directory).join("\0") !== "SKILL.md") fail(`ownership conflict: missing or unexpected wrapper files: ${file}`);
    }
    if (!maybeStat(join(outputRoot, file))) fail(`ownership conflict: missing managed file: ${file}`);
    const bytes = readFileSync(join(outputRoot, file));
    if (sha256(bytes) !== manifest.files[file]) fail(`ownership conflict: ${file === PACKAGE_NAME ? "package" : "wrapper"} hash changed (user edit): ${file}`);
    // Versions 1 and 2 share the wrapper renderer; version 2 adds the package.
    // Preserve historical renderers if a later version changes generated text.
    const knownText = file === PACKAGE_NAME ? expectedPackageText() :
      expectedShimText(null, file.split("/")[0], root, manifest.officialInputs);
    if (!bytes.equals(Buffer.from(knownText))) fail(`ownership conflict: manifest does not describe a known generated file: ${file}`);
    current.set(file, bytes);
  }
  return { realOutput, current, manifest };
}

export function planInstallation(root, outputRoot) {
  if (!outputRoot) fail("--output-root is required; choose a separate installer-owned directory");
  root = resolveSkillsRoot(root);
  outputRoot = resolve(outputRoot);
  if (/[\x00-\x1f\x7f]/.test(root + outputRoot)) fail("control characters are not allowed in roots");
  const source = preflightSkills(root);
  if (!source.ok) fail(source.problems.join("\n"), source.warnings);
  let output;
  try { output = inspectOutput(root, outputRoot, source); }
  catch (error) { error.warnings = source.warnings; throw error; }
  const next = new Map(SHIM_NAMES.map((name) => [
    `${name}/SKILL.md`, Buffer.from(expectedShimText(null, name, root, source.inputs)),
  ]));
  next.set(PACKAGE_NAME, Buffer.from(expectedPackageText()));
  const manifest = sealManifest({
    schemaVersion: 1, owner: OWNER, generator: "pi-adapt-grill-skills.mjs", templateVersion: TEMPLATE_VERSION,
    officialRoot: root, realOfficialRoot: source.realRoot, outputRoot: output.realOutput,
    provenance: "observed-local-files; upstream-authentication-not-performed",
    officialInputs: source.inputs,
    files: Object.fromEntries([...next].map(([file, bytes]) => [file, sha256(bytes)])),
  });
  next.set(MANIFEST_NAME, Buffer.from(stableJson(manifest)));
  const changed = [...next.keys()].filter((file) => !next.get(file).equals(output.current.get(file) ?? Buffer.alloc(0)));
  return { root, outputRoot, source, current: output.current, next, changed, manifest };
}

// Preflight is complete before mkdir/open-for-write. Existing files are opened
// without truncation, checked through the descriptor, then written. No force mode.
// This is not a multi-file transaction; callers must serialize writers and avoid
// concurrent directory/link replacement. See the guide for I/O failure recovery.
export function applyInstallation(plan, onWritePhase = () => {}) {
  const fresh = planInstallation(plan.root, plan.outputRoot);
  for (const file of [MANIFEST_NAME, ...ARTIFACT_FILES]) {
    if (!(plan.current.get(file) ?? Buffer.alloc(0)).equals(fresh.current.get(file) ?? Buffer.alloc(0)) ||
        !plan.next.get(file).equals(fresh.next.get(file))) fail("inputs or output changed during preflight; retry after resolving the concurrent change");
  }
  if (!fresh.changed.length) return;
  onWritePhase();
  assertPlainPath(fresh.outputRoot);
  mkdirSync(fresh.outputRoot, { recursive: true });
  for (const name of SHIM_NAMES) {
    const directory = join(fresh.outputRoot, name);
    assertPlainPath(directory);
    mkdirSync(directory, { recursive: true });
  }
  // Manifest is last, so an interrupted update cannot attest to incomplete bytes.
  for (const file of fresh.changed) {
    const path = join(fresh.outputRoot, file);
    assertPlainPath(path, "file");
    const original = fresh.current.get(file);
    const fd = openSync(path, NOFOLLOW | (original ? constants.O_RDWR : constants.O_WRONLY | constants.O_CREAT | constants.O_EXCL), 0o600);
    try {
      const st = fstatSync(fd);
      if (!st.isFile() || st.nlink !== 1) fail(`unsafe output descriptor: ${path}`);
      if (original && !readFileSync(fd).equals(original)) fail(`ownership conflict: output changed before write: ${path}`);
      assertPlainPath(path, "file");
      const next = fresh.next.get(file);
      let offset = 0;
      while (offset < next.length) {
        const count = writeSync(fd, next, offset, next.length - offset, offset);
        if (!count) fail(`short write: ${path}`);
        offset += count;
      }
      ftruncateSync(fd, next.length);
      fsyncSync(fd);
    } finally { closeSync(fd); }
  }
}

export function verifySkills(root, outputRoot) {
  try {
    const plan = planInstallation(root, outputRoot);
    const failures = plan.changed.map((file) => `local hash/provenance or template mismatch: ${file}; regenerate only after reviewing input changes`);
    return { ok: !failures.length, failures, warnings: plan.source.warnings };
  } catch (error) { return { ok: false, failures: [error.message], warnings: error.warnings ?? [] }; }
}

export const CLI_USAGE = `Usage: node scripts/<pi-adapt-grill-skills|verify-pi-grill-skills>.mjs\n  [officialSkillsRoot | --skills-root <path>] --output-root <separate-owned-directory> [--json]\n\nThe input defaults to ~/.agents/skills. Output is always explicit and separate.\nExit codes: 0 success; 1 input/path/ownership/verification/I/O failure; 2 invalid arguments.\nNo official files or host settings are written. ${SCOPE_NOTE}`;

export function parseCli(argv) {
  let skillsRoot, outputRoot;
  let json = false;
  for (let i = 0; i < argv.length; i++) {
    const arg = argv[i];
    if (arg === "--help" && argv.length === 1) return { help: true };
    if (arg === "--json" && !json) { json = true; continue; }
    if (["--skills-root", "--output-root"].includes(arg)) {
      const value = argv[++i];
      if (!value || value.startsWith("--")) fail(`missing value for ${arg}`);
      if (arg === "--skills-root" && skillsRoot === undefined) skillsRoot = value;
      else if (arg === "--output-root" && outputRoot === undefined) outputRoot = value;
      else fail(`duplicate argument: ${arg}`);
    } else if (!arg.startsWith("-") && skillsRoot === undefined) skillsRoot = arg;
    else fail(`unknown or duplicate argument: ${arg}`);
  }
  if (!outputRoot) fail("--output-root is required; implicit writes beside official skills are no longer supported");
  return { skillsRoot: resolveSkillsRoot(skillsRoot), outputRoot: resolve(outputRoot), json };
}

export function runCli(mode, argv = process.argv.slice(2)) {
  let options;
  try { options = parseCli(argv); }
  catch (error) {
    if (argv.includes("--json")) console.log(JSON.stringify({ ok: false, mode, failures: [error.message], warnings: [], writePhaseStarted: false }));
    else console.error(`${error.message}\n${CLI_USAGE}`);
    process.exitCode = 2;
    return;
  }
  if (options.help) { console.log(CLI_USAGE); return; }
  const result = {
    ok: false, mode, officialRoot: options.skillsRoot, outputRoot: options.outputRoot,
    manifestPath: join(options.outputRoot, MANIFEST_NAME),
    packagePath: join(options.outputRoot, PACKAGE_NAME),
    skillPaths: SHIM_NAMES.map((name) => join(options.outputRoot, name, "SKILL.md")),
    changed: [], warnings: [], failures: [], writePhaseStarted: false,
    upstreamAuthentication: "not-performed", hostValidation: "not-performed",
  };
  try {
    const plan = planInstallation(options.skillsRoot, options.outputRoot);
    result.warnings = plan.source.warnings;
    result.changed = plan.changed;
    if (mode === "verify" && plan.changed.length) fail(`local hash/provenance or template mismatch: ${plan.changed.join(", ")}`);
    if (mode === "adapt") applyInstallation(plan, () => { result.writePhaseStarted = true; });
    result.ok = true;
  } catch (error) {
    result.failures.push(error.message);
    if (error.warnings?.length) result.warnings = error.warnings;
    process.exitCode = 1;
  }
  if (options.json) console.log(JSON.stringify(result));
  else {
    for (const warning of result.warnings) console.error(`warning: ${warning}`);
    if (result.ok) console.log(mode === "verify" ? `Pi grilling local hashes and structure verified: ${options.outputRoot}` :
      result.changed.length ? `Generated/updated ${result.changed.length} installer-owned files: ${options.outputRoot}` : "already generated; nothing to do");
    else {
      console.error(result.writePhaseStarted ? "Pi grilling write phase failed; output may be incomplete:" : "Pi grilling check failed; no files were written:");
      for (const failure of result.failures) console.error(`- ${failure}`);
    }
    console.log(SCOPE_NOTE);
  }
}
