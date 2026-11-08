"""Standalone shell-guard identity, scoped settings and migration validation."""
import copy
import os
from pathlib import Path
import re

from configuration import digest, load_json
from versions import InstallError, stable
import package_utils as pu

KEY = "shell_guard"


def reject_links(path):
    if any(p.is_symlink() or getattr(p, "is_junction", lambda: False)() for p in (path, *path.parents)):
        raise InstallError("shell-guard 路径含链接；拒绝未冻结的外部内容")


def tree_hash(root):
    path = Path(root)
    reject_links(path)
    for item in path.rglob("*"):
        reject_links(item)
    try:
        return pu.tree_hash(path)
    except InstallError as exc:
        raise InstallError(str(exc).replace("插件包", "shell-guard 插件包").replace("插件包含", "shell-guard 插件包含")) from exc


def validate_package(root, entry, development=False):
    root = Path(root)
    hashed = tree_hash(root)
    for name in entry["required_files"]:
        # A pre-0.2 development registration has the wiring in index.ts.
        if development and name == "runtime.mjs" and not re.search(r"[\"']\./runtime\.mjs[\"']", (root / "index.ts").read_text(encoding="utf-8")):
            continue
        if not (root / name).is_file():
            raise InstallError("shell-guard 缺少 " + name)
    pkg = load_json(root / "package.json")
    if not isinstance(pkg, dict) or pkg.get("name") != entry["package_name"]:
        raise InstallError("shell-guard 包名不符；必须选择独立插件目录")
    if (not development and pkg.get("version") != entry["version"]) or not stable(str(pkg.get("version", ""))):
        raise InstallError("shell-guard 插件版本不符")
    pi = pkg.get("pi")
    if not isinstance(pi, dict) or pi.get("extensions") != [entry["expected_extension"]]:
        raise InstallError("shell-guard 必须仅注册独立 index.ts 扩展")
    if any(pi.get(key, []) != [] for key in ("skills", "prompts", "themes")):
        raise InstallError("shell-guard 不得加载其他 Pi 资源")
    if pkg.get("dependencies") or pkg.get("optionalDependencies"):
        raise InstallError("shell-guard 必须是零运行时依赖包")
    return {"root": str(root.resolve()), "name": pkg["name"], "version": pkg["version"],
            "extensions": pi["extensions"], "tree_hash": hashed}


def executable_identity(value, option="--everything-es"):
    path = Path(value).expanduser()
    if not path.is_absolute() or not path.is_file():
        raise InstallError(f"{option} 必须是现存 CLI 文件的绝对路径")
    reject_links(path)
    if (os.name == "nt" and path.suffix.lower() != ".exe") or (os.name != "nt" and not os.access(path, os.X_OK)):
        raise InstallError(f"{option} 必须指向可执行文件")
    return {"path": str(path.resolve()), "sha256": digest(path.read_bytes())}


def gui_identity(value):
    return executable_identity(value, "--everything-gui")


def local_source(value, agent):
    source = pu.registration_source(value)
    if not isinstance(source, str):
        return None
    path = Path(source).expanduser()
    if path.is_absolute() or source.startswith(("./", "../", ".\\", "..\\", "~")) or (Path(agent) / path).exists():
        return path.resolve() if path.is_absolute() else (Path(agent) / path).resolve()
    return None


def same_path(a, b):
    return bool(isinstance(a, (str, Path)) and isinstance(b, (str, Path)) and a and b
                and os.path.normcase(str(Path(a).resolve())) == os.path.normcase(str(Path(b).resolve())))


def same_executable(a, b):
    return (isinstance(a, dict) and isinstance(b, dict) and a.get("sha256") == b.get("sha256")
            and bool(a.get("sha256")) and same_path(a.get("path"), b.get("path")))


def settings_at(agent):
    settings = load_json(Path(agent) / "settings.json", {})
    if not isinstance(settings, dict) or not isinstance(settings.get("packages", []), list):
        raise InstallError("Pi settings/packages 必须是对象/数组")
    return settings


def registrations(settings, agent, entry, allowed=()):
    """Reject duplicates, filtered entries, other copies and hub registrations.

    Read only explicitly registered local package manifests; do not scan profiles.
    """
    found = []
    for item in settings.get("packages", []):
        source = pu.registration_source(item)
        path = local_source(item, agent)
        if path is None:
            if isinstance(source, str) and (entry["package_name"] in source or "gthubtom1/agent-plugins" in source or re.match(r"^(?:npm:)?agent-plugins(?:@|$)", source)):
                raise InstallError("shell-guard 存在远程包或 hub 注册；拒绝重复加载")
            continue
        if (path / entry["plugin_dir"]).is_dir() or any(
            Path(root).is_relative_to(path) and not same_path(root, path) for root in allowed if root
        ):
            raise InstallError("shell-guard 存在 hub/父目录注册；拒绝重复加载")
        known = any(same_path(path, root) for root in allowed)
        package = load_json(path / "package.json", {}) if (path / "package.json").is_file() else {}
        is_guard = isinstance(package, dict) and package.get("name") == entry["package_name"]
        if known or is_guard or path.name == "shell-guard":
            if not known:
                raise InstallError("shell-guard 存在其他注册；开发包迁移需 --replace-shell-guard-root 准确路径")
            if not pu.registration_matches(item, source, agent):
                raise InstallError("shell-guard 注册含用户资源过滤；拒绝覆盖")
            found.append((item, path))
    if len(found) > 1:
        raise InstallError("shell-guard 重复注册；拒绝静默去重")
    extensions = settings.get("extensions", [])
    if not isinstance(extensions, list):
        raise InstallError("Pi settings.extensions 必须是数组")
    for item in extensions:
        path = local_source(item, agent)
        if path is None:
            continue
        package_root = path if path.is_dir() else path.parent
        package = load_json(package_root / "package.json", {}) if (package_root / "package.json").is_file() else {}
        if (isinstance(package, dict) and package.get("name") == entry["package_name"]) or (
            any(path == Path(root) / "index.ts" or path.is_relative_to(Path(root)) for root in allowed if root)
            or (path.name == "index.ts" and path.parent.name == "shell-guard")
        ):
            raise InstallError("shell-guard 存在直接 extensions 注册；仅支持独立 packages 注册")
    return found


def everything_settings(settings):
    guard = settings.get("shellGuard", {})
    if not isinstance(guard, dict) or not isinstance(guard.get("everything", {}), dict):
        raise InstallError("shellGuard/everything 配置必须是对象；拒绝覆盖")
    return guard.get("everything", {})


def es_setting(settings):
    return everything_settings(settings).get("esPath")


def gui_setting(settings):
    return everything_settings(settings).get("guiPath")


def plan_inputs(selected, previous, entry):
    settings = settings_at(selected["agent_dir"])
    old = (previous.get(KEY) or {}).get("root") if previous.get("installed") else None
    replacement = selected.get("replace_shell_guard_root")
    migration = None
    if replacement:
        if old or same_path(replacement, selected.get("shell_guard_root")):
            raise InstallError("--replace-shell-guard-root 仅迁移未由本回执管理的另一开发包")
        identity = validate_package(replacement, entry, development=True)
        matches = registrations(settings, selected["agent_dir"], entry, [replacement])
        if len(matches) != 1 or not same_path(matches[0][1], replacement):
            raise InstallError("迁移必须恰好匹配一个已有 shell-guard 注册")
        migration = {**identity, "registration": matches[0][0]}
    registrations(settings, selected["agent_dir"], entry, [old, replacement, selected.get("shell_guard_root")])
    executable = executable_identity(selected["everything_es"]) if selected.get("everything_es") else None
    gui = gui_identity(selected["everything_gui"]) if selected.get("everything_gui") else None
    current_es = es_setting(settings) if executable else None
    current_gui = gui_setting(settings) if gui else None
    if executable and current_es is not None and not same_path(current_es, executable["path"]):
        managed = previous.get("shell_guard_config") or {}
        if not managed or not same_path(current_es, managed.get("esPath")):
            raise InstallError("Everything esPath 已有用户配置；拒绝静默覆盖")
    if gui and current_gui is not None and not same_path(current_gui, gui["path"]):
        managed = previous.get("shell_guard_config") or {}
        if not managed or not same_path(current_gui, managed.get("guiPath")):
            raise InstallError("Everything guiPath 已有用户配置；拒绝静默覆盖")
    if selected.get("everything_autostart") and not (selected.get("everything_gui") or current_gui):
        raise InstallError("--everything-autostart 需要 --everything-gui 指定 GUI 可执行文件")
    return migration, executable, gui


def validate_plan(plan, entry):
    selected = plan["scope"]
    component = plan["components"][KEY]
    if component.get("plugin_dir") != entry["plugin_dir"]:
        raise InstallError("shell-guard plugin_dir 与清单不符")
    if selected.get("shell_guard_root"):
        local = validate_package(selected["shell_guard_root"], entry)
        if component.get("mode") != "read-only-local-package" or any(component.get(k) != v for k, v in local.items()):
            raise InstallError("shell-guard 本地包自 plan 后漂移或缺少冻结身份")
    else:
        expected = {**entry, "ref": entry["release_ref"], "mode": "clone-frozen-commit"}
        if entry.get("commit") is None:
            expected.pop("commit", None)
        if not all(re.fullmatch(r"[a-f0-9]{40}", str(component.get(k))) for k in ("commit", "repository_tree")) or any(component.get(k) != v for k, v in expected.items()):
            raise InstallError("shell-guard 冻结来源与清单不符")
    migration = plan.get("shell_guard_migration")
    replacement = selected.get("replace_shell_guard_root")
    if bool(migration) != bool(replacement):
        raise InstallError("shell-guard 迁移缺少冻结身份或范围")
    if replacement:
        current = validate_package(replacement, entry, development=True)
        if any(migration.get(k) != v for k, v in current.items()):
            raise InstallError("shell-guard 迁移源自 plan 后漂移")
        found = registrations(settings_at(selected["agent_dir"]), selected["agent_dir"], entry, [replacement])
        if len(found) != 1 or found[0][0] != migration.get("registration"):
            raise InstallError("shell-guard 迁移注册自 plan 后漂移")
    executable = plan.get("everything_es_identity")
    if bool(executable) != bool(selected.get("everything_es")) or (
        executable and not same_executable(executable, executable_identity(selected["everything_es"]))
    ):
        raise InstallError("Everything CLI 自 plan 后漂移或缺少冻结 hash")
    gui = plan.get("everything_gui_identity")
    if bool(gui) != bool(selected.get("everything_gui")) or (
        gui and not same_executable(gui, gui_identity(selected["everything_gui"]))
    ):
        raise InstallError("Everything GUI 自 plan 后漂移或缺少冻结 hash")


def checkout_identity(root, component, run):
    repository = Path(root).parents[len(Path(component["plugin_dir"]).parts) - 1]
    commit = run(["git", "-C", repository, "rev-parse", "HEAD"], cwd=repository)
    if commit != component.get("commit") or not re.fullmatch(r"[a-f0-9]{40}", str(commit)):
        raise InstallError("shell-guard checkout commit 不符")
    if run(["git", "-C", repository, "rev-parse", "HEAD^{tree}"], cwd=repository) != component.get("repository_tree"):
        raise InstallError("shell-guard checkout tree 不符")
    if run(["git", "-C", repository, "status", "--porcelain", "--untracked-files=all", "--ignored", "--", component["plugin_dir"]], cwd=repository):
        raise InstallError("shell-guard checkout tree 与冻结 commit 不符")
    return commit


def failures(receipt, entry, run):
    try:
        stored = receipt.get(KEY) or {}
        frozen = (receipt.get("components") or {}).get(KEY) or {}
        # Old receipts retain their own version/commit; new plans use the new pin.
        compatibility = {**entry, **{k: frozen[k] for k in ("version", "required_files") if k in frozen}}
        if frozen.get("repository") != entry["repository"] or frozen.get("plugin_dir") != entry["plugin_dir"]:
            raise InstallError("shell-guard 回执来源不符")
        root = stored.get("root")
        if not root or (receipt.get("paths") or {}).get(KEY) != root:
            raise InstallError("shell-guard 路径缺失或不一致")
        local = validate_package(root, compatibility)
        if any(stored.get(k) != v for k, v in local.items()) or (receipt.get("hashes") or {}).get("shell_guard_sha256") != local["tree_hash"]:
            raise InstallError("shell-guard identity/hash 漂移或缺失")
        if stored.get("mode") != frozen.get("mode") or stored.get("plugin_dir") != entry["plugin_dir"] or stored.get("repository") != entry["repository"]:
            raise InstallError("shell-guard 来源/模式不符")
        if stored["mode"] == "clone-frozen-commit":
            if stored.get("commit") != checkout_identity(root, frozen, run):
                raise InstallError("shell-guard 回执 commit 不符")
        elif stored["mode"] != "read-only-local-package" or any(frozen.get(k) != v for k, v in local.items()):
            raise InstallError("shell-guard 本地冻结身份不符")
        scope = receipt["scope"]
        if scope.get("client") != "pi" or not scope.get("agent_dir"):
            raise InstallError("shell-guard 仅适用于 Pi")
        settings = settings_at(scope["agent_dir"])
        found = registrations(settings, scope["agent_dir"], entry, [root])
        if len(found) != 1 or not same_path(found[0][1], root):
            raise InstallError("shell-guard 注册缺失或漂移")
        managed = receipt.get("shell_guard_config")
        if managed:
            current = everything_settings(settings)
            if "esPath" in managed and (not same_path(current.get("esPath"), managed.get("esPath"))
                    or not same_executable(executable_identity(managed["esPath"]), managed.get("executable"))):
                raise InstallError("shell-guard Everything esPath 配置或 CLI 漂移")
            if "guiPath" in managed and (not same_path(current.get("guiPath"), managed.get("guiPath"))
                    or not same_executable(gui_identity(managed["guiPath"]), managed.get("gui_executable"))):
                raise InstallError("shell-guard Everything guiPath 配置或 GUI 漂移")
            if "autostart" in managed and current.get("autostart") is not managed.get("autostart"):
                raise InstallError("shell-guard Everything autostart 配置漂移")
        return []
    except (InstallError, OSError, ValueError, TypeError, KeyError, IndexError) as exc:
        return [str(exc)]


def merge_settings(settings, selected, desired_root, previous, migration, entry):
    settings = copy.deepcopy(settings)
    old = (previous.get(KEY) or {}).get("root") if previous.get("installed") else None
    replaced = migration.get("root") if migration else None
    matches = registrations(settings, selected["agent_dir"], entry, [old, replaced, desired_root])
    packages = list(settings.get("packages", []))
    if matches:
        value, path = matches[0]
        if not same_path(path, desired_root):
            new_value = {**value, "source": desired_root} if isinstance(value, dict) else desired_root
            packages[packages.index(value)] = new_value
    else:
        packages.append(desired_root)
    settings["packages"] = packages
    if selected.get("everything_es"):
        current = es_setting(settings)
        previous_config = previous.get("shell_guard_config") or {}
        if current is not None and not same_path(current, selected["everything_es"]) and not same_path(current, previous_config.get("esPath")):
            raise InstallError("Everything esPath 已有用户配置；拒绝静默覆盖")
        if not same_path(current, selected["everything_es"]):
            settings.setdefault("shellGuard", {}).setdefault("everything", {})["esPath"] = selected["everything_es"]
    if selected.get("everything_gui"):
        current = gui_setting(settings)
        previous_config = previous.get("shell_guard_config") or {}
        if current is not None and not same_path(current, selected["everything_gui"]) and not same_path(current, previous_config.get("guiPath")):
            raise InstallError("Everything guiPath 已有用户配置；拒绝静默覆盖")
        if not same_path(current, selected["everything_gui"]):
            settings.setdefault("shellGuard", {}).setdefault("everything", {})["guiPath"] = selected["everything_gui"]
    if selected.get("everything_autostart"):
        current = everything_settings(settings).get("autostart")
        previous_config = previous.get("shell_guard_config") or {}
        if current is not None and current is not True and previous_config.get("autostart") != current:
            raise InstallError("Everything autostart 已有用户配置；拒绝静默覆盖")
        settings.setdefault("shellGuard", {}).setdefault("everything", {})["autostart"] = True
    return settings
