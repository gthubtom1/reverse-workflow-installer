"""Freeze and package the Codex host for the existing bounded Craft execution loop.

Uses the existing reviewed GNU build, lifecycle, DLL and license helpers. It never
installs a compiler, calls a model, changes the frozen Pi source, or accepts a dirty
source snapshot as a released identity.
"""
import argparse
import json
import os
from pathlib import Path
import shutil
import sys
import zipfile

import craft
import craft_codex
import build_craft_bundle as common
from configuration import digest, encode_json, load_json
from versions import InstallError

REPO = Path(__file__).resolve().parents[1]
RUNTIME = REPO / "adapters/craft-codex/runtime"
BASE_RUNTIME = REPO / "adapters/craft-pi/runtime"
MANIFEST = "source-manifest.json"
RECIPES = ("build_craft_codex_bundle.py", "build_craft_bundle.py", "craft_cargo_notices.py",
           "packaging_process.py", "craft_codex.py", "craft.py", "configuration.py", "versions.py")
CRATES = {"craft-codex-bridge": "bridge", "craft-codex-executor": "executor"}
BINS = (("craft-codex-bridge", "codex-app-server-driver"),
        ("craft-codex-executor", "craft-codex-executor"))


def inputs(runtime=RUNTIME, base=BASE_RUNTIME):
    owned = common.tree(runtime)
    owned.pop(MANIFEST, None)
    baseline = common.tree(base / "patches")
    baseline = {"patches/" + name: value for name, value in baseline.items()}
    baseline.update({"notices/" + name: value for name, value in common.tree(base / "notices").items()})
    baseline[MANIFEST] = common.sha(base / MANIFEST)
    return {"schema_version": 1, "name": "craft-codex-execution-source",
            "base_commit": craft.BASE_COMMIT,
            "base_manifest_sha256": baseline[MANIFEST], "mapping": CRATES,
            "files": owned, "shared_base_files": baseline,
            "project_files": {name: common.sha(REPO / name) for name in (
                "LICENSE", "adapters/craft-codex/THIRD_PARTY_NOTICES.md")},
            "recipe_files": {name: common.sha(REPO / "scripts" / name) for name in RECIPES}}


def host_policy(runtime, base):
    value = craft_codex.read_object(runtime / "patches/series.json")
    expected_fields = {"schema_version", "base_commit", "base_tree", "base_policy_series_sha256", "series", "source_inventory", "lock_sha256", "contract"}
    if set(value) != expected_fields or type(value["schema_version"]) is not int or value["schema_version"] != 1 or value["base_commit"] != craft.BASE_COMMIT or value["base_policy_series_sha256"] != common.sha(base / "patches/series.json"):
        raise InstallError("Codex host patch base/schema identity mismatch")
    if not isinstance(value["series"], list) or not value["series"] or not isinstance(value["source_inventory"], list) or not value["source_inventory"]:
        raise InstallError("Codex ordered host patches/source inventory required")
    seen = set()
    for item in value["series"]:
        if not isinstance(item, dict) or set(item) != {"file", "sha256", "bytes", "sources"}:
            raise InstallError("Codex host patch entry malformed")
        name = craft.relative(item["file"])
        if "/" in name or not name.endswith(".patch") or name.casefold() in seen or common.sha(runtime / "patches" / name) != item["sha256"] or type(item["bytes"]) is not int or (runtime / "patches" / name).stat().st_size != item["bytes"]:
            raise InstallError("Codex host patch path/hash/duplicate mismatch")
        if not isinstance(item["sources"], list) or not item["sources"] or len(set(item["sources"])) != len(item["sources"]):
            raise InstallError("Codex host patch source list malformed")
        for source in item["sources"]:
            craft.relative(source)
        seen.add(name.casefold())
    seen.clear()
    for item in value["source_inventory"]:
        if not isinstance(item, dict) or set(item) != {"path", "sha256", "bytes", "state"} or item["state"] != "modified-by-codex-delta" or type(item["bytes"]) is not int or item["bytes"] <= 0:
            raise InstallError("Codex changed source entry malformed")
        name = craft.relative(item["path"])
        if name in seen:
            raise InstallError("Codex changed source duplicate")
        seen.add(name)
    if {source for item in value["series"] for source in item["sources"]} != seen:
        raise InstallError("Codex host patch/source inventory mismatch")
    return value


def checked_inputs(runtime=RUNTIME, base=BASE_RUNTIME):
    expected = load_json(runtime / MANIFEST)
    if inputs(runtime, base) != expected:
        raise InstallError("Codex owned source, policy/notices, or build recipe drift since explicit freeze")
    if expected["base_commit"] != craft.BASE_COMMIT:
        raise InstallError("Codex upstream base unsupported")
    host_policy(runtime, base)
    for name in CRATES.values():
        if not (runtime / name / "Cargo.lock").is_file():
            raise InstallError("Codex crate Cargo.lock missing")
    return expected


def freeze(args):
    runtime, base = Path(args.runtime).absolute(), Path(args.base_runtime).absolute()
    value = inputs(runtime, base)
    common.write_json(runtime / MANIFEST, value)
    checked_inputs(runtime, base)
    return {"frozen": True, "sha256": common.sha(runtime / MANIFEST),
            "source_files": len(value["files"]), "shared_files": len(value["shared_base_files"])}


def build(args):
    if craft.host() != {"os": "windows", "arch": "x86_64"}:
        raise InstallError("Codex native package currently admits Windows x86_64 GNU")
    runtime, base = Path(args.runtime).absolute(), Path(args.base_runtime).absolute()
    frozen = checked_inputs(runtime, base)
    source_manifest_sha = common.sha(runtime / MANIFEST)
    source_commit = common.git_command(["git", "rev-parse", "HEAD"], cwd=REPO)
    tracked = common.git_command(["git", "status", "--porcelain", "--untracked-files=normal"], cwd=REPO)
    if tracked:
        raise InstallError("Commit the reviewed/frozen implementation before packaging; no dirty release provenance")
    stage, output = craft.no_links(Path(args.stage).absolute()), craft.no_links(Path(args.output).absolute())
    if stage.exists() or output.exists() or stage.is_relative_to(output) or output.is_relative_to(stage):
        raise InstallError("Codex stage/output must be separate new directories")
    if any(p.is_relative_to(q) or q.is_relative_to(p) for p in (stage, output) for q in (runtime, base)):
        raise InstallError("Codex staging/output must be separate from canonical inputs")
    common.fresh(stage)
    tools = {name: common.executable(getattr(args, name)) for name in ("cargo", "rustc", "gcc", "objdump")}
    env = common.isolated_env()
    env.update({"CARGO_HOME": str(craft.no_links(Path(args.cargo_home).absolute())),
                "CARGO_TARGET_DIR": str(stage / "target"), "RUSTC": str(tools["rustc"]),
                "CARGO_BUILD_JOBS": "3", "CARGO_TARGET_X86_64_PC_WINDOWS_GNU_LINKER": str(tools["gcc"]),
                "PATH": str(tools["gcc"].parent) + os.pathsep + env.get("PATH", "")})
    tool_info = {name: {"sha256": common.sha(path),
                        "version": common.command([path, "--version"], cwd=stage, env=env)} for name, path in tools.items()}
    verbose = common.command([tools["rustc"], "-vV"], cwd=stage, env=env)
    if not tool_info["cargo"]["version"].startswith("cargo " + common.RUST_VERSION + " ") or ("host: " + common.TARGET + "\n") not in verbose or ("release: " + common.RUST_VERSION + "\n") not in verbose:
        raise InstallError("Explicit Rust/Cargo 1.99.0 Windows GNU toolchain required")
    source = stage / "source"
    source.mkdir()
    upstream = source / "craft-anything-adapted"
    common.clone_base(upstream, args.upstream_mirror)
    host = host_policy(runtime, base)
    if common.git_command(["git", "rev-parse", "HEAD^{tree}"], cwd=upstream) != host["base_tree"]:
        raise InstallError("Codex host original upstream tree mismatch")
    base_manifest = load_json(base / MANIFEST)
    common.apply_patches(upstream, base, base_manifest["patches"])
    series = load_json(base / "patches/series.json")
    for item in series["source_inventory"]:
        if common.sha(upstream / craft.relative(item["path"])) != item["sha256"]:
            raise InstallError("Codex shared policy replay/source mismatch")
    if common.sha(upstream / "Cargo.lock") != series["lock_sha256"]:
        raise InstallError("Codex shared upstream lock drift")
    old_patched_tree = common.git_command(["git", "write-tree"], cwd=upstream)
    for item in host["series"]:
        patch = runtime / "patches" / item["file"]
        common.git_command(["git", "apply", "--check", "--index", str(patch)], cwd=upstream)
        common.git_command(["git", "apply", "--index", str(patch)], cwd=upstream)
    for item in host["source_inventory"]:
        if common.sha(upstream / item["path"]) != item["sha256"] or (upstream / item["path"]).stat().st_size != item["bytes"]:
            raise InstallError("Codex applied host source differs from frozen inventory")
    if common.sha(upstream / "Cargo.lock") != host["lock_sha256"] or host["lock_sha256"] != series["lock_sha256"]:
        raise InstallError("Codex host policy unexpectedly changed dependency lock")
    patched_tree = common.git_command(["git", "write-tree"], cwd=upstream)
    changed = set(filter(None, common.git_command(["git", "diff", "--name-only", "-z", old_patched_tree, patched_tree], cwd=upstream).split("\0")))
    if changed != {item["path"] for item in host["source_inventory"]}:
        raise InstallError("Codex host patch changed undeclared upstream sources")
    for crate, name in CRATES.items():
        shutil.copytree(runtime / name, source / crate)
    common.validate_cargo_paths(source)
    before = {name: common.tree(source / name) for name in CRATES}
    upstream_before = common.staged_tree(upstream)
    metadata, compiled = {}, set()
    for crate, binary in BINS:
        manifest = source / crate / "Cargo.toml"
        cmd = [tools["cargo"], "build", "--locked", "--release", "--no-default-features", "--message-format=json", "--target", common.TARGET, "--manifest-path", manifest, "--bin", binary]
        if args.offline:
            cmd.append("--offline")
        messages = common.command(cmd, cwd=source, env=env, log_prefix=stage / "logs" / binary)
        for line in messages.splitlines():
            message = json.loads(line)
            if message.get("reason") == "compiler-artifact":
                compiled.add(message["package_id"])
        cmd = [tools["cargo"], "metadata", "--locked", "--format-version", "1", "--filter-platform", common.TARGET, "--manifest-path", manifest]
        if args.offline:
            cmd.append("--offline")
        metadata[crate] = json.loads(common.command(cmd, cwd=source, env=env))
        for package in metadata[crate]["packages"]:
            if package["source"] is None and not Path(package["manifest_path"]).resolve().is_relative_to(source.resolve()):
                raise InstallError("Codex Cargo dependency escaped the staged source")
    if checked_inputs(runtime, base) != frozen or any(common.tree(source / name) != values for name, values in before.items()) or common.staged_tree(upstream) != upstream_before:
        raise InstallError("Codex source/lock/recipe changed during build")
    bundle = stage / "bundle"
    bundle.mkdir()
    for _, binary in BINS:
        common.copy_file(stage / "target" / common.TARGET / "release" / (binary + ".exe"), bundle / "bin" / (binary + ".exe"))
    imports = common.collect_dlls(list((bundle / "bin").glob("*.exe")), bundle / "bin", tools["objdump"], args.dll_dir)
    for name in ("LICENSE-MIT", "LICENSE-APACHE", "ATTRIBUTION.md", "NOTICE", "Cargo.lock"):
        common.copy_file(upstream / name, bundle / ("source/upstream-Cargo.lock" if name == "Cargo.lock" else name))
    common.copy_file(runtime / "executor/Cargo.lock", bundle / "Cargo.lock")
    common.copy_file(REPO / "adapters/craft-codex/THIRD_PARTY_NOTICES.md", bundle / "THIRD_PARTY_NOTICES.md")
    from craft_cargo_notices import collect
    owned_packages = {package["id"]: package for item in metadata.values() for package in item["packages"]
                      if package["source"] is None and package["name"] in CRATES}
    owned_ids = compiled.intersection(owned_packages)
    notices = collect(metadata, compiled - owned_ids, [source / name / "Cargo.lock" for name in CRATES] + [upstream / "Cargo.lock"],
                      bundle / "licenses/cargo", source,
                      supplements=base / "notices/cargo-originals", standards=base / "notices/cargo-standard-0bsd")
    common.copy_file(REPO / "LICENSE", bundle / "licenses/cargo/owned/installer-MIT.txt")
    for package_id in sorted(owned_ids):
        package = owned_packages[package_id]
        notices[package["name"] + "-" + package["version"]] = {
            "name": package["name"], "version": package["version"], "source": None,
            "compiled": True, "declared_license": package["license"], "selected_license": "MIT",
            "status": "owned-project original license retained",
            "source_association": {"repository": "https://github.com/gthubtom1/reverse-workflow-installer",
                                   "commit": source_commit, "path": "LICENSE", "sha256": frozen["project_files"]["LICENSE"]},
            "notice_files": {"owned/installer-MIT.txt": frozen["project_files"]["LICENSE"]}}
    blockers = [name for name, record in notices.items() if record.get("status", "").startswith("missing-")]
    if blockers:
        raise InstallError("Codex original dependency license grant missing: " + ", ".join(blockers))
    common.write_json(bundle / "licenses/compiled-cargo-inventory.json", notices)
    for name in (*frozen["files"], MANIFEST):
        common.copy_file(runtime / name, bundle / "source/owned" / name)
    for name in frozen["shared_base_files"]:
        common.copy_file(base / name, bundle / "source/base" / name)
    for name in RECIPES:
        common.copy_file(REPO / "scripts" / name, bundle / "source/build-tools" / name)
    for name in frozen["project_files"]:
        common.copy_file(REPO / name, bundle / "source/project" / name)
    common.copy_file(runtime / "entry-protocol.md", bundle / "docs/entry-protocol.md")
    provenance = {"schema_version": 1, "source_commit": source_commit,
                  "source_manifest_sha256": source_manifest_sha, "base_commit": craft.BASE_COMMIT,
                  "patched_git_tree": patched_tree, "target": common.TARGET,
                  "toolchain": tool_info, "rustc_verbose": verbose, "dll_imports": imports,
                  "compiled_package_count": len(compiled), "publication_blockers": blockers,
                  "build_mode": "release --locked --no-default-features; fixtures disabled; no real model or target",
                  "acceptance": "source compilation and package integrity; protocol and business results recorded separately"}
    common.write_json(bundle / "provenance/build.json", provenance)
    files = common.tree(bundle)
    manifest = {"name": "craft-codex-bundle", "version": "0.1.0", "contract": craft_codex.CONTRACT,
                "base_commit": craft.BASE_COMMIT, "backend_id": craft_codex.BACKEND_ID,
                "permission_contract": craft_codex.PERMISSION_CONTRACT,
                "codex": {"version": "0.167.0-alpha.4.1", "protocol": "app-server-v2"},
                "codex_profile": {"id": load_json(runtime / "codex-profile.json")["id"],
                                  "path": "source/owned/codex-profile.json",
                                  "sha256": common.sha(runtime / "codex-profile.json")},
                "artifact": {"os": "windows", "arch": "x86_64", "target": common.TARGET,
                             "profile": "release", "source_commit": source_commit,
                             "build_source": "https://github.com/gthubtom1/reverse-workflow-installer/tree/" + source_commit},
                "runtime": {"entry": "bin/craft-codex-executor.exe", "entry_kind": "native",
                            "driver": "bin/codex-app-server-driver.exe", "driver_kind": "native",
                            "entry_protocol": "docs/entry-protocol.md",
                            "required_files": ["provenance/build.json", "source/owned/source-manifest.json", "source/owned/codex-profile.json"]},
                "files": files}
    common.write_json(bundle / craft_codex.MANIFEST, manifest)
    result = craft_codex.bundle(bundle)
    shutil.copytree(bundle, output)
    if not craft_codex.same_content(result, craft_codex.bundle(output)):
        raise InstallError("Codex copied artifact differs from verified staging")
    return {"complete": True, "output": str(output), "manifest_sha256": common.sha(output / craft_codex.MANIFEST),
            "source_manifest_sha256": source_manifest_sha, "source_commit": source_commit, "files": len(result["files"])}


def archive(args):
    bundle = craft_codex.bundle(args.bundle)
    archive_path = craft.no_links(Path(args.output).absolute())
    if archive_path.exists() or archive_path.is_relative_to(Path(bundle["root"])):
        raise InstallError("New separate archive path required")
    archive_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive_path, "x", zipfile.ZIP_DEFLATED, compresslevel=9) as zipped:
        for name in sorted(bundle["files"]):
            info = zipfile.ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = (0o100755 if name.startswith("bin/") else 0o100644) << 16
            data = (Path(bundle["root"]) / name).read_bytes()
            if digest(data) != bundle["files"][name]:
                raise InstallError("Codex archive input changed after inventory verification: " + name)
            zipped.writestr(info, data)
    if not craft_codex.same_content(bundle, craft_codex.bundle(bundle["root"])):
        raise InstallError("Codex archive source drift during creation")
    with zipfile.ZipFile(archive_path, "r") as zipped:
        if len(zipped.infolist()) != len(bundle["files"]) or set(zipped.namelist()) != set(bundle["files"]):
            raise InstallError("Codex produced ZIP file inventory mismatch")
        for name, expected in bundle["files"].items():
            if digest(zipped.read(name)) != expected:
                raise InstallError("Codex produced ZIP byte mismatch: " + name)
    return {"complete": True, "archive": str(archive_path), "sha256": common.sha(archive_path),
            "bytes": archive_path.stat().st_size, "manifest_sha256": common.sha(Path(bundle["root"]) / craft_codex.MANIFEST)}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("freeze", "build"):
        sub = commands.add_parser(name)
        sub.add_argument("--runtime", default=str(RUNTIME))
        sub.add_argument("--base-runtime", default=str(BASE_RUNTIME))
        if name == "build":
            for flag in ("stage", "output", "cargo", "rustc", "gcc", "objdump", "cargo-home"):
                sub.add_argument("--" + flag, required=True)
            sub.add_argument("--dll-dir", action="append", default=[])
            sub.add_argument("--upstream-mirror")
            sub.add_argument("--offline", action="store_true")
    sub = commands.add_parser("archive")
    sub.add_argument("--bundle", required=True)
    sub.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    try:
        print(json.dumps({"freeze": freeze, "build": build, "archive": archive}[args.command](args), ensure_ascii=False))
        return 0
    except (InstallError, OSError, ValueError, KeyError, TypeError) as exc:
        print(json.dumps({"complete": False, "error": str(exc)}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
