"""Bounded upstream Skill discovery and Codex native routing ownership.

This is a static resource control, not proof of model routing behavior.
"""
import copy
import json
import os
from pathlib import Path
import re
import stat
import tomllib

from configuration import _toml_structure, digest
from versions import InstallError

KNOWN = frozenset(("craft-anything", "rea", "rea-agents"))
OWNER = "reverse.native-router"


def host_status(selected):
    if "reverse" not in selected.get("components", ["reverse"]):
        return "not-selected"
    return {"codex": "native-skill-controls; static-only",
            "pi": "configured-resource-exclusions-only; static-only"}.get(selected.get("client"), "native-routing-adapter-not-implemented; not-qualified")


def _user_home():
    # Private fixture seam: arbitrary CODEX_HOME still uses the actual user's
    # shared root in production, without asking tests to inspect that profile.
    return Path.home()


def no_links(path):
    path = Path(path).expanduser().absolute()
    if ".." in path.parts:
        raise InstallError(f"Skill path contains parent traversal: {path}")
    for part in [*reversed(path.parents), path]:
        try:
            info = part.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
            raise InstallError(f"Skill symlink/reparse path refused: {part}")
    return path


def skill_identity(path):
    path = no_links(path)
    try:
        regular = stat.S_ISREG(path.stat().st_mode)
    except OSError as exc:
        raise InstallError(f"Expected readable regular SKILL.md: {path}") from exc
    if path.name != "SKILL.md" or not regular:
        raise InstallError(f"Expected readable regular SKILL.md: {path}")
    try:
        data = path.read_bytes()
        text = data.decode("utf-8-sig")
    except (OSError, UnicodeError) as exc:
        raise InstallError(f"Unreadable SKILL.md: {path}") from exc
    match = re.match(r"\A---\r?\n(.*?)\r?\n---(?:\r?\n|$)", text, re.S)
    names = re.findall(r"(?m)^name:[ \t]*([^\r\n]+?)[ \t]*$", match[1]) if match else []
    identity = re.fullmatch(r'''(?:([a-zA-Z0-9_-]+)|"([a-zA-Z0-9_-]+)"|'([a-zA-Z0-9_-]+)')(?:[ \t]+#.*)?''', names[0]) if len(names) == 1 else None
    name = next((value for value in identity.groups() if value is not None), None) if identity else None
    return {"path": str(path.resolve()), "name": name, "sha256": digest(data)}


def codex_roots(selected):
    agent = Path(selected["agent_dir"])
    roots = [agent / "skills", Path(selected.get("codex_skills_root") or agent / "skills"), _user_home() / ".agents/skills"]
    if agent.name.lower() == ".codex":
        roots.append(agent.parent / ".agents/skills")
    if selected.get("project"):
        roots.append(Path(selected["project"]) / ".agents/skills")
    return sorted({str(no_links(p).resolve()) for p in roots})


def scan(roots):
    found = {}
    budget = 4096
    for raw in roots:
        root = no_links(raw)
        if not root.exists():
            continue
        if not root.is_dir():
            raise InstallError(f"Codex native Skills root is not a directory: {root}")
        pending = [(root, 0)]
        while pending:
            directory, depth = pending.pop()
            entry = no_links(directory / "SKILL.md")
            if entry.exists():
                identity = skill_identity(entry)
                if identity["name"] in KNOWN:
                    found[identity["path"]] = identity
                elif directory.name in KNOWN:
                    raise InstallError(f"Known upstream Skill has unsupported identity: {entry}")
                # Native Skill attachments are not nested Skill collections.
                # Do not walk references/scripts/data after reading identity.
                continue
            for item in sorted(directory.iterdir()):
                budget -= 1
                if budget < 0:
                    raise InstallError("Codex native Skills inventory exceeds bounded scan limit")
                no_links(item)
                if item.is_dir():
                    if item.name in (".git", ".cache", "__pycache__", "plugins", "cache"):
                        continue
                    if depth >= 4:
                        raise InstallError(f"Codex native Skills nesting exceeds bounded scan: {item}")
                    pending.append((item, depth + 1))
    return [found[key] for key in sorted(found)]


def config_entries(data):
    try:
        parsed = tomllib.loads(data.decode("utf-8"))
    except (ValueError, UnicodeError) as exc:
        raise InstallError("Invalid Codex native skills config TOML") from exc
    skills = parsed.get("skills", {})
    if not isinstance(skills, dict):
        raise InstallError("Unsupported Codex skills structure")
    entries = skills.get("config", [])
    if not isinstance(entries, list):
        raise InstallError("Unsupported Codex skills.config structure")
    indexed = {}
    for entry in entries:
        if not isinstance(entry, dict) or not isinstance(entry.get("path"), str):
            raise InstallError("Unsupported Codex skills.config entry")
        raw = Path(entry["path"])
        if not raw.is_absolute() or ".." in raw.parts:
            raise InstallError("Codex skills.config requires exact absolute paths")
        key = os.path.normcase(str(raw.resolve()))
        if key in indexed:
            raise InstallError(f"Duplicate Codex skills.config path: {entry['path']}")
        if "enabled" in entry and type(entry["enabled"]) is not bool:
            raise InstallError("Unsupported Codex skills.config enabled value")
        indexed[key] = entry
    return parsed, indexed


def path_key(path):
    return os.path.normcase(str(Path(path).resolve()))


def config_bytes(selected):
    path = no_links(selected.get("client_config") or Path(selected["agent_dir"]) / "config.toml")
    if path.exists() and not path.is_file():
        raise InstallError(f"Codex config is not a regular file: {path}")
    return path.read_bytes() if path.exists() else b""


def table_spans(text):
    headers, _ = _toml_structure(text)
    result = {}
    for start, end in zip(headers, [*headers[1:], len(text)]):
        chunk = text[start:end]
        header = chunk.split("\n", 1)[0].rstrip("\r")
        if re.fullmatch(r"[ \t]*\[\[skills\.config\]\][ \t]*(?:#.*)?", header):
            _, entries = config_entries(chunk.encode())
            if len(entries) != 1:
                raise InstallError("Unsupported Codex Skill table")
            result[next(iter(entries))] = (start, end, chunk)
    return result


def disable(data, paths):
    """Change only simple native table spans; verify full TOML semantics."""
    original, entries = config_entries(data)
    expected = copy.deepcopy(original)
    text = data.decode("utf-8")
    changes = []
    appended = []
    spans = table_spans(text)
    newline = "\r\n" if "\r\n" in text else "\n"
    for path in paths:
        key = path_key(path)
        entry = entries.get(key)
        if entry and entry.get("enabled") is False:
            continue
        if entry is not None:
            if key not in spans or entry.get("enabled") is not True:
                raise InstallError(f"Unsupported Skill disable spelling; refusing to guess: {path}")
            start, end, chunk = spans[key]
            pattern = r"(?m)^([ \t]*enabled[ \t]*=[ \t]*)true([ \t]*(?:#[^\r\n]*)?\r?)$"
            changed, count = re.subn(pattern, r"\g<1>false\2", chunk)
            if count != 1:
                raise InstallError(f"Unsupported Skill enabled spelling: {path}")
            changes.append((start, end, changed))
            target = next(e for e in expected["skills"]["config"] if path_key(e["path"]) == key)
            target["enabled"] = False
        else:
            expected.setdefault("skills", {}).setdefault("config", []).append({"path": path, "enabled": False})
            appended.append(newline + "[[skills.config]]" + newline + "path = " + json.dumps(path, ensure_ascii=False) + newline + "enabled = false" + newline)
    for start, end, changed in sorted(changes, reverse=True):
        text = text[:start] + changed + text[end:]
    if appended:
        text += (newline if text and not text.endswith("\n") else "") + "".join(appended)
    result = text.encode("utf-8")
    if config_entries(result)[0] != expected:
        raise InstallError("Skill disable would change unrelated Codex TOML semantics")
    return result


def plan(selected, explicit=(), previous=None):
    if selected.get("client") != "codex" or "reverse" not in selected.get("components", []):
        return None
    previous = previous or {}
    roots = sorted(set(codex_roots(selected)) | set(previous.get("scan_roots") or []))
    inventory = scan(roots)
    by_path = {item["path"]: item for item in inventory}
    chosen = set()
    for raw in explicit:
        p = Path(raw).expanduser()
        if not p.is_absolute():
            raise InstallError(f"--exclude-workflow-skill requires exact absolute SKILL.md: {p}")
        identity = skill_identity(p)
        path = identity["path"]
        if identity["name"] not in KNOWN or path not in by_path:
            raise InstallError(f"--exclude-workflow-skill is outside native roots or not a known upstream Skill: {p}")
        chosen.add(path)
    _, entries = config_entries(config_bytes(selected))
    old = {item["path"]: item for item in previous.get("disabled_skills", [])}
    records = []
    for item in inventory:
        path = item["path"]
        disabled = (entries.get(path_key(path)) or {}).get("enabled") is False
        if not disabled and path not in chosen:
            raise InstallError(f"Active upstream workflow Skill conflicts with reverse: {path}; use --exclude-workflow-skill \"{path}\"")
        owned = old.get(path, {}).get("ownership") == "installer" and disabled
        records.append({**item, "native_disabled": disabled, "ownership": "installer" if owned or (not disabled and path in chosen) else "external"})
    # Preflight unsupported syntax before any package/setup command.
    disable(config_bytes(selected), [item["path"] for item in records])
    return {"route_owner": OWNER, "scan_roots": roots, "disabled_skills": records,
            "upstream_craft": "tool companion; not a qualified R46 backend",
            "assurance": "static native Skill controls only; host/model routing unverified"}


def validate(frozen, selected, explicit=(), previous=None):
    current = plan(selected, explicit, previous)
    if frozen is None:
        if current and current["disabled_skills"]:
            raise InstallError("Legacy plan lacks routing ownership inventory; regenerate plan")
    elif current != frozen:
        raise InstallError("Routing ownership source/inventory drift since plan; regenerate plan")
    return current


def activated(record):
    result = copy.deepcopy(record)
    if result:
        for item in result["disabled_skills"]:
            item["native_disabled"] = True
    return result


def failures(receipt):
    selected = receipt.get("scope") or {}
    if selected.get("client") != "codex" or "reverse" not in selected.get("components", ["reverse"]):
        return []
    selected = {**selected, "components": ["reverse"]}
    stored = receipt.get("routing_ownership")
    try:
        current = plan(selected, previous=stored)
        if stored and current != stored:
            return ["Codex routing ownership source identity or native control drift"]
        if not stored and current["disabled_skills"]:
            return ["Codex routing ownership inventory missing; update installer receipt"]
    except (InstallError, OSError, ValueError) as exc:
        return ["Codex routing ownership failed: " + str(exc)]
    return []


def restore_disable(before, after, current):
    """Undo only the entries changed by this write; retain all other text."""
    old_data, old = config_entries(before or b"")
    _, new = config_entries(after)
    present, now = config_entries(current)
    text = current.decode("utf-8")
    spans = table_spans(text)
    expected = copy.deepcopy(present)
    edits, conflicts = [], []
    for key in set(old) | set(new):
        if old.get(key) == new.get(key) or now.get(key) == old.get(key):
            continue
        if now.get(key) != new.get(key) or key not in spans:
            conflicts.append("skills.config:" + new.get(key, old.get(key))["path"])
            continue
        start, end, chunk = spans[key]
        # Comments and extra fields added to our table are user edits too.
        new_span = table_spans(after.decode("utf-8")).get(key)
        if new_span is None:
            conflicts.append("unsupported-skill-table")
            continue
        # Compare only the table body, leaving trailing whitespace/comments
        # outside the last managed assignment untouched where possible.
        def body(value):
            return value.rstrip("\r\n")
        if body(chunk) != body(new_span[2]):
            conflicts.append("skills.config-user-modified:" + new[key]["path"])
            continue
        entries = expected["skills"]["config"]
        index = next(i for i, entry in enumerate(entries) if path_key(entry["path"]) == key)
        if key in old:
            entries[index] = old[key]
            # The write changed one boolean. Keep the current surrounding
            # whitespace, including separators inserted by later user tables.
            pattern = r"(?m)^([ \t]*enabled[ \t]*=[ \t]*)false([ \t]*(?:#[^\r\n]*)?\r?)$"
            replacement, count = re.subn(pattern, r"\g<1>true\2", chunk)
            if count != 1 or config_entries(replacement.encode())[1].get(key) != old[key]:
                raise InstallError("Unsupported original Skill restore spelling")
        else:
            entries.pop(index)
            replacement = ""
        edits.append((start, end, replacement))
    for start, end, replacement in sorted(edits, reverse=True):
        text = text[:start] + replacement + text[end:]
    # Removing the final array table naturally removes its implicit parents.
    if expected.get("skills", {}).get("config") == [] and "config" not in old_data.get("skills", {}):
        expected["skills"].pop("config")
        if not expected["skills"] and "skills" not in old_data:
            expected.pop("skills")
    result = text.encode("utf-8")
    if config_entries(result)[0] != expected:
        raise InstallError("Skill restore would change unrelated TOML semantics")
    return result, conflicts
