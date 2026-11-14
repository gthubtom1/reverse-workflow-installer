"""Codex Craft installation contract. Execution remains in the native Rust owner."""
import json
import os
from pathlib import Path
import re

import craft as paths
from configuration import digest, encode_json, load_json
from versions import InstallError

BACKEND_ID = "craft-codex-app-server-v1"
PERMISSION_CONTRACT = "codex-dynamic-bounded-v1"
CODEX_VERSION = "0.167.0-alpha.4.1"
CODEX_PROTOCOL = "app-server-v2"
CODEX_PROFILE_ID = "codex-stock-bounded-v1"
CODEX_PROFILE_ENTRY = "source/owned/codex-profile.json"
PROFILE_SOURCE = "adapters/craft-codex/runtime/codex-profile.json"
CONTRACT = {"name": "craft-codex-execution", "version": 1, "min_reader": 1,
            "required_capabilities": ["craft-bundle-integrity-v1", "craft-resource-ownership-v1", "craft-codex-entry-gate-v1"]}
MANIFEST = "craft-codex-bundle.json"
BUNDLE_DIRECTORY = "craft-codex-bundle"
RESOURCE_DIRECTORY = "craft-codex"
RUNTIME_KEY = "codex_runtime"
SOURCE_OPTIONS = ("craft_bundle", "craft_codex_cli")
REVERSE_DESCRIPTOR = "skills/reconstruction/references/execution-backend-codex-contract.json"
REVERSE_FILES = paths.REVERSE_FILES
REVERSE_CAPABILITIES = ["r46.accepted-research-v1", "r46.single-implementation-owner-v1",
                        "r46.bounded-codex-builder-v1", "r46.candidate-independent-acceptance-v1"]
no_links = paths.no_links
relative = paths.relative
inventory = paths.inventory
resource_identity = paths.resource_identity
same_content = paths.same_content


def gate(value):
    if not isinstance(value, dict) or type(value.get("version")) is not int or type(value.get("min_reader")) is not int or value != CONTRACT:
        raise InstallError("Craft Codex contract/min_reader/required_capabilities unsupported")


def unique_object(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise InstallError("Craft Codex duplicate JSON key")
        value[key] = item
    return value


def read_object(path):
    return json.loads(no_links(path).read_text(encoding="utf-8"), object_pairs_hook=unique_object)


def reverse_contract(root, expected=None):
    """Freeze the original runner's Codex descriptor; never grant task authority."""
    try:
        if not root:
            raise InstallError("provide --reverse-root with the qualified Codex R46 source")
        root = no_links(Path(root).expanduser().absolute()).resolve()
        descriptor_path = no_links(root / REVERSE_DESCRIPTOR)
        raw = descriptor_path.read_bytes()
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=unique_object)
        keys = {"schema_version", "contract_id", "contract_version", "min_reverse_version", "capabilities", "required_files"}
        if not isinstance(value, dict) or set(value) != keys or type(value["schema_version"]) is not int or value["schema_version"] != 1 or type(value["contract_version"]) is not int or value["contract_version"] != 1 or value["contract_id"] != "reverse.r46.codex-execution-backend":
            raise InstallError("unsupported reverse Codex descriptor schema/contract")
        caps = value["capabilities"]
        if not isinstance(caps, list) or len(caps) != len(REVERSE_CAPABILITIES) or not all(isinstance(c, str) for c in caps) or set(caps) != set(REVERSE_CAPABILITIES):
            raise InstallError("unsupported reverse Codex descriptor capabilities")
        def version(text):
            if not isinstance(text, str) or not re.fullmatch(r"(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)", text):
                raise InstallError("invalid reverse semantic version")
            return tuple(map(int, text.split(".")))
        version_bytes = no_links(root / "VERSION").read_bytes()
        actual = version_bytes.decode("utf-8").strip()
        minimum = version(value["min_reverse_version"])
        if minimum < (1, 9, 0) or version(actual) < minimum:
            raise InstallError("reverse VERSION does not meet Codex R46 minimum >=1.9.0")
        required = value["required_files"]
        if not isinstance(required, list) or len(required) != len(REVERSE_FILES):
            raise InstallError("reverse Codex descriptor requires exactly four contract files")
        hashes = {}
        for item in required:
            if not isinstance(item, dict) or set(item) != {"path", "sha256"}:
                raise InstallError("unsafe reverse Codex descriptor file entry")
            name, sha = relative(item["path"]), item["sha256"]
            if name not in REVERSE_FILES or name in hashes or not isinstance(sha, str) or not re.fullmatch(r"[0-9a-f]{64}", sha):
                raise InstallError("duplicate/unsupported reverse Codex contract file or hash")
            path = no_links(root / name)
            if not path.resolve().is_relative_to(root) or not path.is_file() or digest(path.read_bytes()) != sha:
                raise InstallError("reverse Codex contract file missing/hash drift")
            hashes[name] = sha
        identity = {"root": str(root), "descriptor": REVERSE_DESCRIPTOR, "descriptor_sha256": digest(raw),
                    "version": actual, "version_sha256": digest(version_bytes), "files": dict(sorted(hashes.items()))}
        if expected is not None and identity != expected:
            raise InstallError("reverse Codex descriptor/VERSION/contract identity drift since freeze")
        return identity
    except (InstallError, OSError, ValueError, TypeError, KeyError) as exc:
        raise InstallError("Craft Codex needs-contract: " + str(exc)) from exc


def profile_bytes(repo=None):
    """Read the reader's reviewed profile, independent of any supplied artifact."""
    if repo is not None:
        path = Path(repo) / PROFILE_SOURCE
    else:
        local = Path(__file__).resolve().with_name("codex-profile.json")
        path = local if local.exists() else Path(__file__).resolve().parents[1] / PROFILE_SOURCE
    return no_links(path).read_bytes()


def reviewed_profile():
    raw = profile_bytes()
    value = json.loads(raw.decode("utf-8"), object_pairs_hook=unique_object)
    runtime = value.get("runtime") if isinstance(value, dict) else None
    if not isinstance(value, dict) or type(value.get("schema_version")) is not int or value["schema_version"] != 1 or value.get("id") != CODEX_PROFILE_ID or not isinstance(runtime, dict) or set(runtime) != {"version", "protocol", "cli_sha256", "os", "arch"} or runtime["version"] != CODEX_VERSION or runtime["protocol"] != CODEX_PROTOCOL or runtime["os"] != "windows" or runtime["arch"] != "x86_64" or not isinstance(runtime["cli_sha256"], str) or not re.fullmatch(r"[0-9a-f]{64}", runtime["cli_sha256"]):
        raise InstallError("Craft Codex reader's reviewed stock profile is invalid")
    return raw, value


def profile_identity(component):
    """Admit only the reader's exact profile bytes, using portable frozen metadata."""
    raw, _ = reviewed_profile()
    expected = {"id": CODEX_PROFILE_ID, "path": CODEX_PROFILE_ENTRY, "sha256": digest(raw)}
    manifest = component["manifest"]
    if manifest.get("codex_profile") != expected:
        raise InstallError("Craft Codex source profile identity/hash differs from reviewed reader profile")
    if (component.get("files") or {}).get(CODEX_PROFILE_ENTRY) != expected["sha256"] or (manifest.get("files") or {}).get(CODEX_PROFILE_ENTRY) != expected["sha256"]:
        raise InstallError("Craft Codex source profile not covered by frozen file inventory")
    return expected


def bundle(root):
    root = no_links(Path(root).expanduser().absolute())
    files = inventory(root)
    manifest = read_object(root / MANIFEST)
    if not isinstance(manifest, dict) or manifest.get("name") != "craft-codex-bundle" or manifest.get("version") != "0.1.0":
        raise InstallError("Craft Codex bundle name/version unsupported")
    gate(manifest.get("contract"))
    if manifest.get("base_commit") != paths.BASE_COMMIT or manifest.get("backend_id") != BACKEND_ID or manifest.get("permission_contract") != PERMISSION_CONTRACT or "pi" in manifest or "codex_host" in manifest:
        raise InstallError("Craft Codex backend/permission/base identity unsupported")
    if manifest.get("codex") != {"version": CODEX_VERSION, "protocol": CODEX_PROTOCOL}:
        raise InstallError("Craft Codex exact CLI version/protocol unsupported; profile review required")
    expected = manifest.get("files")
    if not isinstance(expected, dict) or not expected or MANIFEST in expected:
        raise InstallError("Craft Codex complete files hash manifest required")
    for name, sha in expected.items():
        relative(name)
        if not isinstance(sha, str) or not re.fullmatch(r"[0-9a-f]{64}", sha):
            raise InstallError("Craft Codex file SHA256 invalid")
    if {k: v for k, v in files.items() if k != MANIFEST} != expected:
        raise InstallError("Craft Codex bundle inventory/hash drift")
    profile = profile_identity({"manifest": manifest, "files": files})
    if no_links(root / profile["path"]).read_bytes() != reviewed_profile()[0]:
        raise InstallError("Craft Codex source profile raw bytes differ from reviewed reader profile")
    artifact = manifest.get("artifact")
    if not isinstance(artifact, dict) or paths.host() != {"os": "windows", "arch": "x86_64"} or any(artifact.get(k) != v for k, v in {"os": "windows", "arch": "x86_64", "target": "x86_64-pc-windows-gnu", "profile": "release"}.items()):
        raise InstallError("Craft Codex artifact OS/arch/target/profile unsupported on this host")
    if not re.fullmatch(r"[0-9a-f]{40}", str(artifact.get("source_commit"))) or not isinstance(artifact.get("build_source"), str) or not artifact["build_source"].strip():
        raise InstallError("Craft Codex source_commit/build_source provenance required")
    runtime = manifest.get("runtime")
    if not isinstance(runtime, dict) or set(runtime) != {"entry", "entry_kind", "driver", "driver_kind", "entry_protocol", "required_files"} or any(runtime.get(k) != v for k, v in {"entry": "bin/craft-codex-executor.exe", "entry_kind": "native", "driver": "bin/codex-app-server-driver.exe", "driver_kind": "native"}.items()):
        raise InstallError("Craft Codex native entry/driver identity or runtime fields unsupported")
    required = runtime.get("required_files")
    if not isinstance(required, list) or not required or not all(isinstance(n, str) for n in required) or len(set(required)) != len(required):
        raise InstallError("Craft Codex required runtime files missing")
    for name in (*paths.REQUIRED, *required, runtime.get("entry_protocol"), runtime["entry"], runtime["driver"]):
        if relative(name) not in expected or (root / name).stat().st_size == 0:
            raise InstallError("Craft Codex required artifact missing/empty: " + name)
    for prefix in ("licenses/", "source/", "provenance/"):
        if not any(n.startswith(prefix) and (root / n).stat().st_size for n in expected):
            raise InstallError("Craft Codex required provenance inventory missing: " + prefix)
    return {"root": str(root.resolve()), "manifest": manifest, "files": files,
            "sha256": digest(encode_json(dict(sorted(files.items())))), "mode": "verified-local-bundle"}


def cli_identity(path):
    path = no_links(Path(path).expanduser().absolute())
    if not path.is_file() or not path.stat().st_size or (os.name == "nt" and path.suffix.lower() != ".exe") or (os.name != "nt" and not os.access(path, os.X_OK)):
        raise InstallError("Craft Codex explicit native CLI executable missing/unsupported; no PATH fallback")
    return {"path": str(path.resolve()), "sha256": digest(path.read_bytes())}


def installed_profile(receipt):
    """Verify the copied profile against the reviewed reader; no source bundle access."""
    data = receipt["craft"]
    expected = profile_identity(receipt["components"]["craft"])
    runtime = data[RUNTIME_KEY]
    if set(runtime) != {"cli", "version", "config_root", "protocol", "profile"} or runtime.get("profile") != expected:
        raise InstallError("Craft Codex runtime profile receipt identity drift")
    raw, reviewed = reviewed_profile()
    if no_links(Path(data["root"]) / expected["path"]).read_bytes() != raw:
        raise InstallError("Craft Codex installed source profile bytes drift")
    if runtime["cli"] != cli_identity(runtime["cli"]["path"]) or runtime["cli"]["sha256"] != reviewed["runtime"]["cli_sha256"]:
        raise InstallError("Craft Codex CLI binary differs from reviewed stock profile")
    return expected


def runtime_identity(selected, component, run):
    cli = cli_identity(selected["craft_codex_cli"])
    expected = component["manifest"].get("codex")
    if expected != {"version": CODEX_VERSION, "protocol": CODEX_PROTOCOL}:
        raise InstallError("Craft Codex CLI version/protocol needs profile review")
    profile = profile_identity(component)
    if cli["sha256"] != reviewed_profile()[1]["runtime"]["cli_sha256"]:
        raise InstallError("Craft Codex CLI binary differs from reviewed stock profile")
    output = run([cli["path"], "--version"], cwd=Path(cli["path"]).parent, env=entry_environment())
    if output.strip() != "codex-cli " + expected["version"] or cli_identity(cli["path"]) != cli:
        raise InstallError("Craft Codex explicit CLI --version/hash mismatch")
    return {"cli": cli, "version": expected["version"], "config_root": str(no_links(selected["agent_dir"]).resolve()),
            "protocol": expected["protocol"], "profile": profile}


def inspect_backend(receipt, run):
    """Execute only the owner metadata operation, never prepare/build/model requests."""
    command = entry_command(receipt)
    runtime = receipt["craft"][RUNTIME_KEY]
    if runtime_identity({"craft_codex_cli": runtime["cli"]["path"], "agent_dir": runtime["config_root"]}, receipt["components"]["craft"], run) != runtime:
        raise InstallError("Craft Codex CLI version drift before inspection")
    data = json.loads(run([*command, "--inspect"], cwd=Path(receipt["craft"]["root"]), env=entry_environment(receipt)))
    commands = data.get("commands") if isinstance(data, dict) else None
    if not isinstance(data, dict) or data.get("name") != "craft-codex-executor" or type(data.get("contract_version")) is not int or data["contract_version"] != 1 or data.get("backend_id") != BACKEND_ID or data.get("permission_contract") != PERMISSION_CONTRACT or not isinstance(commands, list) or not {"--inspect", "--version", "--validate", "--prepare", "--run"}.issubset(commands):
        raise InstallError("Craft Codex native owner inspection contract mismatch")
    return {k: data[k] for k in ("name", "contract_version", "backend_id", "permission_contract", "commands")}


def validate_plan(plan, entry):
    gate(plan.get("craft_contract"))
    selected = plan["scope"]
    if selected["client"] != "codex" or not {"reverse", "spec_kit", "craft"}.issubset(selected["components"]):
        raise InstallError("Craft Codex requires Codex, reverse and spec-kit")
    reverse_contract(selected.get("reverse_root"), plan.get("craft_reverse_contract") or {})
    if plan["components"]["craft"] != {**bundle(selected["craft_bundle"]), "repository": entry["repository"]}:
        raise InstallError("Craft Codex bundle root/content drift since plan")


def install_bundle(component, target, journal):
    current = bundle(component["root"])
    if not same_content(current, component) or current["root"] != component["root"]:
        raise InstallError("Craft Codex source bundle drift before copy")
    target = no_links(target)
    if target.exists():
        installed = bundle(target)
        if not same_content(installed, current):
            raise InstallError("Craft Codex isolated version directory drift")
        return installed
    source = Path(current["root"])
    for name in sorted(current["files"], key=lambda n: ((source / n).stat().st_size, n)):
        destination = no_links(target / name)
        journal.write(destination, (source / name).read_bytes())
        destination.chmod((source / name).stat().st_mode & 0o777)
    installed = bundle(target)
    if not same_content(installed, current) or not same_content(bundle(source), current):
        raise InstallError("Craft Codex bundle drift during exact copy")
    return installed


def resource_files(repo, receipt_path):
    root = no_links(Path(repo) / "adapters/craft-codex")
    result = {}
    def unreadable(error):
        raise InstallError("Craft Codex resources cannot be completely enumerated") from error
    for directory, dirs, files in os.walk(root, followlinks=False, onerror=unreadable):
        if Path(directory) == root:
            dirs[:] = [name for name in dirs if name != "runtime"]
        for name in dirs + files:
            no_links(Path(directory) / name)
        for name in files:
            source = Path(directory) / name
            if not source.is_file():
                raise InstallError("Craft Codex resource is not a regular file")
            result[relative(source.relative_to(root).as_posix())] = source.read_bytes()
    if any(name == "receipt-location.json" or name.startswith("lib/") for name in result):
        raise InstallError("Craft Codex resources collide with generated reader/pointer")
    for name in ("entry.py", "builder-instructions.md", "skills/reconstruction-execution/SKILL.md"):
        if not result.get(name):
            raise InstallError("Craft Codex execution resource missing: " + name)
    if not any(name.startswith("skills/reconstruction-execution/references/") for name in result):
        raise InstallError("Craft Codex execution references missing")
    for name in ("craft_codex.py", "craft.py", "configuration.py", "versions.py"):
        result["lib/" + name] = (Path(repo) / "scripts" / name).read_bytes()
    result["lib/codex-profile.json"] = profile_bytes(repo)
    result["receipt-location.json"] = encode_json({"receipt": str(receipt_path)})
    if len({name.casefold() for name in result}) != len(result):
        raise InstallError("Craft Codex resource case collision")
    return result


def validate_resources(plan, repo):
    current = resource_identity(resource_files(repo, Path(plan["scope"]["root"]) / ".installer/receipt.json"))
    if current != plan.get("craft_resources"):
        raise InstallError("Craft Codex execution resource source inventory/hash drift since plan")


def failures(receipt):
    try:
        gate(receipt.get("craft_contract"))
        scope, data = receipt["scope"], receipt["craft"]
        if not receipt.get("installed") or scope["client"] != "codex" or not {"craft", "reverse", "spec_kit"}.issubset(scope["components"]):
            raise InstallError("Craft Codex receipt dependency/client mismatch")
        gate(data.get("contract"))
        reverse_contract((receipt.get("reverse") or {}).get("root"), receipt.get("craft_reverse_contract") or {})
        current = bundle(data["root"])
        if not same_content(current, receipt["components"]["craft"]) or data["sha256"] != current["sha256"]:
            raise InstallError("Craft Codex installed bundle identity drift")
        version = no_links(data["root"]).parent
        if version.parent != no_links(Path(scope["root"]) / "versions") or Path(data["root"]) != version / BUNDLE_DIRECTORY or Path(data["resources"]) != version / RESOURCE_DIRECTORY or data["root"] != receipt["paths"]["craft"] or Path(data["root"]).resolve() != Path(data["root"]):
            raise InstallError("Craft Codex bundle/resources outside isolated version directory")
        resources = no_links(data["resources"])
        if inventory(resources) != data["resource_hashes"]:
            raise InstallError("Craft Codex managed execution resources drift")
        if data.get("entry") != str(resources / "entry.py") or "pi_runtime" in data:
            raise InstallError("Craft Codex receipt entry/runtime mismatch")
        runtime = data[RUNTIME_KEY]
        codex = current["manifest"]["codex"]
        if runtime["cli"] != cli_identity(runtime["cli"]["path"]) or runtime.get("protocol") != codex["protocol"] or runtime.get("config_root") != scope["agent_dir"] or runtime.get("version") != codex["version"]:
            raise InstallError("Craft Codex explicit CLI identity drift")
        installed_profile(receipt)
        if load_json(resources / "receipt-location.json") != {"receipt": str(Path(scope["root"]) / ".installer/receipt.json")}:
            raise InstallError("Craft Codex receipt pointer drift")
        return []
    except (InstallError, OSError, ValueError, KeyError, TypeError) as exc:
        return [str(exc)]


def entry_command(receipt):
    errors = failures(receipt)
    if errors:
        raise InstallError("Craft Codex entry denied: " + "; ".join(errors))
    runtime = receipt["components"]["craft"]["manifest"]["runtime"]
    return [str(Path(receipt["craft"]["root"]) / runtime["entry"])]


def entry_environment(receipt=None):
    env = paths.clean_node_env()
    for key in list(env):
        if key.startswith(("CRAFT_PI_", "CRAFT_CODEX_", "CRAFT_TOOL_POLICY", "CODEX_TOOL_POLICY", "CODEX_SERVER", "CODEX_HOST", "TOOL_POLICY")):
            env.pop(key)
    if receipt:
        data = receipt["craft"]
        runtime = data[RUNTIME_KEY]
        profile = installed_profile(receipt)
        env.update({"CRAFT_CODEX_CLI": runtime["cli"]["path"], "CRAFT_CODEX_VERSION": runtime["version"],
                    "CRAFT_CODEX_HOME": runtime["config_root"], "CODEX_HOME": runtime["config_root"],
                    "CRAFT_CODEX_CLI_SHA256": runtime["cli"]["sha256"], "CRAFT_BUNDLE_ROOT": data["root"],
                    "CRAFT_CODEX_RUNTIME_PROFILE": str(no_links(Path(data["root"]) / profile["path"])),
                    "CRAFT_CODEX_RUNTIME_PROFILE_SHA256": profile["sha256"],
                    "CRAFT_BUILDER_INSTRUCTIONS": str(Path(data["resources"]) / "builder-instructions.md")})
    return env


def update_record(previous, current):
    value = paths.update_record(previous, current)
    value["policy"] = "explicit frozen Codex native bundle; no ambient CLI or Pi fallback"
    evidence = current["manifest"]["artifact"].get("publication")
    value["publication"] = {"status": "artifact-evidence-recorded" if evidence else "pending",
                            "evidence": evidence,
                            "verification": "artifact provenance frozen; independent release-pin/remote verification belongs to publisher"}
    return value
