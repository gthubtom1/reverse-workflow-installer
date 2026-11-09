"""Reproducible Craft/Pi packaging. Never installs system tools or calls a model.

Only Windows x86_64 GNU is admitted. `freeze` is an explicit integration step,
not permission to snapshot a worker that is still editing its source.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import zipfile
from urllib.parse import urlparse
from urllib.request import Request, urlopen

import craft
from configuration import encode_json, load_json
from versions import InstallError
from packaging_process import run_owned

BASE = craft.BASE_COMMIT
UPSTREAM = "https://github.com/storytold/craft-anything"
TARGET = "x86_64-pc-windows-gnu"
RUST_VERSION = "1.99.0"
PI_PACKAGE = "@earendil-works/pi-coding-agent"
PI_VERSION = "1.5.0"
NODE_VERSION = "v24.20.0"
RUNTIME = Path(__file__).resolve().parents[1] / "adapters/craft-pi/runtime"
SOURCE_DIRS = {"craft-pi-bridge": "bridge", "craft-pi-executor": "executor"}
DENIED = {"auth.json", "mcp.json", "settings.json", "credentials.json", ".env", "backups", ".npmrc"}
SYSTEM_DLLS = {x.casefold() for x in (
    "kernel32.dll", "ntdll.dll", "user32.dll", "advapi32.dll", "bcrypt.dll", "bcryptprimitives.dll",
    "crypt32.dll", "cryptbase.dll", "cryptnet.dll", "secur32.dll", "sspicli.dll", "ws2_32.dll",
    "iphlpapi.dll", "dnsapi.dll", "nsi.dll", "msvcrt.dll", "ucrtbase.dll", "shell32.dll", "shlwapi.dll",
    "ole32.dll", "oleaut32.dll", "combase.dll", "uuid.dll", "userenv.dll", "version.dll", "winmm.dll",
    "winhttp.dll", "wininet.dll", "normaliz.dll", "dbghelp.dll", "psapi.dll", "gdi32.dll", "gdi32full.dll",
    "dwmapi.dll", "uxtheme.dll", "comctl32.dll", "setupapi.dll", "cfgmgr32.dll", "powrprof.dll",
    "wtsapi32.dll", "propsys.dll", "windowscodecs.dll", "winspool.drv", "hid.dll", "imm32.dll", "d3d11.dll", "rpcrt4.dll",
)}


def fail(message):
    raise InstallError(message)


def sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(encode_json(value))


def tree(root):
    return craft.inventory(root, forbidden=DENIED)


def check_files(root, expected):
    if not expected or tree(root) != expected:
        fail("exact source/file manifest drift: missing, empty, added or changed inputs")


def fresh(path):
    path = craft.no_links(Path(path).absolute())
    if path.exists():
        fail("staging/output must not exist: " + str(path))
    path.mkdir(parents=True)
    return path


def copy_file(source, target):
    craft.no_links(source)
    craft.no_links(target)
    if Path(source).absolute() == Path(target).absolute():
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)


def command(argv, *, cwd, env=None, timeout=1800, log_prefix=None):
    result = run_owned(argv, cwd=cwd, env=env, timeout=timeout, log_prefix=log_prefix)
    if result['cleanup'] != 'verified' or result['timed_out'] or result['had_descendants']:
        fail(f"command lifecycle blocked: timeout={result['timed_out']}; cleanup={result['cleanup']}; scope={result['scope']}")
    if result['returncode']:
        fail(f"command failed ({result['returncode']}): {Path(argv[0]).name}: {result['stderr'][-6000:]}")
    return result['stdout'].strip()


def isolated_env():
    # Do not pass provider credentials, npm hooks/config, RUSTFLAGS or Node injection.
    names = ("PATH", "SYSTEMROOT", "WINDIR", "COMSPEC", "TEMP", "TMP", "PATHEXT", "NUMBER_OF_PROCESSORS")
    return {k: v for k, v in os.environ.items() if k.upper() in names}


def executable(path):
    p = craft.no_links(Path(path).absolute())
    if not p.is_file() or not p.stat().st_size:
        fail("explicit tool missing: " + str(p))
    return p


def snapshot_bridge(source, manifest_path, expected_tree, destination=None):
    from craft_sources import snapshot
    return snapshot(source, manifest_path, expected_tree, 'bridge', destination or RUNTIME / 'bridge')


def snapshot_executor(source, manifest_path, expected_tree, destination=None):
    from craft_sources import snapshot
    return snapshot(source, manifest_path, expected_tree, 'executor', destination or RUNTIME / 'executor')


def snapshot_policy(series_path, source_identity_path, stage, mirror, destination=None, *, expected_series_sha256):
    series_path = executable(series_path)
    identity_path = executable(source_identity_path)
    original_sha = sha(series_path)
    if original_sha != expected_series_sha256:
        fail('explicit approved policy series SHA256 mismatch')
    series = load_json(series_path)
    identity = load_json(identity_path)
    if identity.get("series_sha256") != original_sha or identity.get("source") != series or series.get("base_commit") != BASE:
        fail("policy series/source identity mismatch")
    patches = series.get("series", [])
    inventory = series.get("source_inventory", [])
    if not patches or not inventory or len({p["file"] for p in patches}) != len(patches) or len({p["path"] for p in inventory}) != len(inventory):
        fail("policy patch/source inventory empty or duplicate")
    stage = fresh(stage)
    clone = stage / "upstream"
    clone_base(clone, mirror)
    if git_command(["git", "rev-parse", "HEAD^{tree}"], cwd=clone) != series.get("base_tree"):
        fail("policy base tree mismatch")
    original_toml = sha(clone / "Cargo.toml")
    records = []
    for patch in patches:
        name = craft.relative(patch["file"])
        if "/" in name or sha(series_path.parent / name) != patch["sha256"]:
            fail("policy patch identity mismatch")
        records.append({"path": name, "sha256": patch["sha256"]})
    apply_patches(clone, series_path.parent, records)
    for item in inventory:
        rel = craft.relative(item["path"])
        if sha(clone / rel) != item["sha256"]:
            fail("policy applied source hash mismatch: " + rel)
    if sha(clone / "Cargo.lock") != series.get("lock_sha256") or series.get("lock_sha256") != series.get("upstream_lock_sha256") or sha(clone / "Cargo.toml") != original_toml:
        fail("policy Cargo.lock/Cargo.toml changed")
    if sha(series_path) != original_sha or load_json(identity_path) != identity:
        fail("policy freeze changed during replay")
    destination = fresh(destination or RUNTIME / "patches")
    for p in records:
        copy_file(series_path.parent / p["path"], destination / p["path"])
        if sha(destination / p["path"]) != p["sha256"]:
            fail("copied policy patch drift")
    # Original series contains a developer replay path. Preserve its digest in
    # portable provenance, and keep the original only in the local replay stage.
    copy_file(series_path, stage / "original-series.json")
    portable = {k: series[k] for k in ("version", "upstream", "base_commit", "base_tree", "lock_sha256", "upstream_lock_sha256", "series", "source_inventory")}
    portable["origin"] = {"original_series_sha256": original_sha, "source_identity_sha256": sha(identity_path),
                          "transformation": "omitted local replay path/log inventory; patches and source hashes unchanged"}
    write_json(destination / "series.json", portable)
    result = {"base_commit": BASE, "patches": len(records), "matching_source_files": len(inventory), "cargo_lock_unchanged": True,
              "cargo_toml_unchanged": True, "original_series_sha256": original_sha, "portable_series_sha256": sha(destination / "series.json"),
              "files": tree(destination), "qualification": "patch replay only; independent re-review and full executor/driver freeze pending"}
    write_json(stage / "replay-result.json", result)
    return result


def validate_bridge_snapshot(root):
    from craft_sources import validate
    return validate(root, 'bridge')


def recipe_identity():
    root = Path(__file__).resolve().parent
    return {name: sha(root / name) for name in ('build_craft_bundle.py', 'craft_sources.py', 'craft_cargo_notices.py', 'test_craft_owned.py', 'packaging_process.py', 'craft.py', 'configuration.py', 'versions.py')}


def approved_series(path, expected_sha):
    path = executable(path)
    if not re.fullmatch(r'[0-9a-f]{64}', str(expected_sha)) or sha(path) != expected_sha:
        fail('approved policy series SHA256 mismatch')
    value = load_json(path)
    if value.get('base_commit') != BASE or not isinstance(value.get('series'), list) or not value['series']:
        fail('approved policy series/base missing')
    records = []
    seen = set()
    for item in value['series']:
        name = craft.relative(item['file'])
        if '/' in name or not name.endswith('.patch') or name in seen or sha(path.parent / name) != item['sha256']:
            fail('approved policy patch hash/path mismatch')
        seen.add(name)
        records.append({'path': 'patches/' + name, 'sha256': item['sha256']})
    if set(tree(path.parent)) != seen | {path.name}:
        fail('approved series directory has unlisted files')
    return records


def owned_inventory(root, name):
    root = Path(root)
    if (root / 'packaged-source-manifest.json').is_file():
        from craft_sources import validate
        validate(root, 'bridge' if name == 'craft-pi-bridge' else 'executor')
        return tree(root)
    selected = {p: sha(root / p) for p in ('Cargo.toml', 'Cargo.lock')}
    for folder in ('src', 'tests', 'examples'):
        if (root / folder).is_dir():
            selected.update({folder + '/' + p: h for p, h in tree(root / folder).items()})
    for p in ('build.rs', '.gitignore', 'README.md', 'config.example.json', 'entry-protocol.json', 'LICENSE-MIT', 'ATTRIBUTION.md', 'THIRD_PARTY_NOTICES.md'):
        if (root / p).is_file():
            selected[p] = sha(root / p)
    return selected


def execution_resources():
    repo = Path(__file__).resolve().parents[1]
    adapter = repo / 'adapters/craft-pi'
    data = {p: (adapter / p).read_bytes() for p in tree(adapter) if not p.startswith('runtime/')}
    for name in ('craft.py', 'configuration.py', 'versions.py'):
        data['lib/' + name] = (repo / 'scripts' / name).read_bytes()
    return data


def freeze(bridge, executor, patches, notices, protocol, destination=RUNTIME, *, series_path=None, series_sha256=None):
    """Copy only after the lead has frozen sources. No live worktree is changed.

    Relative Cargo dependencies are retained by the canonical sibling mapping.
    Test/fixture/development sources remain owned inputs; production builds name exact bins.
    """
    destination = Path(destination)
    series_path = executable(series_path) if series_path else None
    if series_path is None:
        fail('explicit approved policy series and SHA256 required')
    patch_records = approved_series(series_path, series_sha256)
    if [Path(p).absolute() for p in patches] != [series_path.parent / Path(p['path']).name for p in patch_records]:
        fail('patch arguments must match approved series order exactly')
    if destination.exists() and any(destination.glob("source-manifest.json")):
        fail("canonical snapshot already exists; review replacement explicitly")
    sources = {}
    for name, raw in (("craft-pi-bridge", bridge), ("craft-pi-executor", executor)):
        root = craft.no_links(Path(raw).absolute())
        identities = owned_inventory(root, name)
        if not identities or not any(n.endswith(".rs") for n in identities):
            fail("owned Rust source is empty")
        sources[name] = (root, identities)
    patch_inputs = [(executable(p), sha(p)) for p in patches]
    if not patch_inputs:
        fail("ordered complete policy patches required")
    notice_root = craft.no_links(Path(notices).absolute())
    notice_files = tree(notice_root)
    if not notice_files or "THIRD_PARTY_NOTICES.md" not in notice_files:
        fail("reviewed license/notices tree with THIRD_PARTY_NOTICES.md required")
    protocol = executable(protocol)
    protocol_sha = sha(protocol)
    # Hash selected inputs twice around copying. Never certify a moving worker tree.
    destination.mkdir(parents=True, exist_ok=True)
    if (destination / 'patches').exists():
        if tree(destination / 'patches') != tree(series_path.parent):
            fail('existing policy snapshot differs from explicitly approved series')
    for name, (root, identities) in sources.items():
        target = destination / SOURCE_DIRS[name]
        if root.resolve() == target.resolve():
            continue
        if target.exists():
            fail("canonical source directory already exists: " + SOURCE_DIRS[name])
        for rel in identities:
            copy_file(root / rel, target / rel)
    for record, (path, digest) in zip(patch_records, patch_inputs):
        if digest != record['sha256']:
            fail('approved policy patch changed before copy')
        target = destination / record['path']
        if path.resolve() != target.resolve():
            copy_file(path, target)
    target_series = destination / 'patches/series.json'
    if series_path.resolve() != target_series.resolve():
        copy_file(series_path, target_series)
    for rel in notice_files:
        copy_file(notice_root / rel, destination / "notices" / rel)
    copy_file(protocol, destination / "entry-protocol.md")
    resources = execution_resources()
    for rel, content in resources.items():
        target = destination / 'resources' / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
    if execution_resources() != resources:
        fail('execution resource source changed during freeze')
    for name, (root, identities) in sources.items():
        current = owned_inventory(root, name)
        if current != identities:
            fail("source changed while freezing: " + name)
        copied = tree(destination / SOURCE_DIRS[name])
        if copied != identities:
            fail("copied source differs from frozen input: " + name)
    if tree(notice_root) != notice_files or sha(protocol) != protocol_sha or any(sha(p) != h for p, h in patch_inputs):
        fail("patch/protocol/notices changed while freezing")
    for rel, digest in notice_files.items():
        if sha(destination / "notices" / rel) != digest:
            fail("copied notice differs from input")
    if sha(destination / "entry-protocol.md") != protocol_sha or any(sha(destination / p["path"]) != p["sha256"] for p in patch_records):
        fail("copied patch/protocol differs from input")
    if sha(series_path) != series_sha256 or approved_series(target_series, series_sha256) != patch_records:
        fail('approved policy series changed during freeze')
    inputs = {}
    for folder in ("bridge", "executor", "patches", "notices", "resources"):
        inputs.update({folder + "/" + k: v for k, v in tree(destination / folder).items()})
    inputs["entry-protocol.md"] = protocol_sha
    value = {"schema_version": 1, "upstream": UPSTREAM, "base_commit": BASE,
             "target": TARGET, "rust_version": RUST_VERSION, "pi_version": PI_VERSION,
             "recipe_sha256": sha(__file__), "recipe_files": recipe_identity(),
             "patch_series": {"path": "patches/series.json", "sha256": series_sha256},
             "resource_sha256": hashlib.sha256(encode_json({p: h for p, h in sorted(inputs.items()) if p.startswith('resources/')})).hexdigest(),
             "mapping": {**SOURCE_DIRS, "craft-anything-adapted": "upstream-clone-and-ordered-patches"},
             "patches": patch_records, "files": dict(sorted(inputs.items()))}
    write_json(destination / "source-manifest.json", value)
    return value


def source_identity(runtime):
    runtime = craft.no_links(Path(runtime).absolute())
    value = load_json(runtime / "source-manifest.json")
    if not isinstance(value, dict) or value.get("schema_version") != 1:
        fail("frozen canonical source-manifest.json required; awaiting source freeze")
    if (value.get("upstream"), value.get("base_commit"), value.get("target"), value.get("rust_version"), value.get("pi_version")) != (UPSTREAM, BASE, TARGET, RUST_VERSION, PI_VERSION):
        fail("source base/toolchain/target unsupported; update candidate needs compatibility review")
    if value.get("recipe_sha256") != sha(__file__) or value.get('recipe_files') != recipe_identity():
        fail("build recipe changed since source freeze")
    actual = {}
    for folder in ("bridge", "executor", "patches", "notices", "resources"):
        actual.update({folder + "/" + k: v for k, v in tree(runtime / folder).items()})
    actual["entry-protocol.md"] = sha(runtime / "entry-protocol.md")
    if not value.get("files") or actual != value["files"]:
        fail("exact source manifest drift")
    if value.get('resource_sha256') != hashlib.sha256(encode_json({p: h for p, h in sorted(actual.items()) if p.startswith('resources/')})).hexdigest():
        fail('frozen execution resources identity mismatch')
    patches = value.get("patches")
    if not isinstance(patches, list) or not patches:
        fail("nonempty ordered patches required")
    seen = set()
    for patch in patches:
        rel = craft.relative(patch.get("path"))
        if not rel.startswith("patches/") or rel in seen or patch.get("sha256") != actual.get(rel):
            fail("patch reference/hash invalid")
        seen.add(rel)
    series = value.get('patch_series', {})
    if series.get('path') != 'patches/series.json' or approved_series(runtime / 'patches/series.json', series.get('sha256')) != patches:
        fail('frozen approved series/ordered patches changed')
    if seen != {p for p in actual if p.startswith("patches/") and p != 'patches/series.json'}:
        fail("every patch must be applied exactly once")
    expected_mapping = {**SOURCE_DIRS, "craft-anything-adapted": "upstream-clone-and-ordered-patches"}
    if value.get("mapping") != expected_mapping:
        fail("unsupported canonical source mapping")
    # Fixed sibling layout makes every path dependency auditable without rewrites.
    import tomllib
    for name in ("craft-pi-bridge", "craft-pi-executor"):
        root = runtime / SOURCE_DIRS[name]
        if name == "craft-pi-bridge" and (root / "packaged-source-manifest.json").exists():
            validate_bridge_snapshot(root)
        if name == "craft-pi-executor" and (root / "packaged-source-manifest.json").exists():
            from craft_sources import validate
            validate(root, "executor")
        metadata = tomllib.loads((root / "Cargo.toml").read_text(encoding="utf-8"))
        if metadata.get("package", {}).get("name") != name:
            fail("owned package identity mismatch")
        for p in dependency_paths(metadata):
            if p != "../craft-pi-bridge" and not re.fullmatch(r"\.\./craft-anything-adapted/crates/[a-zA-Z0-9_-]+", p):
                fail("Cargo dependency escapes canonical sibling layout")
    return value, sha(runtime / "source-manifest.json")


def assert_unchanged(runtime, frozen):
    if source_identity(runtime) != frozen:
        fail("source changed while build was running; no certified artifact")


def git_command(argv, *, cwd):
    env = isolated_env()
    env.update({"GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1", "GIT_TERMINAL_PROMPT": "0"})
    return command(argv, cwd=cwd, env=env)


def apply_patches(source, runtime, patches, run=git_command):
    if run(["git", "rev-parse", "HEAD"], cwd=source) != BASE:
        fail("patch base incompatible")
    if run(["git", "status", "--porcelain", "--untracked-files=all"], cwd=source):
        fail("upstream staging must be clean before patch application")
    for patch in patches:
        path = Path(runtime).absolute() / craft.relative(patch["path"])
        if sha(path) != patch["sha256"]:
            fail("patch hash drift")
        # --index checks the complete context against the previously applied patch.
        run(["git", "apply", "--check", "--index", str(path)], cwd=source)
        run(["git", "apply", "--index", str(path)], cwd=source)


def dll_imports(binary, objdump, run=command):
    result = run([objdump, "-p", binary], cwd=Path(binary).parent)
    if "pei-x86-64" not in result:
        fail("artifact is not a Windows x86_64 PE binary")
    return sorted(set(re.findall(r"DLL Name:\s*([^\s]+)", result, flags=re.I)), key=str.casefold)


def collect_dlls(binaries, destination, objdump, dll_dirs, run=command):
    queue, report, provided = list(binaries), {}, {}
    for folder in dll_dirs:
        for p in craft.no_links(Path(folder).absolute()).glob("*.dll"):
            craft.no_links(p)
            key = p.name.casefold()
            if key in provided and sha(p) != sha(provided[key]):
                fail("ambiguous runtime DLL: " + p.name)
            provided[key] = p
    while queue:
        binary = queue.pop(0)
        imports = dll_imports(binary, objdump, run)
        report[Path(binary).name] = imports
        for name in imports:
            key = name.casefold()
            if key in SYSTEM_DLLS or re.fullmatch(r"(?:api|ext)-ms-win-[a-z0-9-]+\.dll", key):
                continue
            if key not in provided:
                fail("unresolved non-system DLL: " + name)
            target = Path(destination) / provided[key].name
            if not target.exists():
                copy_file(provided[key], target)
                queue.append(target)
    return report


def clone_base(destination, mirror=None, run=git_command):
    # Ignore user filters/hooks and normalize checkout bytes on every machine.
    if mirror:
        mirror = craft.no_links(Path(mirror).absolute())
    run(["git", "clone", "--config", "core.autocrlf=false", "--config", "core.eol=lf", "--no-checkout", "--no-hardlinks", str(mirror or UPSTREAM), str(destination)], cwd=destination.parent)
    run(["git", "checkout", "--detach", BASE], cwd=destination)
    if run(["git", "rev-parse", "HEAD"], cwd=destination) != BASE:
        fail("upstream exact base missing")


def staged_tree(root):
    """Include new untracked files too; omit only the clone's Git database."""
    found = {}
    for directory, dirs, files in os.walk(root, followlinks=False):
        dirs[:] = [name for name in dirs if name != ".git"]
        for name in dirs + files:
            p = craft.no_links(Path(directory) / name)
            rel = craft.relative(p.relative_to(root).as_posix())
            if p.is_file():
                found[rel] = sha(p)
    return found


def dependency_paths(metadata):
    for key, value in metadata.items():
        if key in ("dependencies", "dev-dependencies", "build-dependencies") and isinstance(value, dict):
            for dependency in value.values():
                if isinstance(dependency, dict) and "path" in dependency:
                    yield dependency["path"]
        elif isinstance(value, dict):
            yield from dependency_paths(value)


def validate_cargo_paths(source):
    import tomllib
    for rel in staged_tree(source):
        if Path(rel).name != "Cargo.toml":
            continue
        path = source / rel
        metadata = tomllib.loads(path.read_text(encoding="utf-8"))
        for dependency in dependency_paths(metadata):
            target = craft.no_links(path.parent / dependency)
            if not target.resolve().is_relative_to(source.resolve()) or not (target / "Cargo.toml").is_file():
                fail("Cargo path dependency missing/outside isolated source: " + rel)


def refresh_cached_policy(upstream, previous_path, previous, runtime, value, history_root, mirror=None):
    """Validate the old patch tree before preserving/replaying a changed series."""
    import time
    if git_command(['git', 'rev-parse', 'HEAD'], cwd=upstream) != BASE:
        fail('incremental upstream base changed')
    previous_series = Path(previous_path).parent / 'patches/series.json'
    if sha(previous_series) != previous['files'].get('patches/series.json'):
        fail('previous approved policy series drift')
    prior = load_json(previous_series)
    previous_inventory = prior['source_inventory']
    staged_diff = set(git_command(['git', 'diff', '--cached', '--name-only'], cwd=upstream).splitlines())
    if staged_diff != {p['path'] for p in previous_inventory} or git_command(['git', 'diff', '--name-only'], cwd=upstream) or git_command(['git', 'ls-files', '--others', '--exclude-standard'], cwd=upstream):
        fail('incremental patched upstream tree drift')
    if any(sha(upstream / craft.relative(item['path'])) != item['sha256'] for item in previous_inventory):
        fail('previous staged policy source hash drift')
    original_cargo_toml = sha(upstream / 'Cargo.toml')
    if sha(upstream / 'Cargo.lock') != prior['lock_sha256']:
        fail('previous staged Cargo.lock drift')
    if previous['patches'] != value['patches']:
        # Keep the cache and old verified source; replay from a fresh exact base.
        history = Path(history_root) / (str(time.time_ns()) + '-craft-anything-adapted')
        history.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(upstream), history)
        clone_base(upstream, mirror or history)
        if sha(upstream / 'Cargo.toml') != original_cargo_toml:
            fail('fresh policy base Cargo.toml differs from prior baseline')
        apply_patches(upstream, runtime, value['patches'])
    return original_cargo_toml


def build(args):
    import time
    build_started = time.monotonic()
    if craft.host() != {"os": "windows", "arch": "x86_64"}:
        fail("unsupported platform: only Windows x86_64 GNU is admitted")
    if not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", args.version):
        fail("exact three-part bundle version required")
    runtime = Path(args.runtime).absolute()
    frozen = source_identity(runtime)
    value, source_sha = frozen
    tools = {key: executable(getattr(args, key)) for key in ("cargo", "rustc", "gcc", "objdump")}
    reuse = getattr(args, 'reuse_stage', False)
    if args.previous_source_manifest and not reuse:
        fail('previous source manifest is only valid for explicit stage reuse')
    if reuse and (not args.previous_source_manifest or not args.previous_source_sha256):
        fail('incremental reuse requires explicit prior manifest path/SHA')
    if reuse:
        stage = craft.no_links(Path(args.stage).absolute())
        previous_path = executable(args.previous_source_manifest)
        if sha(previous_path) != args.previous_source_sha256:
            fail('explicit previous staged source manifest SHA mismatch')
        previous = load_json(previous_path)
        for folder in SOURCE_DIRS:
            prefix = previous['mapping'][folder] + '/'
            expected = {p[len(prefix):]: h for p, h in previous['files'].items() if p.startswith(prefix)}
            if tree(stage / 'source' / folder) != expected:
                fail('previous staged owned source drift; refuse incremental reuse')
    else:
        stage = fresh(args.stage)
    output = craft.no_links(Path(args.output).absolute())
    if output.is_relative_to(stage) or stage.is_relative_to(output) or output.is_relative_to(runtime) or runtime.is_relative_to(output):
        fail("build output must be separate from staging and canonical runtime source")
    if output.exists():
        fail("output already exists")
    env = isolated_env()
    env.update({"CARGO_HOME": str(stage / "cargo-home"), "CARGO_TARGET_DIR": str(stage / "target"),
                "RUSTC": str(tools["rustc"]), "CARGO_BUILD_JOBS": '3', "CARGO_TARGET_X86_64_PC_WINDOWS_GNU_LINKER": str(tools["gcc"]),
                "PATH": str(tools["gcc"].parent) + os.pathsep + env.get("PATH", "")})
    tool_info = {k: {"sha256": sha(p), "version": command([p, "--version"], cwd=stage, env=env)} for k, p in tools.items()}
    rust_verbose = command([tools["rustc"], "-vV"], cwd=stage, env=env)
    if not tool_info["cargo"]["version"].startswith("cargo " + RUST_VERSION + " ") or f"release: {RUST_VERSION}\n" not in rust_verbose or f"host: {TARGET}\n" not in rust_verbose:
        fail("exact Rust/Cargo 1.99.0 GNU toolchain required (no automatic installation)")
    source = stage / "source"
    if not reuse:
        source.mkdir()
    upstream = source / "craft-anything-adapted"
    if not reuse:
        clone_base(upstream, args.upstream_mirror)
        original_cargo_toml = sha(upstream / 'Cargo.toml')
        apply_patches(upstream, runtime, value["patches"])
    else:
        original_cargo_toml = refresh_cached_policy(upstream, previous_path, previous, runtime, value,
                                                    stage / 'source-history', args.upstream_mirror)
    series = load_json(runtime / 'patches/series.json')
    for item in series.get('source_inventory', []):
        if sha(upstream / craft.relative(item['path'])) != item['sha256']:
            fail('fresh applied policy source hash mismatch')
    if series.get('lock_sha256') and (sha(upstream / 'Cargo.lock') != series['lock_sha256'] or sha(upstream / 'Cargo.toml') != original_cargo_toml):
        fail('fresh policy replay changed Cargo baseline')
    upstream_tree = git_command(["git", "write-tree"], cwd=upstream)
    for name in ("craft-pi-bridge", "craft-pi-executor"):
        target = source / name
        if reuse:
            history = stage / 'source-history' / (str(int(time.time())) + '-' + name)
            history.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(target), history)
        shutil.copytree(runtime / SOURCE_DIRS[name], target)
    # Exact pre-build source inventories include Cargo.lock and every untracked/dirty input.
    owned_before = {name: tree(source / name) for name in ("craft-pi-bridge", "craft-pi-executor")}
    for name, copied in owned_before.items():
        prefix = SOURCE_DIRS[name] + "/"
        expected = {p[len(prefix):]: h for p, h in value["files"].items() if p.startswith(prefix)}
        if copied != expected:
            fail("staged source differs from canonical frozen input: " + name)
    upstream_before = staged_tree(upstream)
    validate_cargo_paths(source)
    metadata, compiled = {}, set()
    for name, binary in (("craft-pi-bridge", "pi-rpc-driver"), ("craft-pi-executor", "craft-pi-executor")):
        manifest = source / name / "Cargo.toml"
        cmd = [tools["cargo"], "build", "--locked", "--release", "--message-format=json", "--target", TARGET, "--manifest-path", manifest, "--bin", binary]
        if args.offline:
            cmd.append("--offline")
        output = command(cmd, cwd=source, env=env, log_prefix=stage / 'logs' / binary)
        for line in output.splitlines():
            message = json.loads(line)
            if message.get('reason') == 'compiler-artifact':
                compiled.add(message['package_id'])
        meta_cmd = [tools["cargo"], "metadata", "--locked", "--format-version", "1", "--filter-platform", TARGET, "--manifest-path", manifest]
        if args.offline:
            meta_cmd.append("--offline")
        metadata[name] = json.loads(command(meta_cmd, cwd=source, env=env))
        for pkg in metadata[name]["packages"]:
            if pkg["source"] is None and not Path(pkg["manifest_path"]).resolve().is_relative_to(source.resolve()):
                fail("Cargo metadata resolved a path dependency outside isolated source")
    assert_unchanged(runtime, frozen)
    if any(tree(source / name) != files for name, files in owned_before.items()) or upstream_before != staged_tree(upstream):
        fail("staged source/Cargo.lock changed during build")
    # A failed build leaves diagnostics/staging, but never an eligible craft-bundle.json.
    bundle = stage / "bundle"
    bundle.mkdir()
    for binary in ("craft-pi-executor", "pi-rpc-driver"):
        copy_file(stage / "target" / TARGET / "release" / (binary + ".exe"), bundle / "bin" / (binary + ".exe"))
    imports = collect_dlls(list((bundle / "bin").glob("*.exe")), bundle / "bin", tools["objdump"], args.dll_dir)
    for name in ("LICENSE-MIT", "LICENSE-APACHE", "ATTRIBUTION.md", "NOTICE"):
        copy_file(upstream / name, bundle / name)
    copy_file(upstream / "Cargo.lock", bundle / "source/upstream-Cargo.lock")
    copy_file(source / "craft-pi-executor/Cargo.lock", bundle / "Cargo.lock")
    for rel in tree(runtime / "notices"):
        copy_file(runtime / "notices" / rel, bundle / "licenses/reviewed" / rel)
    copy_file(runtime / "notices/THIRD_PARTY_NOTICES.md", bundle / "THIRD_PARTY_NOTICES.md")
    if not (bundle / "THIRD_PARTY_NOTICES.md").is_file():
        fail("reviewed third party notices missing")
    from craft_cargo_notices import collect
    dependencies = collect(metadata, compiled,
        [source / n / 'Cargo.lock' for n in ('craft-pi-bridge', 'craft-pi-executor')] + [upstream / 'Cargo.lock'],
        bundle / 'licenses/cargo', source,
        supplements=(runtime / 'notices/cargo-originals') if (runtime / 'notices/cargo-originals/source-registry.json').is_file() else None,
        standards=(runtime / 'notices/cargo-standard-0bsd') if (runtime / 'notices/cargo-standard-0bsd/SOURCE.json').is_file() else None,
        allow_missing=getattr(args, 'candidate_allow_missing_notice', False))
    publication_blockers = [key + ': original license grant text missing' for key, record in dependencies.items()
                            if record.get('status', '').startswith('missing-')]
    write_json(bundle / 'licenses/compiled-cargo-inventory.json', dependencies)
    for rel in value["files"]:
        copy_file(runtime / rel, bundle / "source" / rel)
    if any(p.startswith(('node_modules/', 'node/', 'licenses/pi/', 'pi/')) for p in tree(bundle)):
        fail('native Craft artifact must not embed external Pi/Node closure')
    copy_file(runtime / "source-manifest.json", bundle / "source/source-manifest.json")
    for name, expected_sha in value['recipe_files'].items():
        source_script = Path(__file__).resolve().parent / name
        if sha(source_script) != expected_sha:
            fail('packaging recipe changed before retaining build source')
        copy_file(source_script, bundle / 'source/build-tools' / name)
    copy_file(runtime / "entry-protocol.md", bundle / "docs/entry-protocol.md")
    provenance = {"schema_version": 1, "source_manifest_sha256": source_sha, "base_commit": BASE,
                  "patched_git_tree": upstream_tree, "target": TARGET, "toolchain": tool_info,
                  "rustc_verbose": rust_verbose, "dll_imports": imports, "dependencies": dependencies,
                  "build_mode": "release --locked; fixtures disabled; no model calls",
                  "qualification": "candidate baseline packaging only; known runtime issue may remain; provider/business acceptance separate",
                  "external_pi": "complete official dependency acquired separately; Pi/Node not included",
                  "compiled_package_count": len(compiled), "publication_blockers": publication_blockers, "incremental_cache_reused": reuse,
                  "previous_source_manifest_sha256": args.previous_source_sha256 if reuse else None,
                  "build_seconds": time.monotonic() - build_started}
    write_json(bundle / "build-provenance.json", provenance)
    probes = {}
    probe_env = isolated_env()
    if args.pi_distribution:
        external_root = Path(args.pi_distribution).absolute()
        external_manifest = load_json(external_root / 'pi-runtime.json')
        probe_env.update({'CRAFT_PI_NODE': str(executable(args.pi_node)),
                          'CRAFT_PI_ENTRY': str(external_root / craft.relative(external_manifest['entry']))})
    for mode in ('--inspect', '--version'):
        response = json.loads(command([bundle / 'bin/craft-pi-executor.exe', mode], cwd=bundle, env=probe_env))
        if response.get('name') != 'craft-pi-executor' or response.get('version') != args.version:
            fail('copied executor CLI identity mismatch')
        probes[mode] = response
    driver_probe = run_owned([bundle / 'bin/pi-rpc-driver.exe', '--packaging-invalid'], cwd=bundle, env=probe_env, timeout=10)
    if driver_probe['returncode'] != 2 or driver_probe['cleanup'] != 'verified':
        fail('copied driver preflight startup failed')
    probes['driver_preflight'] = {'exit_code': 2, 'cleanup': 'verified', 'pi_child_started': False}
    if args.pi_distribution:
        pi_root = Path(args.pi_distribution).absolute()
        pi_manifest = load_json(pi_root / 'pi-runtime.json')
        pi_entry = pi_root / craft.relative(pi_manifest['entry'])
        pi_identity = craft.pi_distribution(pi_root, PI_VERSION, pi_entry)
        node = executable(args.pi_node)
        probe_env.update({'PI_CODING_AGENT_DIR': str(stage / 'probe-agent'), 'HOME': str(stage / 'probe-home'),
                          'USERPROFILE': str(stage / 'probe-home'), 'PI_OFFLINE': '1', 'PI_TELEMETRY': '0'})
        if command([node, pi_entry, '--version'], cwd=stage, env=probe_env, timeout=30) != PI_VERSION:
            fail('external official Pi version mismatch')
        probes['external_pi'] = {'version': PI_VERSION, 'node_sha256': sha(node),
                                  'manifest_sha256': sha(pi_root / 'pi-runtime.json'), 'bundled': False}
        if craft.pi_distribution(pi_root, PI_VERSION, pi_entry) != pi_identity:
            fail('external Pi changed during no-model version probe')
    write_json(bundle / 'cli-probes.json', probes)
    assert_unchanged(runtime, frozen)
    manifest = {"name": "craft-pi-bundle", "version": args.version, "contract": craft.CONTRACT,
                "qualification": "candidate baseline; not accepted; no model/business/install acceptance",
                "min_installer_version": "0.7.0", "publication_blockers": publication_blockers,
                "base_commit": BASE, "pi": {"version": PI_VERSION, "protocol": "rpc"},
                "artifact": {"os": "windows", "arch": "x86_64", "source_commit": BASE,
                             "build_source": f"{UPSTREAM}@{BASE}; ordered patches and owned source sha256:{source_sha}; Rust {RUST_VERSION}; {TARGET}; build-provenance.json"},
                "runtime": {"entry": "bin/craft-pi-executor.exe", "entry_kind": "native", "driver": "bin/pi-rpc-driver.exe", "driver_kind": "native",
                            "entry_protocol": "docs/entry-protocol.md", "required_files": sorted("bin/" + p.name for p in (bundle / "bin").iterdir())},
                "patches": [{"path": "source/" + p["path"], "sha256": p["sha256"]} for p in value["patches"]], "files": tree(bundle)}
    return certify_bundle(bundle, manifest, runtime, frozen, Path(args.output))


def certify_bundle(bundle, manifest, runtime, frozen, output):
    try:
        assert_unchanged(runtime, frozen)
        write_json(bundle / craft.MANIFEST, manifest)
        craft.bundle(bundle)
        assert_unchanged(runtime, frozen)
        shutil.copytree(bundle, output)
        craft.bundle(output)
        assert_unchanged(runtime, frozen)
    except Exception:
        # Neither staging nor final output may retain an eligible manifest after failure.
        (bundle / craft.MANIFEST).unlink(missing_ok=True)
        (output / craft.MANIFEST).unlink(missing_ok=True)
        raise
    return {"bundle": str(output.absolute()), "manifest_sha256": sha(output / craft.MANIFEST)}


def validate_npm_lock(lock):
    if lock.get("lockfileVersion") != 3 or not isinstance(lock.get("packages"), dict):
        fail("npm lockfileVersion 3 and complete package closure required")
    packages = lock["packages"]
    main = packages.get("node_modules/" + PI_PACKAGE, {})
    if main.get("version") != PI_VERSION:
        fail("official Pi exact package version missing from lock")
    for rel, pkg in packages.items():
        if not rel:
            continue
        craft.relative(rel)
        url = urlparse(pkg.get("resolved", ""))
        if pkg.get("link") or not pkg.get("version") or url.scheme != "https" or url.netloc != "registry.npmjs.org" or not re.fullmatch(r"sha(?:512|256)-[A-Za-z0-9+/]+={0,2}", pkg.get("integrity", "")):
            fail("npm dependency lacks exact official registry URL/integrity: " + rel)
    return packages


def copy_node(source, target, expected_sha):
    if sha(source) != expected_sha:
        fail('Node source changed before copy')
    copy_file(source, target)
    if sha(source) != expected_sha or sha(target) != expected_sha:
        fail('Node source/copy identity drift')
    return target


def probe_pi_version(source_node, selected_node, entry, stage, env, expected_sha):
    if sha(source_node) != expected_sha or sha(selected_node) != expected_sha:
        fail('Node source/copy identity drift before probe')
    version = command([selected_node, entry, '--version'], cwd=stage, env=env, timeout=60)
    if sha(source_node) != expected_sha or sha(selected_node) != expected_sha:
        fail('Node source/copy identity drift during probe')
    if version != PI_VERSION:
        fail('standalone CLI version/import probe failed')
    return version


def has_license_grant(text):
    if len(text) < 200:
        return False
    if re.search(r'(?i)permission is hereby granted|permission to use, copy|apache license[\s,]+version|redistribution and use|mozilla public license|gnu (?:lesser |affero )?general public license|isc license|blue oak model license', text):
        return True
    # Recognize the actual Unlicense dedication, permission and disclaimer, not
    # package SPDX metadata or a README link alone.
    normalized = ' '.join(text.casefold().split())
    return all(fragment in normalized for fragment in (
        'this is free and unencumbered software released into the public domain.',
        'anyone is free to copy, modify, publish, use, compile, sell, or distribute this software',
        'we make this dedication for the benefit of the public at large',
        'the software is provided "as is", without warranty of any kind',
        'unlicense.org',
    ))


def notice_source_registry(distribution):
    root = Path(distribution) / 'licenses/pi'
    registry_path = root / 'source-registry.json'
    if not registry_path.exists():
        return {}, None
    identity = load_json(root / 'notice-source-identity.json')
    if not isinstance(identity, dict) or identity.get('registry_sha256') != sha(registry_path):
        fail('notice source registry identity drift')
    registry = load_json(registry_path)
    artifacts = registry.get('artifact_hashes')
    if not isinstance(artifacts, dict) or not artifacts:
        fail('notice source registry artifact inventory missing')
    expected = {'source-registry.json': identity['registry_sha256']}
    for rel, item in artifacts.items():
        path = root / craft.relative(rel)
        craft.no_links(path)
        if sha(path) != item.get('sha256') or path.stat().st_size != item.get('bytes'):
            fail('notice source artifact hash/size drift: ' + rel)
        expected[rel] = item['sha256']
    if identity.get('files') != expected or {p: h for p, h in tree(root).items() if p != 'notice-source-identity.json'} != expected:
        fail('notice source inventory drift')
    records = {}
    for item in registry['packages']:
        key = (item['name'], item['version'])
        if key in records:
            fail('duplicate notice package association')
        if item.get('status') in ('resolved', 'resolved-detector-gap'):
            rel = craft.relative(item['license_file'])
            if expected.get(rel) != item.get('license_sha256') or not has_license_grant((root / rel).read_text(encoding='utf-8')):
                fail('registered notice lacks matching actual license grant')
        records[key] = item
    return records, identity['registry_sha256']


def integrate_notice_sources(distribution, source, approved_registry_sha256):
    source = craft.no_links(Path(source).absolute())
    registry_path = source / 'source-registry.json'
    if sha(registry_path) != approved_registry_sha256:
        fail('approved notice registry SHA256 mismatch')
    registry = load_json(registry_path)
    files = {'source-registry.json': approved_registry_sha256}
    for rel, item in registry['artifact_hashes'].items():
        p = source / craft.relative(rel)
        craft.no_links(p)
        if sha(p) != item['sha256'] or p.stat().st_size != item['bytes']:
            fail('original notice source hash/size mismatch')
        files[rel] = item['sha256']
    if tree(source) != files:
        fail('original notice source tree differs from registry')
    target = fresh(Path(distribution) / 'licenses/pi')
    for rel, digest in files.items():
        copy_file(source / rel, target / rel)
        if sha(source / rel) != digest or sha(target / rel) != digest:
            fail('notice changed during exact copy')
    write_json(target / 'notice-source-identity.json', {'schema_version': 1, 'registry_sha256': approved_registry_sha256, 'files': files})
    notice_source_registry(distribution)
    return files


def npm_notice_inventory(distribution):
    """Inventory actual copyright/license text; SPDX metadata alone is insufficient."""
    distribution = Path(distribution)
    lock = load_json(distribution / 'package-lock.json')
    packages, missing = [], []
    sources, registry_sha = notice_source_registry(distribution)
    for rel, locked in validate_npm_lock(lock).items():
        if not rel or not (distribution / rel / 'package.json').is_file():
            continue
        root = distribution / rel
        metadata = load_json(root / 'package.json')
        notices = {}
        license_text_found = False
        for p in root.iterdir():
            if not p.is_file() or not re.match(r'(?i)^(licen[cs]e|copying|notice|readme)([._-]|$)', p.name):
                continue
            craft.no_links(p)
            text = p.read_text(encoding='utf-8', errors='replace')
            # Preserve only real distributed text; a label such as 'License: MIT'
            # is not the MIT permission grant or copyright notice.
            if re.search(r'(?i)copyright|permission is hereby granted|apache license|redistribution and use|mozilla public license', text) or has_license_grant(text):
                notices[p.relative_to(distribution).as_posix()] = sha(p)
            if has_license_grant(text):
                license_text_found = True
        association = sources.get((metadata.get('name'), metadata.get('version')))
        if association:
            if association.get('integrity') != locked['integrity']:
                fail('notice association npm lock integrity mismatch')
            if association.get('status') in ('resolved', 'resolved-detector-gap'):
                registered = 'licenses/pi/' + association['license_file']
                notices[registered] = association['license_sha256']
                license_text_found = True
        item = {'path': rel, 'name': metadata.get('name'), 'version': metadata.get('version'),
                'declared_license': metadata.get('license'), 'integrity': locked['integrity'], 'notice_files': notices,
                'license_text_found': license_text_found}
        if association:
            # Preserve the source association and its limitations verbatim. In
            # particular AWS tag/version/time evidence is not an attestation.
            item['source_association'] = association
        packages.append(item)
        if not license_text_found:
            missing.append({'name': item['name'], 'version': item['version'], 'path': rel, 'reason': 'actual license grant text absent/unrecognized; SPDX or a copyright label alone is insufficient'})
    return {'schema_version': 1, 'packages': packages, 'missing': missing, 'source_registry_sha256': registry_sha,
            'distribution_status': 'blocked-missing-notices' if missing else 'notice-text-inventoried; legal review still required'}


def require_pi_notices(distribution):
    actual = npm_notice_inventory(distribution)
    declared = load_json(Path(distribution) / 'NOTICE-inventory.json')
    if declared != actual or actual['missing']:
        fail('Pi distribution release blocked: missing/drifted NOTICE-inventory or actual license/copyright texts')
    return actual


def prepare_pi(args):
    if craft.host() != {"os": "windows", "arch": "x86_64"}:
        fail("unsupported Pi packaging platform; Windows x86_64 only")
    node, npm = executable(args.node), executable(args.npm_cli)
    stage = fresh(args.stage)
    env = isolated_env()
    agent = stage / "probe-agent"
    agent.mkdir()
    env.update({"PI_CODING_AGENT_DIR": str(agent), "PI_OFFLINE": "1", "HOME": str(stage / "home"), "USERPROFILE": str(stage / "home"),
                "APPDATA": str(stage / 'appdata'), "LOCALAPPDATA": str(stage / 'localappdata')})
    node_identity = {"version": command([node, "--version"], cwd=stage, env=env), "sha256": sha(node)}
    if node_identity["version"] != NODE_VERSION:
        fail("explicit Node 24.20.0 required")
    distribution = stage / "distribution"
    distribution.mkdir()
    write_json(distribution / "package.json", {"name": "official-pi-standalone-package", "version": "1.0.0", "private": True,
                                               "dependencies": {PI_PACKAGE: PI_VERSION}})
    for name in ("user.npmrc", "global.npmrc"):
        (stage / name).write_text("", encoding="utf-8")
    npm_args = [node, npm, "--prefix", distribution, "--ignore-scripts", "--bin-links=false", "--no-audit", "--no-fund",
                "--registry=https://registry.npmjs.org", "--cache", stage / "npm-cache", "--userconfig", stage / "user.npmrc", "--globalconfig", stage / "global.npmrc"]
    if args.lock:
        lock_path = executable(args.lock)
        validate_npm_lock(load_json(lock_path))
        copy_file(lock_path, distribution / "package-lock.json")
    else:
        command([*npm_args, "install", "--package-lock-only"], cwd=stage, env=env)
    lock_path = distribution / "package-lock.json"
    lock_sha = sha(lock_path)
    packages = validate_npm_lock(load_json(lock_path))
    command([*npm_args, "ci", "--include=optional"], cwd=stage, env=env)
    if sha(lock_path) != lock_sha:
        fail("npm changed frozen lock during ci")
    closure = []
    for rel, pkg in packages.items():
        if not rel:
            continue
        package_json = distribution / rel / "package.json"
        if not package_json.exists():
            if pkg.get("optional"):
                continue  # Other platform optional packages remain pinned in the lock.
            fail("npm locked dependency missing: " + rel)
        installed = load_json(package_json)
        if installed.get("version") != pkg["version"]:
            fail("npm installed package version drift: " + rel)
        closure.append({"path": rel, "name": installed.get("name"), "version": installed["version"],
                        "integrity": pkg["integrity"], "license": installed.get("license"), "has_install_script": bool(pkg.get("hasInstallScript"))})
    package_root = "node_modules/" + PI_PACKAGE
    entry = package_root + "/dist/bundle/cli.js"
    probe_node = node
    if args.include_node:
        probe_node = copy_node(node, distribution / "node/node.exe", node_identity['sha256'])
        copy_file(node.parent / 'LICENSE', distribution / 'node/LICENSE')
    probe = probe_pi_version(node, probe_node, distribution / entry, stage, env, node_identity['sha256'])
    write_json(distribution / "npm-provenance.json", {"schema_version": 1, "registry": "https://registry.npmjs.org", "package": PI_PACKAGE,
               "version": PI_VERSION, "npm_version": command([node, npm, "--version"], cwd=stage, env=env), "lock_sha256": lock_sha,
               "node": node_identity, "node_bundled": args.include_node, "install_scripts": "disabled", "closure": closure,
               "probe": {"version_stdout": probe, "model_invoked": False},
               "qualification": "official npm closure and CLI imports; optional native features and provider not qualified"})
    notice_inventory = npm_notice_inventory(distribution)
    write_json(distribution / 'NOTICE-inventory.json', notice_inventory)
    value = {"schema_version": 1, "name": "official-pi-standalone", "version": PI_VERSION,
             "dependency_closure": "self-contained-node-modules-v1", "package_root": package_root,
             "dependency_root": "node_modules", "entry": entry, "files": tree(distribution)}
    write_json(distribution / "pi-runtime.json", value)
    craft.pi_distribution(distribution, PI_VERSION, distribution / entry)
    return {"distribution": str(distribution), "entry": entry, "manifest_sha256": sha(distribution / "pi-runtime.json"), "files": len(value["files"]), "packages": len(closure), "node": node_identity, 'distribution_status': notice_inventory['distribution_status'], 'missing_notices': notice_inventory['missing']}


def download_node_archive(pin, destination):
    if pin != load_json(RUNTIME / 'pi/node-windows-x64.json') or pin.get('version') != NODE_VERSION or pin.get('url') != 'https://nodejs.org/dist/v24.20.0/node-v24.20.0-win-x64.zip':
        fail('unsupported official Node archive pin')
    destination = Path(destination)
    if destination.exists():
        fail('Node download target already exists')
    request = Request(pin['url'], headers={'User-Agent': 'craft-pi-upstream-acquisition'})
    with urlopen(request, timeout=30) as response, destination.open('xb') as out:
        if response.geturl() != pin['url']:
            fail('Node archive redirected outside explicit pinned URL')
        total = 0
        while True:
            data = response.read(1024 * 1024)
            if not data:
                break
            total += len(data)
            if total > 150 * 1024 * 1024:
                fail('Node archive exceeds pinned acquisition limit')
            out.write(data)
    if sha(destination) != pin['sha256']:
        fail('official Node archive SHA256 mismatch')
    return destination


def acquisition_worker_command(args, token):
    command = [sys.executable, '-B', str(Path(__file__).resolve()), 'acquire-pi', '--stage', args.stage,
               '--lock', args.lock, '--deadline-seconds', str(args.deadline_seconds), '--_worker-token', token]
    if args.node_archive:
        command += ['--node-archive', args.node_archive]
    return command


def acquire_cli(args):
    if not 1 <= args.deadline_seconds <= 600:
        fail('acquire deadline must be in 1..600 seconds')
    if args._worker_token:
        if args._worker_token != os.environ.get('CRAFT_ACQUIRE_OWNER_TOKEN'):
            fail('internal acquire worker requires owned supervisor')
        return acquire_pi(args)
    stage = craft.no_links(Path(args.stage).absolute())
    if stage.exists():
        fail('acquire output must be a fresh directory')
    import secrets
    token = secrets.token_hex(32)
    env = isolated_env()
    env['CRAFT_ACQUIRE_OWNER_TOKEN'] = token
    observed = run_owned(acquisition_worker_command(args, token), cwd=Path(__file__).resolve().parents[1],
                         env=env, timeout=args.deadline_seconds, cleanup_seconds=5)
    lifecycle = {k: observed[k] for k in ('returncode', 'timed_out', 'cleanup', 'had_descendants', 'scope')}
    lifecycle['total_deadline_seconds'] = args.deadline_seconds
    receipt = stage / 'acquisition-result.json'
    if observed['timed_out'] or observed['cleanup'] != 'verified' or observed['had_descendants'] or observed['returncode'] != 0:
        if stage.is_dir():
            receipt.unlink(missing_ok=True)
            write_json(stage / 'acquisition-failure.json', lifecycle)
        fail('acquire total deadline/lifecycle failure: cleanup=' + observed['cleanup'] + '; ' + observed['stderr'][-1500:])
    value = json.loads(observed['stdout'])
    if not receipt.is_file() or load_json(receipt) != value:
        fail('acquire worker receipt missing or inconsistent')
    write_json(stage / 'acquisition-supervision.json', lifecycle)
    return value


def acquire_pi(args):
    if craft.host() != {'os': 'windows', 'arch': 'x86_64'}:
        fail('unsupported acquisition platform; only Windows x86_64')
    stage = fresh(args.stage)
    pin = load_json(RUNTIME / 'pi/node-windows-x64.json')
    archive = stage / 'node.zip'
    if args.node_archive:
        source = executable(args.node_archive)
        if sha(source) != pin['sha256']:
            fail('cached official Node archive SHA256 mismatch')
        copy_file(source, archive)
        if sha(archive) != pin['sha256']:
            fail('copied official Node archive SHA256 mismatch')
    else:
        download_node_archive(pin, archive)
    extracted = extract_official_node(archive, stage / 'node-download', pin)
    node_root = extracted / pin['archive_root']
    node = node_root / 'node.exe'
    if sha(node) != pin['node_sha256']:
        fail('extracted official Node executable hash mismatch')
    result = prepare_pi(argparse.Namespace(stage=str(stage / 'pi'), node=str(node),
                         npm_cli=str(node_root / 'node_modules/npm/bin/npm-cli.js'), lock=args.lock, include_node=True))
    distribution = Path(result['distribution'])
    entry = distribution / result['entry']
    frozen = craft.pi_distribution(distribution, PI_VERSION, entry)
    registry = RUNTIME / 'pi/notices/source-registry.json'
    notice_sha = '82b6c2000a313e6266b2b2e20f3fcce287194cab69cdb41ec244400ad2c2196b'
    integrate_notice_sources(distribution, registry.parent, notice_sha)
    notices = npm_notice_inventory(distribution)
    write_json(distribution / 'NOTICE-inventory.json', notices)
    write_json(distribution / 'upstream-acquisition.json', {
        'schema_version': 1, 'node_archive': pin, 'npm_lock_sha256': sha(distribution / 'package-lock.json'),
        'notice_registry_sha256': notice_sha, 'dependency_closure': 'full official declared dependencies; no pruning',
        'use': 'dependency acquired from upstream on this computer; not our redistributed Pi/Node artifact',
        'redistribution_status': notices['distribution_status'],
    })
    manifest = frozen['manifest']
    manifest['files'] = {p: h for p, h in tree(distribution).items() if p != 'pi-runtime.json'}
    write_json(distribution / 'pi-runtime.json', manifest)
    craft.pi_distribution(distribution, PI_VERSION, entry)
    probe = probe_pi(distribution, distribution / 'node/node.exe', stage / 'rpc-probe')
    pi_options = ['--craft-pi-node', str(distribution / 'node/node.exe'), '--craft-pi-entry', str(entry),
                  '--craft-pi-distribution', str(distribution), '--craft-pi-version', PI_VERSION]
    result = {**result, 'files': len(manifest['files']), 'manifest_sha256': sha(distribution / 'pi-runtime.json'), 'rpc_probe': probe,
              'missing_notices': notices['missing'], 'distribution_status': notices['distribution_status'],
              'installer_pi_options': pi_options, 'acquisition': 'complete official npm closure; upstream download on this computer',
              'redistribution': 'blocked for Pi ZIP; excluded from our native Craft release'}
    write_json(stage / 'acquisition-result.json', result)
    return result


def probe_pi(distribution, node, stage):
    distribution = craft.no_links(Path(distribution).absolute())
    node = executable(node)
    value = load_json(distribution / "pi-runtime.json")
    entry = distribution / craft.relative(value.get("entry"))
    identity = craft.pi_distribution(distribution, PI_VERSION, entry)
    provenance = load_json(distribution / "npm-provenance.json")
    if sha(node) != provenance.get("node", {}).get("sha256"):
        fail("probe Node identity differs from packaged runtime")
    stage = fresh(stage)
    env = isolated_env()
    env.update({"PI_CODING_AGENT_DIR": str(stage / "agent"), "HOME": str(stage / "home"), "USERPROFILE": str(stage / "home"),
                "PI_OFFLINE": "1", "PI_TELEMETRY": "0"})
    argv = [node, entry, "--mode", "rpc", "--offline", "--no-session", "--no-extensions", "--no-context-files", "--no-skills",
            "--no-prompt-templates", "--no-mcp", "--no-tools", "--no-themes", "--no-approve"]
    result = run_owned(argv, cwd=stage, env=env, input='{"id":"packaging-state-only","type":"get_state"}\n', timeout=30)
    if result['cleanup'] != 'verified' or result['timed_out'] or result['had_descendants']:
        fail('Pi state probe lifecycle blocked: cleanup=' + result['cleanup'])
    responses = [json.loads(line) for line in result['stdout'].splitlines() if line.strip()]
    matched = [x for x in responses if x.get("id") == "packaging-state-only"]
    if result['returncode'] or len(matched) != 1 or not matched[0].get("success") or matched[0].get("data", {}).get("messageCount") != 0:
        fail("standalone RPC get_state probe failed; no model prompt was sent")
    if craft.pi_distribution(distribution, PI_VERSION, entry) != identity:
        fail("Pi distribution changed during probe")
    report = {"exit_code": result['returncode'], "get_state_success": True, "message_count": 0, "model_invoked": False,
              "distribution_sha256": identity["sha256"], "node_sha256": sha(node)}
    write_json(stage / "probe-result.json", report)
    return report


def extract_official_node(archive, destination, pin):
    if pin != load_json(RUNTIME / 'pi/node-windows-x64.json') or sha(archive) != pin['sha256']:
        fail('official Node archive identity required before extraction')
    # This is npm's published built-in config, not a user/profile .npmrc.
    # The exact archive digest is verified before this one fixed-path exception.
    return safe_extract_zip(archive, destination, official_names={pin['archive_root'] + '/node_modules/npm/.npmrc'})


def safe_extract_zip(archive, destination, *, official_names=frozenset()):
    """Validate the whole archive before creating any extracted item."""
    with zipfile.ZipFile(archive) as z:
        seen, total = set(), 0
        for item in z.infolist():
            name = item.filename[:-1] if item.is_dir() else item.filename
            craft.relative(name)
            if any(p.casefold() in DENIED for p in Path(name).parts) and name not in official_names:
                fail("archive contains credential/profile path")
            key = name.casefold()
            if key in seen or (item.external_attr >> 16) & 0o170000 == 0o120000 or item.flag_bits & 1:
                fail("archive duplicate/link/encrypted member")
            seen.add(key)
            total += item.file_size
            if total > 2 * 1024**3 or len(seen) > 100000:
                fail("archive exceeds packaging limits")
        if not seen:
            fail("archive is empty")
        destination = fresh(destination)
        for item in z.infolist():
            target = destination / item.filename
            if item.is_dir():
                target.mkdir(parents=True, exist_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                with z.open(item) as src, target.open("xb") as out:
                    shutil.copyfileobj(src, out)
    return destination


def release_artifact(bundle, output, *, pi=False):
    if pi:
        require_pi_notices(bundle)
        entry = load_json(Path(bundle) / "pi-runtime.json").get("entry")
        craft.pi_distribution(bundle, PI_VERSION, Path(bundle) / craft.relative(entry))
    else:
        craft.bundle(bundle)
    files = tree(bundle)
    output = Path(output)
    if output.exists():
        fail("release output exists")
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "x", zipfile.ZIP_DEFLATED) as z:
        for name in sorted(files):
            item = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            item.external_attr = 0o100644 << 16
            data = (Path(bundle) / name).read_bytes()
            if hashlib.sha256(data).hexdigest() != files[name]:
                fail("release input changed while archiving")
            z.writestr(item, data, compress_type=zipfile.ZIP_DEFLATED)
    check_files(bundle, files)
    digest = sha(output)
    kind = "official-pi-standalone" if pi else "craft-pi-bundle"
    blockers = load_json(Path(bundle) / craft.MANIFEST).get('publication_blockers', []) if not pi else []
    output.with_suffix(output.suffix + ".sha256").write_text(digest + "  " + output.name + "\n", encoding="utf-8")
    write_json(output.with_suffix(output.suffix + ".upload-plan.json"), {"published": False, "kind": kind, "asset": output.name, "sha256": digest,
               "release_eligible": False, "publication_blockers": blockers + ['candidate only; business/install acceptance is separate'],
               "release_url": None, "next": "review artifact/license/runtime acceptance; publish approved release; resolve real tag/commit/asset URL and digest before installer pin"})
    detail = ("Includes the inventoried original npm notice texts; legal and runtime acceptance remain separate." if pi else
              "Includes canonical owned source, ordered patches, lockfiles, licenses and build/DLL provenance.")
    if blockers:
        detail += ' Publication blocked: ' + '; '.join(blockers) + '.'
    output.with_suffix(output.suffix + ".release-body.md").write_text(
        "Prepared candidate " + kind + " Windows artifact\n\nSHA256: " + digest + "\n\nNot published. Runtime/provider/business acceptance remains separate. " + detail + "\n", encoding="utf-8")
    return {"asset": str(output), "sha256": digest, "published": False}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    p = sub.add_parser('acquire-pi')
    p.add_argument('--stage', required=True)
    p.add_argument('--deadline-seconds', type=int, default=600, help='total owned-process wall deadline, 1..600 seconds (default 600)')
    p.add_argument('--_worker-token', default=None, help=argparse.SUPPRESS)
    p.add_argument('--lock', default=str(RUNTIME / 'pi/package-lock.json'))
    p.add_argument('--node-archive', help='optional locally cached exact official archive; its pinned SHA256 is mandatory')
    p = sub.add_parser('notice-inventory')
    p.add_argument('--distribution', required=True)
    p.add_argument('--output', required=True)
    p = sub.add_parser("snapshot-policy")
    p.add_argument('--series-sha256', required=True)
    for name in ("series", "source-identity", "stage", "upstream-mirror"):
        p.add_argument("--" + name, required=True)
    p = sub.add_parser("snapshot-bridge", help="import only an explicit lead-approved driver source manifest")
    p.add_argument("--source", required=True)
    p.add_argument("--manifest", required=True)
    p.add_argument("--source-tree-sha256", required=True)
    p = sub.add_parser("freeze", help="ONLY after the lead freezes all worker sources")
    for name in ("bridge", "executor", "notices", "protocol"):
        p.add_argument("--" + name, required=True)
    p.add_argument("--patch", action="append", required=True)
    p.add_argument('--series', required=True)
    p.add_argument('--series-sha256', required=True)
    p = sub.add_parser("build")
    p.add_argument("--runtime", default=str(RUNTIME))
    for name in ("stage", "output", "version", "cargo", "rustc", "gcc", "objdump"):
        p.add_argument("--" + name, required=True)
    p.add_argument("--dll-dir", action="append", default=[])
    p.add_argument("--upstream-mirror")
    p.add_argument("--offline", action="store_true")
    p.add_argument('--candidate-allow-missing-notice', action='store_true', help='prepare a non-publishable candidate with exact missing compiled grants recorded; never legal/release certification')
    p.add_argument('--reuse-stage', action='store_true', help='reuse exact prior source-layout cache after previous manifest verification')
    p.add_argument('--previous-source-manifest')
    p.add_argument('--previous-source-sha256')
    p.add_argument('--pi-distribution', help='explicit separately acquired official Pi root; never copied')
    p.add_argument('--pi-node', help='explicit Node for no-model external Pi version probe')
    p = sub.add_parser("prepare-pi")
    for name in ("stage", "node", "npm-cli"):
        p.add_argument("--" + name, required=True)
    locks = p.add_mutually_exclusive_group()
    locks.add_argument("--lock", default=str(RUNTIME / "pi/package-lock.json"))
    locks.add_argument("--resolve-lock", dest="lock", action="store_const", const=None, help="explicitly resolve a new candidate lock; review before canonical adoption")
    p.add_argument("--include-node", action="store_true")
    p = sub.add_parser("probe-pi")
    for name in ("distribution", "node", "stage"):
        p.add_argument("--" + name, required=True)
    p = sub.add_parser("release-pi")
    p.add_argument("--distribution", required=True)
    p.add_argument("--output", required=True)
    p = sub.add_parser("release-artifact")
    p.add_argument("--bundle", required=True)
    p.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    try:
        if args.action == 'acquire-pi':
            result = acquire_cli(args)
        elif args.action == 'notice-inventory':
            result = npm_notice_inventory(args.distribution)
            write_json(args.output, result)
            print(json.dumps({'distribution_status': result['distribution_status'], 'missing': result['missing'], 'output': args.output}, indent=2))
            return 2 if result['missing'] else 0
        elif args.action == "snapshot-policy":
            result = snapshot_policy(args.series, args.source_identity, args.stage, args.upstream_mirror, expected_series_sha256=args.series_sha256)
        elif args.action == "snapshot-bridge":
            result = snapshot_bridge(args.source, args.manifest, args.source_tree_sha256)
        elif args.action == "freeze":
            result = freeze(args.bridge, args.executor, args.patch, args.notices, args.protocol, series_path=args.series, series_sha256=args.series_sha256)
        elif args.action == "build":
            result = build(args)
        elif args.action == "prepare-pi":
            result = prepare_pi(args)
        elif args.action == "probe-pi":
            result = probe_pi(args.distribution, args.node, args.stage)
        elif args.action == "release-pi":
            result = release_artifact(args.distribution, args.output, pi=True)
        else:
            result = release_artifact(args.bundle, args.output)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (InstallError, OSError, ValueError, KeyError, TypeError, subprocess.TimeoutExpired, zipfile.BadZipFile) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
