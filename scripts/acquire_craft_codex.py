#!/usr/bin/env python3
"""Acquire the pinned Codex Craft artifact and exact Reverse source; never install."""
import argparse
import json
from pathlib import Path
import re
import secrets
import sys

import acquire_craft as shared
import craft
import craft_codex
from build_craft_bundle import safe_extract_zip
from configuration import atomic, encode_json
from packaging_process import run_owned
from versions import InstallError

NAME = "craft-codex-windows-x64"


def validate_pin(pin):
    shared.fields(pin, "schema_version name craft reverse codex")
    if type(pin["schema_version"]) is not int or pin["schema_version"] != 1 or pin["name"] != NAME:
        raise InstallError("Unsupported Codex release pin")
    asset, reverse, codex = (pin[key] for key in ("craft", "reverse", "codex"))
    shared.fields(asset, "repository tag commit asset asset_id sha256 manifest_sha256")
    shared.fields(reverse, "repository commit descriptor_sha256")
    shared.fields(codex, "version protocol")
    if asset["repository"] != shared.OWN or asset["tag"] != "craft-codex-v0.1.0" or asset["asset"] != "craft-codex-windows-x64-0.1.0.zip" or type(asset["asset_id"]) is not int or asset["asset_id"] <= 0:
        raise InstallError("Codex artifact repository/tag/asset identity mismatch")
    if reverse["repository"] != shared.REVERSE or codex != {"version": "0.167.0-alpha.4.1", "protocol": "app-server-v2"}:
        raise InstallError("Codex source/protocol profile unsupported")
    for value in (asset["commit"], reverse["commit"]):
        shared.hex_value(value, 40)
    for value in (asset["sha256"], asset["manifest_sha256"], reverse["descriptor_sha256"]):
        shared.hex_value(value, 64)
    return pin


def checkout_reverse(record, target, stage):
    # Reuse the bounded worker's clean Git environment, not the operator's hooks/auth.
    common = ["git", "-c", "core.autocrlf=false", "-c", "core.eol=lf", "-c", "http.followRedirects=false",
              "-c", "http.version=HTTP/1.1", "-c", "core.hooksPath=" + str(stage / "empty-hooks")]
    shared.git_command([*common, "init", str(target)], stage=stage)
    for rest in (["remote", "add", "origin", record["repository"]],
                 ["fetch", "--no-tags", "--depth", "1", "origin", record["commit"]],
                 ["checkout", "--detach", "FETCH_HEAD"]):
        shared.git_command([*common, "-C", str(target), *rest], stage=stage)
    canonical = shared.canonical_files(target, record["commit"])
    checkout = shared.checkout_files(target)
    if shared.git_command([*common, "-C", str(target), "status", "--porcelain", "--untracked-files=all"], stage=stage).strip():
        raise InstallError("Reverse checkout changed after canonical Git inspection")
    return {"canonical_files": canonical, "checkout_files": checkout}


def git_bindings(root):
    return {name: shared.file_sha(craft.no_links(root / ".git" / name)) for name in ("HEAD", "config", "index")}


def revalidate_candidate(args, candidate):
    stage = craft.no_links(Path(args.stage).absolute())
    pin_path = craft.no_links(Path(args.pin_file).absolute())
    if shared.file_sha(pin_path) != candidate["pin_sha256"] or candidate["pin_sha256"] != args._pin_sha256 or validate_pin(shared.strict_json(pin_path.read_text(encoding="utf-8"))) != candidate["pin"]:
        raise InstallError("Codex acquisition pin drift since supervision preflight")
    pin, frozen = candidate["pin"], candidate["inputs"]
    cli = craft_codex.cli_identity(args.codex_cli)
    bundle_root, reverse_root = stage / "craft-archive", stage / "reverse"
    if candidate["installer_options"] != {"craft_bundle": str(bundle_root), "reverse_root": str(reverse_root), "craft_codex_cli": cli["path"]} or cli != candidate["cli"]:
        raise InstallError("Codex acquisition CLI/path drift before completion")
    if shared.file_sha(stage / pin["craft"]["asset"]) != pin["craft"]["sha256"] or shared.file_sha(bundle_root / craft_codex.MANIFEST) != pin["craft"]["manifest_sha256"] or craft_codex.bundle(bundle_root)["sha256"] != frozen["bundle_sha256"]:
        raise InstallError("Codex acquisition archive/bundle drift before completion")
    if (craft.no_links(reverse_root / ".git/HEAD").read_bytes().strip() != pin["reverse"]["commit"].encode("ascii") or craft_codex.reverse_contract(reverse_root) != candidate["reverse_contract"] or shared.checkout_files(reverse_root) != frozen["reverse_files"] or git_bindings(reverse_root) != frozen["reverse_git"]):
        raise InstallError("Codex acquisition source drift before completion")


def publish_candidate(args, candidate, supervision):
    if supervision["returncode"] or supervision["timed_out"] or supervision["cleanup"] != "verified" or supervision["had_descendants"]:
        raise InstallError("Codex acquisition failed/timed out or owned cleanup not verified; retain logs and stage")
    if candidate.get("phase") != "candidate-verified" or "complete" in candidate:
        raise InstallError("Codex acquisition worker did not return a verified candidate")
    revalidate_candidate(args, candidate)
    stage = Path(args.stage).absolute()
    result = {key: value for key, value in candidate.items() if key not in ("phase", "inputs")}
    result.update(complete=True, cleanup="verified")
    atomic(stage / "installer-options.json", encode_json(result["installer_options"]))
    # The supervisor publishes success only after Job/pipe cleanup and final byte checks.
    atomic(stage / "acquisition-result.json", encode_json(result))
    return result


def acquire(args):
    shared.require_windows()
    pin_path = craft.no_links(Path(args.pin_file).absolute())
    pin_sha = shared.file_sha(pin_path)
    if pin_sha != args._pin_sha256:
        raise InstallError("Codex acquisition pin drift since supervision preflight")
    pin = validate_pin(shared.strict_json(pin_path.read_text(encoding="utf-8")))
    stage = craft.no_links(Path(args.stage).absolute())
    shared.validate_win32_stage(stage, pin)
    if stage.exists():
        raise InstallError("Codex acquisition stage must not exist; retain failed stages")
    cli = craft_codex.cli_identity(args.codex_cli)
    _, reviewed = craft_codex.reviewed_profile()
    if cli["sha256"] != reviewed["runtime"]["cli_sha256"]:
        raise InstallError("Explicit Codex CLI bytes are not qualified by the reviewed runtime profile")
    stage.mkdir(parents=True)
    (stage / "home").mkdir()
    version = shared.git_command([cli["path"], "--version"], stage=stage).decode("utf-8").strip()
    if version != "codex-cli " + pin["codex"]["version"] or craft_codex.cli_identity(cli["path"]) != cli:
        raise InstallError("Explicit Codex CLI differs from the pinned protocol profile")
    archive = stage / pin["craft"]["asset"]
    url = pin["craft"]["repository"] + "/releases/download/" + pin["craft"]["tag"] + "/" + pin["craft"]["asset"]
    shared.transfer(url, destination=archive)
    if shared.file_sha(archive) != pin["craft"]["sha256"]:
        raise InstallError("Pinned Codex archive SHA256 mismatch")
    shared.validate_win32_stage(stage, pin, archive=archive, kind="craft")
    bundle_root = stage / "craft-archive"
    safe_extract_zip(archive, bundle_root)
    if shared.file_sha(bundle_root / craft_codex.MANIFEST) != pin["craft"]["manifest_sha256"]:
        raise InstallError("Pinned Codex bundle manifest SHA256 mismatch")
    bundle = craft_codex.bundle(bundle_root)
    if bundle["manifest"]["artifact"]["source_commit"] != pin["craft"]["commit"] or bundle["manifest"]["codex"] != pin["codex"]:
        raise InstallError("Codex bundle build source/runtime differs from public pin")
    reverse_root = stage / "reverse"
    source = checkout_reverse(pin["reverse"], reverse_root, stage)
    reverse = craft_codex.reverse_contract(reverse_root)
    if reverse["descriptor_sha256"] != pin["reverse"]["descriptor_sha256"]:
        raise InstallError("Codex Reverse descriptor differs from public pin")
    options = {"craft_bundle": str(bundle_root), "reverse_root": str(reverse_root),
               "craft_codex_cli": cli["path"]}
    result = {"phase": "candidate-verified", "name": NAME, "pin": pin, "pin_sha256": pin_sha,
              "installer_options": options, "cli": cli, "archive_sha256": shared.file_sha(archive),
              "manifest_sha256": shared.file_sha(bundle_root / craft_codex.MANIFEST),
              "reverse_contract": reverse,
              "inputs": {"bundle_sha256": bundle["sha256"], "reverse_files": source["checkout_files"],
                         "reverse_canonical_files": source["canonical_files"],
                         "reverse_git": git_bindings(reverse_root)},
              "verification": "pinned archive bytes, native bundle inventory, exact canonical Git source and CLI identity",
              "real_model_or_business_acceptance": "not performed by acquisition"}
    revalidate_candidate(args, result)
    atomic(stage / "acquisition-candidate.json", encode_json(result))
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pin-file", required=True)
    parser.add_argument("--stage", required=True)
    parser.add_argument("--codex-cli", required=True, help="Exact native CLI; no PATH/account discovery")
    parser.add_argument("--deadline-seconds", type=int, default=600)
    parser.add_argument("--_worker-token", help=argparse.SUPPRESS)
    parser.add_argument("--_pin-sha256", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    try:
        pin_path = craft.no_links(Path(args.pin_file).absolute())
        pin_sha = shared.file_sha(pin_path)
        validate_pin(shared.strict_json(pin_path.read_text(encoding="utf-8")))
        shared.validate_win32_stage(Path(args.stage).absolute(), None)
        if not 1 <= args.deadline_seconds <= 1800:
            raise InstallError("Bounded acquisition deadline must be 1..1800 seconds")
        if args._worker_token:
            if not re.fullmatch("[0-9a-f]{32}", args._worker_token) or args._pin_sha256 != pin_sha:
                raise InstallError("Invalid worker identity or frozen pin drift")
            print(json.dumps(acquire(args), ensure_ascii=False))
            return 0
        shared.require_windows()
        token = secrets.token_hex(16)
        args._pin_sha256 = pin_sha
        command = [sys.executable, "-B", str(Path(__file__).resolve()), "--pin-file", str(Path(args.pin_file).absolute()),
                   "--stage", str(Path(args.stage).absolute()), "--codex-cli", str(Path(args.codex_cli).absolute()),
                   "--deadline-seconds", str(args.deadline_seconds), "--_worker-token", token, "--_pin-sha256", pin_sha]
        result = run_owned(command, cwd=Path(__file__).resolve().parents[1],
                           env=shared.clean_env(Path(args.stage).absolute()), timeout=args.deadline_seconds,
                           log_prefix=Path(args.stage).absolute().parent / ("codex-acquire-" + token))
        if result["returncode"] or result["timed_out"] or result["cleanup"] != "verified" or result["had_descendants"]:
            raise InstallError("Codex acquisition failed/timed out or owned cleanup not verified; retain logs and stage")
        candidate = shared.strict_json(result["stdout"])
        output = publish_candidate(args, candidate, result)
        print(json.dumps(output, ensure_ascii=False))
        return 0
    except (InstallError, OSError, ValueError, KeyError, TypeError) as exc:
        print(json.dumps({"complete": False, "error": str(exc)}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
