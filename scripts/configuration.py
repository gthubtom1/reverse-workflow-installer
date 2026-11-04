"""Configuration ownership, atomic writes and conditional three-way recovery."""
import base64
import copy
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
import tomllib

from versions import InstallError

MISSING = object()


def digest(data):
    return hashlib.sha256(data).hexdigest()


def atomic(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=".installer-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def encode_json(value):
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def load_json(path, default=None):
    path = Path(path)
    if not path.exists():
        return copy.deepcopy(default)
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, OSError) as exc:
        raise InstallError(f"无效的严格 JSON: {path}") from exc


def merge_restore(before, after, current, conflicts, key="$"):
    """Undo only values still equal to our write; retain subsequent user edits."""
    if current == after:
        return copy.deepcopy(before) if before is not MISSING else MISSING
    if before == after:
        return current
    if isinstance(after, dict) and isinstance(current, dict) and (isinstance(before, dict) or before is MISSING):
        result = copy.deepcopy(current)
        original = {} if before is MISSING else before
        for k in set(original) | set(after):
            b, a, c = original.get(k, MISSING), after.get(k, MISSING), current.get(k, MISSING)
            restored = merge_restore(b, a, c, conflicts, key + "." + k)
            if restored is MISSING:
                result.pop(k, None)
            else:
                result[k] = restored
        return result
    if isinstance(before, list) and isinstance(after, list) and isinstance(current, list):
        # Installer owns added/removed exact resources, not the entire user list.
        result = copy.deepcopy(current)
        for item in after:
            if item not in before and item in result:
                result.remove(item)
        for item in before:
            if item not in after and item not in result:
                result.append(item)
        return result
    conflicts.append(key)
    return current


def toml_parts(data):
    text = data.decode("utf-8")
    try:
        parsed = tomllib.loads(text)
    except ValueError as exc:
        raise InstallError("Codex config.toml 无效；先修复再安装") from exc
    # Conservative: refuse quoted/array forms of the owned table instead of guessing.
    chunks = re.split(r"(?m)^(?=\[)", text)
    owned, rest = {}, []
    for chunk in chunks:
        line = chunk.splitlines()[0] if chunk else ""
        match = re.fullmatch(r"\[mcp_servers\.rea(?:\.[A-Za-z0-9_-]+)*\]\s*(?:#.*)?", line)
        if match:
            owned[line.split("#")[0].strip()] = chunk
        else:
            rest.append(chunk)
    if parsed.get("mcp_servers", {}).get("rea") and not owned:
        raise InstallError("REA 使用了暂不支持的 TOML 表拼写；拒绝猜测修改")
    return parsed, owned, "".join(rest)


def codex_merge(before, staged):
    original, _, rest = toml_parts(before)
    modified, owned, _ = toml_parts(staged)
    for value in (original, modified):
        value.setdefault("mcp_servers", {}).pop("rea", None)
        if not value["mcp_servers"]:
            value.pop("mcp_servers")
    if original != modified:
        raise InstallError("官方 setup 修改了非 REA 的 Codex 字段；拒绝合并")
    result = rest.rstrip() + "\n\n" + "".join(owned.values())
    tomllib.loads(result)
    return result.encode("utf-8")


class Journal:
    def __init__(self, directory):
        self.directory = Path(directory)
        self.path = self.directory / "journal.json"
        self.data = {"status": "pending", "files": []}
        self.save()

    def save(self):
        atomic(self.path, encode_json(self.data))

    def write(self, path, data, kind="file"):
        path = Path(path).resolve()
        before = path.read_bytes() if path.exists() else None
        if before == data:
            return
        entry = {"path": str(path), "kind": kind, "before": None if before is None else base64.b64encode(before).decode(), "after": base64.b64encode(data).decode(), "before_sha256": None if before is None else digest(before), "after_sha256": digest(data)}
        # Persist the recovery material BEFORE mutation, including on partial failure.
        self.data["files"].append(entry)
        self.save()
        atomic(path, data)

    def finish(self, status):
        self.data["status"] = status
        self.save()


def restore_journal(path, apply=False):
    data = load_json(path)
    results = []
    for entry in reversed(data["files"]):
        target = Path(entry["path"])
        before = None if entry["before"] is None else base64.b64decode(entry["before"])
        after = base64.b64decode(entry["after"])
        current = target.read_bytes() if target.exists() else None
        conflicts = []
        if current == before:
            result = current
        elif current == after:
            result = before
        elif entry["kind"] == "json" and current is not None:
            try:
                value = merge_restore(MISSING if before is None else json.loads(before), json.loads(after), json.loads(current), conflicts)
                result = None if value is MISSING else encode_json(value)
            except ValueError:
                conflicts.append("invalid-json")
                result = current
        elif entry["kind"] == "toml" and current is not None:
            _, old, _ = toml_parts(before or b"")
            _, new, _ = toml_parts(after)
            _, now, rest = toml_parts(current)
            for key in set(old) | set(new):
                if now.get(key, "").rstrip() == new.get(key, "").rstrip():
                    if key in old:
                        now[key] = old[key]
                    else:
                        now.pop(key, None)
                elif now.get(key) != old.get(key):
                    conflicts.append(key)
            result = (rest.rstrip() + "\n\n" + "".join(now.values())).encode()
        else:
            result = current
            conflicts.append("user-modified")
        if apply and result != current:
            if result is None:
                target.unlink(missing_ok=True)
            else:
                atomic(target, result)
        results.append({"path": str(target), "conflicts": conflicts, "changed": result != current})
    return results
