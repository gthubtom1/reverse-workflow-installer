"""Craft's opt-in package contract and file mechanics; no runtime or provider setup."""
import copy
import json
import os
from pathlib import Path, PurePosixPath
import platform
import re
from urllib.parse import urlparse

from configuration import digest, encode_json, load_json
from versions import InstallError, stable

BASE_COMMIT = "0326b4de8051f85a0f3139cd82f88f76911e6a35"
PACKAGE_NAME = "reverse-workflow-craft-pi"
CONTRACT = {"name": "craft-pi-execution", "version": 1, "min_reader": 1,
            "required_capabilities": ["craft-bundle-integrity-v1", "craft-resource-ownership-v1", "craft-entry-gate-v1"]}
MANIFEST = "craft-bundle.json"
REQUIRED = ("Cargo.lock", "LICENSE-MIT", "LICENSE-APACHE", "ATTRIBUTION.md", "THIRD_PARTY_NOTICES.md")
REVERSE_DESCRIPTOR = "skills/reconstruction/references/execution-backend-contract.json"
REVERSE_FILES = ("skills/reconstruction/references/execution-backend.md", "skills/reconstruction/SKILL.md",
                 "skills/ops/role-map.md", "skills/reconstruction/references/spec-kit-workflow.md")
REVERSE_CAPABILITIES = ["r46.accepted-research-v1", "r46.single-implementation-owner-v1",
                        "r46.bounded-pi-builder-v1", "r46.candidate-independent-acceptance-v1"]


def reverse_contract(root, expected=None):
    """Qualify R46's machine descriptor; it grants no task scope or acceptance authority."""
    try:
        if not root:
            raise InstallError("provide --reverse-root with the qualified R46 source; default release is not certified")
        root = no_links(Path(root).expanduser().absolute()).resolve()
        descriptor_path = no_links(root / REVERSE_DESCRIPTOR)
        raw = descriptor_path.read_bytes()

        def unique(pairs):
            obj = {}
            for key, value in pairs:
                if key in obj:
                    raise InstallError("duplicate descriptor JSON key")
                obj[key] = value
            return obj

        value = json.loads(raw.decode("utf-8"), object_pairs_hook=unique)
        keys = {"schema_version", "contract_id", "contract_version", "min_reverse_version", "capabilities", "required_files"}
        if not isinstance(value, dict) or set(value) != keys or type(value["schema_version"]) is not int or value["schema_version"] != 1 or type(value["contract_version"]) is not int or value["contract_version"] != 1 or value["contract_id"] != "reverse.r46.execution-backend":
            raise InstallError("unsupported reverse descriptor schema/contract")
        capabilities = value["capabilities"]
        if not isinstance(capabilities, list) or len(capabilities) != 4 or not all(isinstance(cap, str) for cap in capabilities) or set(capabilities) != set(REVERSE_CAPABILITIES):
            raise InstallError("unsupported reverse descriptor capabilities")

        def version(text):
            if not isinstance(text, str) or not re.fullmatch(r"(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)", text):
                raise InstallError("invalid reverse semantic version")
            return tuple(map(int, text.split(".")))

        version_bytes = no_links(root / "VERSION").read_bytes()
        actual_version = version_bytes.decode("utf-8").strip()
        minimum = version(value["min_reverse_version"])
        if minimum < (1, 9, 0) or version(actual_version) < minimum:
            raise InstallError("reverse VERSION does not meet R46 minimum >=1.9.0")
        required = value["required_files"]
        if not isinstance(required, list) or len(required) != len(REVERSE_FILES):
            raise InstallError("reverse descriptor requires exactly four contract files")
        hashes = {}
        for item in required:
            if not isinstance(item, dict) or set(item) != {"path", "sha256"}:
                raise InstallError("unsafe reverse descriptor file entry")
            name = relative(item["path"])
            sha = item["sha256"]
            if name not in REVERSE_FILES or name in hashes or not isinstance(sha, str) or not re.fullmatch(r"[0-9a-f]{64}", sha):
                raise InstallError("duplicate/unsupported reverse contract file or hash")
            path = no_links(root / name)
            if not path.resolve().is_relative_to(root) or not path.is_file() or digest(path.read_bytes()) != sha:
                raise InstallError("reverse contract file missing/hash drift")
            hashes[name] = sha
        identity = {"root": str(root), "descriptor": REVERSE_DESCRIPTOR, "descriptor_sha256": digest(raw),
                    "version": actual_version, "version_sha256": digest(version_bytes),
                    "files": dict(sorted(hashes.items()))}
        if expected is not None and identity != expected:
            raise InstallError("reverse descriptor/VERSION/contract identity drift since freeze")
        return identity
    except (InstallError, OSError, ValueError, TypeError, KeyError) as exc:
        raise InstallError("Craft needs-contract: " + str(exc)) from exc



def gate(value):
    if not isinstance(value, dict) or type(value.get("version")) is not int or type(value.get("min_reader")) is not int or value != CONTRACT:
        raise InstallError("Craft contract/min_reader/required_capabilities unsupported")


def no_links(path):
    path = Path(path).absolute()
    if any(p.is_symlink() or getattr(p, "is_junction", lambda: False)() for p in (path, *path.parents)):
        raise InstallError("Craft path contains symlink/junction")
    return path


def relative(name):
    if not isinstance(name, str) or not name or "\\" in name or ":" in name:
        raise InstallError("Craft file path must be a canonical relative POSIX path")
    p = PurePosixPath(name)
    if p.is_absolute() or p.as_posix() != name or any(x in (".", "..") for x in p.parts):
        raise InstallError("Craft file path escapes bundle")
    if any(x.rstrip(". ") != x or x.casefold() in (".git", ".installer") for x in p.parts):
        raise InstallError("Craft reserved file path")
    return name


def host():
    arch = {"amd64": "x86_64", "x86_64": "x86_64", "arm64": "aarch64", "aarch64": "aarch64"}.get(platform.machine().lower())
    return {"os": platform.system().lower(), "arch": arch}


def inventory(root, *, forbidden=()):
    root = no_links(root)
    if not root.is_dir():
        raise InstallError("Craft bundle directory missing")
    found, folded = {}, set()
    # os.walk does not traverse directory symlinks; reject every entry before reading.
    def unreadable(error):
        raise InstallError("Craft tree cannot be completely enumerated") from error
    for directory, dirs, files in os.walk(root, followlinks=False, onerror=unreadable):
        for name in dirs + files:
            p = no_links(Path(directory) / name)
            if name.casefold() in forbidden:
                raise InstallError("Craft runtime tree contains forbidden profile/secret/backup path")
            rel = relative(p.relative_to(root).as_posix())
            if rel.casefold() in folded:
                raise InstallError("Craft case-colliding file paths")
            folded.add(rel.casefold())
            if p.is_file():
                found[rel] = digest(p.read_bytes())
            elif not p.is_dir():
                raise InstallError("Craft bundle contains non-regular file")
    return found


def bundle(root):
    root = no_links(Path(root).expanduser().absolute())
    files = inventory(root)
    manifest = load_json(root / MANIFEST)
    if not isinstance(manifest, dict) or manifest.get("name") != "craft-pi-bundle" or not stable(str(manifest.get("version", ""))):
        raise InstallError("Craft bundle name/version missing or unsupported")
    gate(manifest.get("contract"))
    pi = manifest.get("pi")
    if not isinstance(pi, dict) or not stable(str(pi.get("version", ""))) or pi.get("protocol") != "rpc":
        raise InstallError("Craft bundle requires exact Pi version and rpc protocol")
    if manifest.get("base_commit") != BASE_COMMIT:
        raise InstallError("Craft base_commit unsupported; staged patch compatibility review required")
    expected = manifest.get("files")
    if not isinstance(expected, dict) or not expected or MANIFEST in expected:
        raise InstallError("Craft files hash manifest missing")
    for name, sha in expected.items():
        relative(name)
        if not isinstance(sha, str) or not re.fullmatch(r"[0-9a-f]{64}", sha):
            raise InstallError("Craft file SHA256 invalid")
    if {k: v for k, v in files.items() if k != MANIFEST} != expected:
        raise InstallError("Craft bundle file inventory/hash drift (missing, added or edited file)")
    artifact = manifest.get("artifact")
    if not isinstance(artifact, dict):
        raise InstallError("Craft artifact identity must be an object")
    if any(artifact.get(k) != v or v is None for k, v in host().items()):
        raise InstallError("Craft artifact OS/arch unsupported on this host")
    if not re.fullmatch(r"[0-9a-f]{40}", str(artifact.get("source_commit"))) or not isinstance(artifact.get("build_source"), str) or not artifact["build_source"].strip():
        raise InstallError("Craft artifact source_commit/build_source required")
    runtime = manifest.get("runtime")
    if not isinstance(runtime, dict):
        raise InstallError("Craft runtime must be an object")
    required = runtime.get("required_files")
    if not isinstance(required, list) or not required or not all(isinstance(x, str) for x in required) or len(set(required)) != len(required):
        raise InstallError("Craft required runtime files missing")
    for name in (*REQUIRED, *required, runtime.get("entry_protocol"), runtime.get("entry"), runtime.get("driver")):
        if relative(name) not in expected:
            raise InstallError("Craft required artifact missing: " + name)
    for key in ("entry", "driver"):
        p = root / runtime[key]
        kind = runtime.get(key + "_kind")
        if kind not in ("native", "python") or p.stat().st_size == 0:
            raise InstallError("Craft runtime entry/driver kind must be native or python")
        if kind == "python" and p.suffix != ".py":
            raise InstallError("Craft portable Python entry must reference a .py artifact")
        if kind == "native" and ((os.name == "nt" and p.suffix.lower() != ".exe") or (os.name != "nt" and not os.access(p, os.X_OK))):
            raise InstallError("Craft native entry/driver must be executable")
    patches = manifest.get("patches")
    if not isinstance(patches, list) or not patches:
        raise InstallError("Craft ordered patch hashes required")
    seen = set()
    for patch in patches:
        if not isinstance(patch, dict) or relative(patch.get("path")) not in expected or patch.get("sha256") != expected[patch["path"]] or patch["path"] in seen:
            raise InstallError("Craft patch identity invalid")
        seen.add(patch["path"])
    return {"root": str(root.resolve()), "manifest": manifest, "files": files,
            "sha256": digest(encode_json(dict(sorted(files.items())))), "mode": "verified-local-bundle"}


def same_content(a, b):
    return all(a.get(k) == b.get(k) for k in ("manifest", "files", "sha256", "mode"))


def validate_plan(plan, entry):
    gate(plan.get("craft_contract"))
    selected = plan["scope"]
    if selected["client"] != "pi" or not {"reverse", "spec_kit", "craft"}.issubset(selected["components"]):
        raise InstallError("Craft requires explicitly selected Pi, reverse and spec-kit")
    reverse_contract(selected.get("reverse_root"), plan.get("craft_reverse_contract") or {})
    frozen = plan["components"]["craft"]
    current = bundle(selected["craft_bundle"])
    if frozen != {**current, "repository": entry["repository"]}:
        raise InstallError("Craft bundle root/content drift since plan")


def install_bundle(component, target, journal):
    current = bundle(component["root"])
    if not same_content(current, component) or current["root"] != component["root"]:
        raise InstallError("Craft source bundle drift before copy")
    target = no_links(target)
    if target.exists():
        installed = bundle(target)
        if not same_content(installed, current):
            raise InstallError("Craft isolated version directory drift")
        return installed
    # Keep large native bytes out of the cumulative recovery journal until last.
    # Journal.write still persists every entry before mutating its destination.
    source = Path(current["root"])
    for name in sorted(current["files"], key=lambda name: ((source / name).stat().st_size, name)):
        destination = target / name
        journal.write(destination, (Path(current["root"]) / name).read_bytes())
        # Unix executable bits are part of runtime eligibility, not content hashes.
        destination.chmod((Path(current["root"]) / name).stat().st_mode & 0o777)
    installed = bundle(target)
    if not same_content(installed, current) or not same_content(bundle(current["root"]), current):
        raise InstallError("Craft bundle drift during exact copy")
    return installed


def registration(settings, agent, allowed):
    if not isinstance(settings, dict) or any(not isinstance(settings.get(k, []), list) for k in ("packages", "skills", "extensions", "prompts")):
        raise InstallError("Craft Pi settings resource fields must be arrays")
    from_path = lambda value: value.get("source") if isinstance(value, dict) else value
    found = []
    for value in settings.get("packages", []):
        source = from_path(value)
        if not isinstance(source, str):
            raise InstallError("Craft Pi package source invalid")
        if source.startswith(("npm:", "git:", "https:", "github:")) or (not Path(source).is_absolute() and not source.startswith((".", "~")) and not (Path(agent) / source).exists()):
            if PACKAGE_NAME in source:
                raise InstallError("Craft remote package registration conflicts with owned package")
            continue
        p = Path(source).expanduser()
        if not p.is_absolute():
            p = Path(agent) / p
        p = p.resolve()
        known = any(p == Path(x).resolve() for x in allowed if x)
        package = load_json(p / "package.json", {}) if (p / "package.json").is_file() else {}
        if known or package.get("name") == PACKAGE_NAME or PACKAGE_NAME in source or any(Path(x).resolve().is_relative_to(p) for x in allowed if x):
            if not known or (isinstance(value, dict) and set(value) != {"source"}):
                raise InstallError("Craft duplicate/filtered/foreign/parent package registration")
            found.append(value)
    if len(found) > 1:
        raise InstallError("Craft duplicate package registration")
    # The package owns the skill: direct resource registrations would load it twice.
    for key in ("skills", "extensions", "prompts"):
        for value in settings.get(key, []):
            source = from_path(value)
            if isinstance(source, str) and ("reconstruction-execution" in source or PACKAGE_NAME in source or any(str(x) in source for x in allowed if x)):
                raise InstallError("Craft direct resource registration conflicts with owned package")
    return found


def merge_settings(settings, agent, previous, wanted):
    result = copy.deepcopy(settings)
    old = (previous.get("craft") or {}).get("resources")
    found = registration(result, agent, (old, wanted))
    if old and not found:
        raise InstallError("Craft managed package registration missing")
    packages = result.setdefault("packages", [])
    if found:
        packages.remove(found[0])
    packages.append(str(wanted))
    replacements = [{"before": found[0] if found else None, "after": str(wanted)}] if not found or found[0] != str(wanted) else []
    return result, replacements


def failures(receipt):
    errors = []
    try:
        gate(receipt.get("craft_contract"))
        reverse_contract((receipt.get("reverse") or {}).get("root"), receipt.get("craft_reverse_contract") or {})
        data = receipt["craft"]
        gate(data.get("contract"))
        frozen = receipt["components"]["craft"]
        current = bundle(data["root"])
        if not same_content(current, frozen) or data["sha256"] != current["sha256"]:
            raise InstallError("Craft installed bundle identity drift")
        scope = receipt["scope"]
        if scope["client"] != "pi" or not {"craft", "reverse", "spec_kit"}.issubset(scope["components"]):
            raise InstallError("Craft receipt dependency mismatch")
        version = Path(data["root"]).parent
        if not version.is_relative_to(Path(scope["root"]) / "versions") or Path(data["resources"]) != version / "craft-pi":
            raise InstallError("Craft installed package/resources are outside isolated version directory")
        if data["root"] != receipt["paths"]["craft"] or Path(data["root"]).resolve() != Path(data["root"]):
            raise InstallError("Craft installed bundle root mismatch")
        resources = no_links(data["resources"])
        actual = inventory(resources)
        expected = data["resource_hashes"]
        if actual != expected:
            raise InstallError("Craft managed execution resources drift")
        pi = data["pi_runtime"]
        if pi["version"] != frozen["manifest"]["pi"]["version"]:
            raise InstallError("Craft Pi version contract mismatch")
        for key in ("node", "entry"):
            item = pi[key]
            no_links(item["path"])
            if digest(Path(item["path"]).read_bytes()) != item["sha256"]:
                raise InstallError("Craft explicit Pi runtime identity drift")
        distribution = pi_distribution(pi["distribution"]["root"], pi["version"], pi["entry"]["path"])
        if distribution != pi["distribution"]:
            raise InstallError("Craft Pi distribution/dependency load tree drift")
        locator = load_json(resources / "receipt-location.json")
        if locator != {"receipt": str(Path(scope["root"]) / ".installer/receipt.json")}:
            raise InstallError("Craft receipt pointer drift")
        settings = load_json(Path(scope["agent_dir"]) / "settings.json", {})
        if len(registration(settings, scope["agent_dir"], (resources,))) != 1:
            raise InstallError("Craft unique package registration missing")
    except (InstallError, OSError, ValueError, KeyError, TypeError) as exc:
        errors.append(str(exc))
    return errors


def update_record(previous, current):
    old = (previous.get("components") or {}).get("craft")
    return {"policy": "pinned-compatible-patch-assets; never official latest",
            "old": {k: old[k] for k in ("sha256", "manifest")} if old else None,
            "candidate": {k: current[k] for k in ("sha256", "manifest")},
            "source_ref": current["root"], "stage": "isolated-version-directory",
            "runtime_qualification": "unverified", "publication": "candidate artifact; publication status must be checked from the current release pin"}


def pinned_release(record, fetch):
    """Resolve our published artifact pin; upstream Craft provenance stays separate."""
    from acquire_craft import resolve_pin
    return {**resolve_pin(record, fetch), "status": "metadata-verified; download/package compatibility unverified"}


def pi_runtime(selected, component, run):
    """Explicit standalone runtime, never an ambient PATH pi or personal profile."""
    result = {}
    expected = component["manifest"]["pi"]["version"]
    if selected.get("craft_pi_version") != expected:
        raise InstallError("Craft explicit Pi version does not match bundle contract")
    for key, option in (("node", "craft_pi_node"), ("entry", "craft_pi_entry")):
        path = no_links(selected[option])
        if not path.is_file() or not path.stat().st_size:
            raise InstallError("Craft explicit Pi runtime file missing: " + key)
        result[key] = {"path": str(path.resolve()), "sha256": digest(path.read_bytes())}
    distribution = pi_distribution(selected["craft_pi_distribution"], expected, result["entry"]["path"])
    env = clean_node_env()
    version = run([result["node"]["path"], result["entry"]["path"], "--version"], cwd=Path(selected["craft_pi_distribution"]), env=env)
    # Accept only the CLI's exact version line, not arbitrary matching output.
    if version.strip() != expected:
        raise InstallError("Craft standalone Pi --version mismatch")
    return {**result, "distribution": distribution, "version": expected, "protocol": "rpc", "qualification": "unverified: version probe and frozen distribution only; no provider request"}


def resource_files(repo, receipt_path):
    root = Path(repo) / "adapters/craft-pi"
    # Runtime execution resources are deliberately kept separate from the
    # build/source archive under adapters/craft-pi/runtime. The installed
    # resource package needs the entry, instructions, references, skills and
    # generated reader only; build/debug/qualification helpers belong to the
    # bundle source manifest, not the every-run resource inventory.
    result = {name: (root / name).read_bytes()
              for name in inventory(root)
              if name != "runtime" and not name.startswith("runtime/")}
    if any(name == "receipt-location.json" or name.startswith("lib/") for name in result):
        raise InstallError("Craft adapter source collides with generated reader/pointer resources")
    for name in ("craft.py", "configuration.py", "versions.py"):
        result["lib/" + name] = (Path(repo) / "scripts" / name).read_bytes()
    result["receipt-location.json"] = encode_json({"receipt": str(receipt_path)})
    return result


def resource_identity(files):
    hashes = {name: digest(data) for name, data in files.items()}
    return {"files": hashes, "sha256": digest(encode_json(dict(sorted(hashes.items()))))}


def validate_resources(plan, repo):
    expected = plan.get("craft_resources")
    current = resource_identity(resource_files(repo, Path(plan["scope"]["root"]) / ".installer/receipt.json"))
    if not expected or current != expected:
        raise InstallError("Craft execution resource source inventory/hash drift since plan")


def clean_node_env():
    env = os.environ.copy()
    env.pop("NODE_OPTIONS", None)
    env.pop("NODE_PATH", None)
    return env


def pi_distribution(root, version, entry):
    """Read only an explicit standalone distribution, never an ambient runtime tree.

    Its packaging manifest asserts a reviewed self-contained Node dependency closure.
    We check the whole declared tree and reject unresolved declared dependencies.
    This is a content identity check, not authentication or an OS import sandbox.
    """
    root = no_links(Path(root).expanduser().absolute())
    # Refuse before traversal if this is not a deliberately packaged distribution.
    manifest_path = root / "pi-runtime.json"
    no_links(manifest_path)
    value = load_json(manifest_path)
    if not isinstance(value, dict) or value.get("schema_version") != 1 or value.get("name") != "official-pi-standalone" or value.get("version") != version or value.get("dependency_closure") != "self-contained-node-modules-v1":
        raise InstallError("Craft Pi runtime unsupported: complete reviewed standalone distribution manifest required")
    package = root / relative(value.get("package_root"))
    dependencies = root / relative(value.get("dependency_root"))
    expected_entry = root / relative(value.get("entry"))
    if dependencies != root / "node_modules" or not package.is_relative_to(dependencies) or expected_entry != package / "dist/bundle/cli.js" or expected_entry.resolve() != Path(entry).resolve():
        raise InstallError("Craft Pi distribution package/dependency/entry roots unsupported")
    expected = value.get("files")
    if not isinstance(expected, dict) or not expected or "pi-runtime.json" in expected:
        raise InstallError("Craft Pi distribution complete files/hash manifest required")
    for name, sha in expected.items():
        relative(name)
        if not isinstance(sha, str) or not re.fullmatch(r"[0-9a-f]{64}", sha):
            raise InstallError("Craft Pi distribution file SHA256 invalid")
    found = inventory(root, forbidden={"auth.json", "mcp.json", "settings.json", "credentials.json", ".env", "backups"})
    if {k: v for k, v in found.items() if k != "pi-runtime.json"} != expected:
        raise InstallError("Craft Pi distribution/dependency file inventory/hash drift")
    identity = load_json(package / "package.json")
    if not isinstance(identity, dict) or identity.get("name") != "@earendil-works/pi-coding-agent" or identity.get("version") != version:
        raise InstallError("Craft Pi package name/version mismatch")
    for name in found:
        path = root / name
        if path.name != "package.json" or not path.is_relative_to(dependencies):
            continue
        package_dir = path.parent
        installed_package = package_dir.parent.name == "node_modules" or (package_dir.parent.name.startswith("@") and package_dir.parent.parent.name == "node_modules")
        if not installed_package:
            continue  # Embedded examples/templates are not installed Node packages.
        pkg = load_json(path)
        if not isinstance(pkg, dict):
            raise InstallError("Craft Pi dependency package metadata invalid")
        required = pkg.get("dependencies", {})
        if not isinstance(required, dict):
            raise InstallError("Craft Pi dependency declarations invalid")
        for dep in required:
            if not re.fullmatch(r"(?:@[A-Za-z0-9_.-]+/)?[A-Za-z0-9_.-]+", dep) or dep in (".", ".."):
                raise InstallError("Craft Pi dependency name unsupported")
            current = path.parent
            resolved = None
            while current.is_relative_to(root):
                candidate = current / "node_modules" / dep / "package.json"
                if current.name != "node_modules" and candidate.is_file():
                    resolved = candidate
                    break
                if current == root:
                    break
                current = current.parent
            if resolved is None or not resolved.is_relative_to(dependencies):
                raise InstallError("Craft Pi dependency closure unresolved/outside distribution: " + dep)
    return {"root": str(root.resolve()), "manifest": value, "files": found,
            "sha256": digest(encode_json(dict(sorted(found.items()))))}


def entry_command(receipt):
    errors = failures(receipt)
    if errors:
        raise InstallError("Craft entry denied: " + "; ".join(errors))
    data = receipt["craft"]
    runtime = receipt["components"]["craft"]["manifest"]["runtime"]
    path = str(Path(data["root"]) / runtime["entry"])
    import sys
    return [sys.executable, "-B", path] if runtime["entry_kind"] == "python" else [path]

