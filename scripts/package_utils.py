"""Generic package identity and Pi package-registration helpers."""
import hashlib
import os
from pathlib import Path

from versions import InstallError


def tree_hash(path):
    """Hash every package file and reject links that escape the package root."""
    directory = Path(path)
    if directory.is_symlink() or not directory.is_dir():
        raise InstallError("插件包目录无效或为符号链接")
    hasher = hashlib.sha256()
    for item in sorted(directory.rglob("*")):
        relative = item.relative_to(directory).as_posix()
        if item.is_symlink():
            raise InstallError("插件包含符号链接；拒绝未冻结的外部内容")
        if item.is_file():
            hasher.update(relative.encode() + b"\0" + str(item.stat().st_size).encode() + b"\0")
            with item.open("rb") as stream:
                for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                    hasher.update(chunk)
    return hasher.hexdigest()


def registration_source(value):
    return value.get("source") if isinstance(value, dict) else value


def resolved_registration_source(value, agent=None):
    source = registration_source(value)
    if not isinstance(source, str) or not source:
        return None
    path = Path(source).expanduser()
    if not path.is_absolute():
        if agent is None:
            return None
        path = Path(agent) / path
    try:
        return path.resolve()
    except (OSError, RuntimeError):
        return None


def same_registration_source(value, root, agent=None):
    if not root:
        return False
    path = resolved_registration_source(value, agent)
    if path is None:
        return False
    try:
        root_path = Path(root).expanduser()
        if not root_path.is_absolute() and agent is not None:
            root_path = Path(agent) / root_path
        return os.path.normcase(str(path)) == os.path.normcase(str(root_path.resolve()))
    except (OSError, RuntimeError, TypeError):
        return False


def registration_matches(value, root, agent=None):
    """Accept one canonical package directory without resource overrides."""
    return same_registration_source(value, root, agent) and not (
        isinstance(value, dict) and any(key in value for key in ("extensions", "skills", "prompts", "themes"))
    )


def exposes_plugin_registration(value, plugin_root, plugin_dir, agent=None):
    """Detect a parent package registration that exposes a child plugin."""
    source_path = resolved_registration_source(value, agent)
    if source_path is None or not plugin_root:
        return False
    try:
        plugin_path = Path(plugin_root).expanduser().resolve()
        if source_path == plugin_path:
            return False
        relative = plugin_path.relative_to(source_path)
    except (OSError, RuntimeError, ValueError):
        return False
    return str(relative).replace("\\", "/") == plugin_dir or (source_path / plugin_dir).is_dir()
