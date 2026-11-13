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
    if current == before:
        return current
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
    if (isinstance(before, list) or before is MISSING) and isinstance(after, list) and isinstance(current, list):
        # Installer owns added/removed exact resources, not the entire user list.
        original_missing = before is MISSING
        before = [] if original_missing else before
        result = copy.deepcopy(current)
        for item in after:
            if item not in before and item in result:
                result.remove(item)
        for item in before:
            if item not in after and item not in result:
                result.append(item)
        return MISSING if original_missing and not result else result
    conflicts.append(key)
    return current


def _toml_structure(text):
    """Locate real table headers and comments, skipping strings and value arrays."""
    headers, comments = [], []
    quote, depth, offset = None, 0, 0
    for line_match in re.finditer(r"[^\n]*\n|[^\n]+$", text):
        line = line_match.group()
        if quote is None and depth == 0 and line.lstrip(" \t").startswith("["):
            headers.append(offset)
        i = 0
        while i < len(line):
            char = line[i]
            if quote:
                if quote[0] == '"' and char == "\\":
                    i += 2
                    continue
                if len(quote) == 3 and line.startswith(quote, i):
                    # TOML permits one or two extra quotes at a multiline end.
                    while i < len(line) and line[i] == quote[0]:
                        i += 1
                    quote = None
                    continue
                if len(quote) == 1 and char == quote:
                    quote = None
            elif char == "#":
                comments.append(line[i:].rstrip("\r\n"))
                break
            elif char in "\"'":
                quote = char * 3 if line.startswith(char * 3, i) else char
                i += len(quote)
                continue
            elif char in "[{":
                depth += 1
            elif char in "]}":
                depth -= 1
            i += 1
        offset += len(line)
    return headers, comments


def without_rea(value):
    value = copy.deepcopy(value)
    servers = value.get("mcp_servers")
    if isinstance(servers, dict):
        servers.pop("rea", None)
        if not servers:
            value.pop("mcp_servers", None)
    return value


def toml_parts(data):
    try:
        text = data.decode("utf-8")
        parsed = tomllib.loads(text)
    except (ValueError, UnicodeError) as exc:
        raise InstallError("Codex config.toml 无效；先修复再安装") from exc
    headers, _ = _toml_structure(text)
    boundaries = sorted(set([0, *headers, len(text)]))
    owned, rest = {}, []
    for start, end in zip(boundaries, boundaries[1:]):
        chunk = text[start:end]
        line = chunk.split("\n", 1)[0].rstrip("\r")
        match = re.fullmatch(r"[ \t]*\[mcp_servers\.rea(?:\.[A-Za-z0-9_-]+)*\][ \t]*(?:#.*)?", line)
        if match:
            owned[line.split("#")[0].strip()] = chunk
        else:
            rest.append(chunk)
    rest = "".join(rest)
    try:
        remaining = tomllib.loads(rest)
    except ValueError as exc:
        raise InstallError("REA 使用了暂不支持的 TOML 表拼写；拒绝猜测修改") from exc
    servers = remaining.get("mcp_servers", {})
    if (isinstance(servers, dict) and "rea" in servers) or without_rea(remaining) != without_rea(parsed):
        raise InstallError("REA 使用了暂不支持的 TOML 表拼写；拒绝猜测修改")
    return parsed, owned, rest


def assemble_toml(rest, owned, non_rea, comment_sources=()):
    """Keep user text/comments and verify semantics after moving managed tables."""
    tail = "".join(owned.values())
    comments = _toml_structure(tail)[1]
    retained, seen = [], {}
    for source in comment_sources:
        for comment in _toml_structure(source)[1]:
            seen[comment] = seen.get(comment, 0) + 1
            if seen[comment] > comments.count(comment):
                retained.append(comment + "\n")
                comments.append(comment)
    result = rest + ("\n" if rest and not rest.endswith("\n") else "") + "".join(retained)
    if tail:
        result += "\n" + tail
    try:
        parsed = tomllib.loads(result)
        managed = tomllib.loads(tail).get("mcp_servers", {}).get("rea")
    except ValueError as exc:
        raise InstallError("合并后的 Codex config.toml 无效；拒绝写入") from exc
    if without_rea(parsed) != non_rea or parsed.get("mcp_servers", {}).get("rea") != managed:
        raise InstallError("REA 合并会改变非 REA 的 Codex 字段或 REA 语义；拒绝写入")
    return result.encode("utf-8")


def codex_merge(before, staged):
    original, old, rest = toml_parts(before)
    modified, owned, _ = toml_parts(staged)
    if without_rea(original) != without_rea(modified):
        raise InstallError("官方 setup 修改了非 REA 的 Codex 字段；拒绝合并")
    result = assemble_toml(rest, owned, without_rea(original), old.values())
    if tomllib.loads(result.decode()).get("mcp_servers", {}).get("rea") != modified.get("mcp_servers", {}).get("rea"):
        raise InstallError("REA 合并语义不一致；拒绝写入")
    return result


SECTION_PREFIX = b"<!-- reverse-workflow installer "


def managed_section(data):
    """One explicit owner per AGENTS bridge; user prose stays outside the span."""
    markers = list(re.finditer(rb"(?m)^<!-- reverse-workflow installer (begin|end) (.+) -->\r?$", data))
    if not markers and SECTION_PREFIX not in data:
        return None
    if len(markers) != 2 or [m[1] for m in markers] != [b"begin", b"end"] or markers[0][2] != markers[1][2] or data.count(SECTION_PREFIX) != 2:
        raise InstallError("Codex AGENTS.md 受管 section 标识不完整或重复；请审阅冲突")
    try:
        owner = json.loads(markers[0][2])
    except (ValueError, UnicodeError) as exc:
        raise InstallError("Codex AGENTS.md section owner 无效") from exc
    if not isinstance(owner, str) or not owner:
        raise InstallError("Codex AGENTS.md section owner 无效")
    start, end = markers[0].start(), markers[1].end()
    if data[end:end + 1] == b"\n":
        end += 1
    return owner, start, end, data[start:end]


def section_block(body, owner):
    identity = json.dumps(str(Path(owner).resolve()), ensure_ascii=True).encode()
    return SECTION_PREFIX + b"begin " + identity + b" -->\n" + body.rstrip(b"\r\n") + b"\n" + SECTION_PREFIX + b"end " + identity + b" -->\n"


class Journal:
    def __init__(self, directory):
        self.directory = Path(directory)
        self.path = self.directory / "journal.json"
        self.data = {"status": "pending", "files": []}
        self.save()

    def save(self):
        atomic(self.path, encode_json(self.data))

    def write(self, path, data, kind="file", *, replacements=None):
        path = Path(path).resolve()
        before = path.read_bytes() if path.exists() else None
        if before == data:
            return
        entry = {"path": str(path), "kind": kind, "before": None if before is None else base64.b64encode(before).decode(), "after": base64.b64encode(data).decode(), "before_sha256": None if before is None else digest(before), "after_sha256": digest(data)}
        if replacements:
            entry["package_replacements"] = copy.deepcopy(replacements)
        # Persist the recovery material BEFORE mutation, including on partial failure.
        self.data["files"].append(entry)
        self.save()
        atomic(path, data)

    def finish(self, status):
        self.data["status"] = status
        self.save()


def restore_journal(path, apply=False, defer_receipt=None):
    data = load_json(path)
    results = []
    entries = list(reversed(data["files"]))
    if defer_receipt is not None:
        defer_receipt = str(Path(defer_receipt).resolve())
        entries.sort(key=lambda e: e["path"] == defer_receipt)
    for entry in entries:
        target = Path(entry["path"])
        if str(target) == defer_receipt and any(item["conflicts"] for item in results):
            results.append({"path": str(target), "conflicts": ["restore-incomplete"], "changed": False})
            continue
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
                original, installed, present = (MISSING if before is None else json.loads(before)), json.loads(after), json.loads(current)
                # A replaced package is one logical registration. If the user
                # edited/removed its new item, do not resurrect the old copy.
                for replacement in entry.get("package_replacements", []):
                    old, new = replacement["before"], replacement["after"]
                    packages = present.get("packages", []) if isinstance(present, dict) else []
                    if new not in packages and old not in packages:
                        conflicts.append("$.packages.replaced-registration")
                        if isinstance(original, dict) and old in original.get("packages", []):
                            original["packages"].remove(old)
                value = merge_restore(original, installed, present, conflicts)
                result = None if value is MISSING else encode_json(value)
            except ValueError:
                conflicts.append("invalid-json")
                result = current
        elif entry["kind"] == "section" and current is not None:
            try:
                old = managed_section(before or b"")
                new = managed_section(after)
                now = managed_section(current)
                if new is None or now is None or now[0] != new[0] or now[3] != new[3]:
                    raise InstallError("managed section modified")
                # Legacy whole-file ownership migrates to a section. On undo,
                # restore that old body while retaining later surrounding prose.
                replacement = old[3] if old else ((before or b"") if new[1] == 0 else b"")
                result = current[:now[1]] + replacement + current[now[2]:]
            except InstallError:
                conflicts.append("managed-section-modified")
                result = current
        elif entry["kind"] == "toml" and current is not None:
            try:
                _, old, _ = toml_parts(before or b"")
                _, new, _ = toml_parts(after)
                present, now, rest = toml_parts(current)
                removed = list(now.values())
                for key in set(old) | set(new):
                    if now.get(key, "").rstrip() == new.get(key, "").rstrip():
                        if key in old:
                            now[key] = old[key]
                        else:
                            now.pop(key, None)
                    elif now.get(key) != old.get(key):
                        conflicts.append(key)
                result = assemble_toml(rest, now, without_rea(present), removed)
            except InstallError:
                conflicts.append("invalid-or-unsupported-toml")
                result = current
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
