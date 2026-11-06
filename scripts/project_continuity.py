"""Read-only project-continuity package identity and content validation."""
import hashlib
import json
from pathlib import Path

from versions import InstallError

CONFIG_KEY = "project_continuity"
REQUIRED_FILES = ("package.json", "index.ts", "runtime.mjs", "store.mjs")


def plugin_entry(manifest):
    entry = (manifest or {}).get(CONFIG_KEY)
    if not isinstance(entry, dict):
        raise InstallError("components.json 缺少 project_continuity 来源")
    for key in ("repository", "api", "release_ref", "plugin_dir", "package_name", "version", "expected_extension"):
        if not entry.get(key):
            raise InstallError(f"project_continuity 来源清单缺少 {key}")
    return entry


def plugin_tree_hash(path):
    """Hash every package file; reject links whose target content could escape the hash."""
    directory = Path(path)
    if directory.is_symlink() or not directory.is_dir():
        raise InstallError("project-continuity 插件目录无效或为符号链接")
    hasher = hashlib.sha256()
    for item in sorted(directory.rglob("*")):
        relative = item.relative_to(directory).as_posix()
        if item.is_symlink():
            raise InstallError("project-continuity 插件含符号链接；拒绝未冻结的外部内容")
        if item.is_file():
            hasher.update(relative.encode() + b"\0" + str(item.stat().st_size).encode() + b"\0")
            with item.open("rb") as stream:
                for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                    hasher.update(chunk)
    return hasher.hexdigest()


def validate_local_package(package_path, manifest):
    """Require the standalone zero-dependency plugin, never the hub package."""
    entry = plugin_entry(manifest)
    package_path = Path(package_path)
    tree_hash = plugin_tree_hash(package_path)
    for name in REQUIRED_FILES:
        if not (package_path / name).is_file():
            raise InstallError(f"project-continuity 插件缺少 {name}")
    try:
        pkg = json.loads((package_path / "package.json").read_text(encoding="utf-8"))
    except (ValueError, OSError) as exc:
        raise InstallError("project-continuity 本地插件 package.json 无效") from exc
    if not isinstance(pkg, dict):
        raise InstallError("project-continuity package.json 必须是对象")
    if pkg.get("name") != entry["package_name"]:
        raise InstallError("project-continuity 插件包名不符")
    if pkg.get("version") != entry["version"]:
        raise InstallError("project-continuity 插件版本不符")
    pi = pkg.get("pi")
    if not isinstance(pi, dict) or pi.get("extensions") != [entry["expected_extension"]]:
        raise InstallError("project-continuity pi.extensions 必须仅包含 " + entry["expected_extension"])
    if any(pi.get(key, []) != [] for key in ("skills", "prompts", "themes")):
        raise InstallError("project-continuity 不得加载其他 Pi 资源")
    if pkg.get("dependencies") or pkg.get("optionalDependencies"):
        raise InstallError("project-continuity 必须是零运行时依赖包")
    return {
        "root": str(package_path.resolve()),
        "name": pkg["name"],
        "version": pkg["version"],
        "extensions": list(pi["extensions"]),
        "tree_hash": tree_hash,
    }


def registration_source(value):
    if isinstance(value, dict):
        return value.get("source")
    return value


def exposes_plugin_registration(value, plugin_root, plugin_dir):
    """Detect a hub/ancestor package that would load the same plugin twice."""
    source = registration_source(value)
    if not source:
        return False
    try:
        source_path = Path(source).expanduser().resolve()
        plugin_path = Path(plugin_root).expanduser().resolve()
    except (OSError, RuntimeError, TypeError):
        return False
    if source_path == plugin_path:
        return False
    try:
        relative = plugin_path.relative_to(source_path)
    except ValueError:
        return False
    return str(relative).replace("\\", "/") == plugin_dir or (source_path / plugin_dir).is_dir()


def registration_matches(value, root):
    """Accept a plain directory source; resource overrides require user review."""
    return value == root or (
        isinstance(value, dict) and value.get("source") == root
        and not any(key in value for key in ("extensions", "skills", "prompts", "themes"))
    )
