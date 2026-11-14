"""Transactional orchestration. All package acquisition stays in official CLIs."""
import contextlib
import copy
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import uuid
from types import SimpleNamespace
from datetime import datetime, timezone

from configuration import Journal, atomic, codex_merge, digest, encode_json, load_json, restore_journal, toml_parts, managed_section, section_block
from versions import COMPONENTS, InstallError, resolve, stable
import package_utils as pu
import shell_guard as sg
import craft as cr
import craft_codex as cc
import routing_ownership as ro

REPO = Path(__file__).resolve().parents[1]
ADAPTER_VERSION = "0.2.0"  # Transaction protocol; old receipts remain readable.
INSTALLER_VERSION = "0.7.0"  # Candidate; no release/tag publication implied.


def run(args, *, cwd, env=None):
    try:
        completed = subprocess.run([str(a) for a in args], cwd=cwd, env=env, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=900)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise InstallError(f"命令无法完成: {Path(str(args[0])).name} ({type(exc).__name__})") from exc
    if completed.returncode:
        # Do not echo arbitrary output that may contain profile credentials.
        raise InstallError(f"官方命令失败 (exit {completed.returncode}): {Path(str(args[0])).name} {' '.join(str(x) for x in args[1:3])}；请在指定隔离目录手动重跑以查看官方诊断")
    return completed.stdout.strip()


def object_output(text, operation):
    try:
        result = json.loads(text)
    except ValueError as exc:
        raise InstallError(f"{operation} 未返回完整 JSON；当前官方接口未获支持") from exc
    if not isinstance(result, dict):
        raise InstallError(f"{operation} JSON 必须是对象")
    # Incur may wrap command results in a data envelope.
    if isinstance(result.get("data"), dict):
        result = result["data"]
    if result.get("status") in ("failed", "error", "blocked", "cancelled") or result.get("error"):
        raise InstallError(f"{operation} 报告失败；未激活该事务")
    return result


def abs_path(value):
    return Path(value).expanduser().resolve()


def selected_components(value):
    if value is None or str(value).strip().lower() in ("", "all"):
        return ["rea", "spec_kit", "reverse"]
    aliases = {"rea": "rea", "spec-kit": "spec_kit", "spec_kit": "spec_kit", "reverse": "reverse", "shell-guard": "shell_guard", "shell_guard": "shell_guard", "craft": "craft"}
    result = []
    for raw in str(value).split(","):
        key = aliases.get(raw.strip().lower())
        if key is None or key in result:
            raise InstallError("--components 只能包含不重复的 rea, spec-kit, reverse, shell-guard, craft，或 all")
        result.append(key)
    if not result:
        raise InstallError("--components 不能为空")
    return result


def needs_host(components):
    return any(key in components for key in ("rea", "spec_kit", "shell_guard", "craft"))


def needs_project(components):
    # Spec Kit's CLI can be installed globally; its project templates are
    # generated only when the user explicitly supplies a project scope.
    return False


def needs_agent(components, client):
    return "rea" in components or ("reverse" in components and client in ("pi", "codex", "claude")) or ("shell_guard" in components and client == "pi") or "craft" in components


def detect_client(client, config=None, env=None, agent_dir=None):
    if client == "none":
        return "none", ["explicit --client none"]
    if client != "auto":
        return client, ["explicit --client"]
    env = os.environ if env is None else env
    evidence = set()
    names = []
    for key in ("PI_CODING_AGENT", "AI_AGENT"):
        if env.get(key, "").lower() == ("true" if key == "PI_CODING_AGENT" else "pi"):
            evidence.add("pi")
            names.append(key)
    if env.get("CODEX_THREAD_ID"):
        evidence.add("codex")
        names.append("CODEX_THREAD_ID")
    configs = []
    if config and config.exists():
        configs.append(config)
    if agent_dir:
        agent_dir = Path(agent_dir)
        configs.extend(path for path in (agent_dir / "config.toml", agent_dir / "settings.json", agent_dir / "mcp.json", agent_dir / "claude_desktop_config.json") if path.exists() and path not in configs)
    for candidate in configs:
        if candidate.suffix == ".json":
            value = load_json(candidate, {})
            if not isinstance(value, dict):
                raise InstallError(f"宿主配置必须是 JSON 对象: {candidate}")
            if str(value.get("$schema", "")).startswith("https://pi.dev/schemas/"):
                evidence.add("pi")
                names.append("Pi configuration schema")
            elif candidate.name == "claude_desktop_config.json" and isinstance(value.get("mcpServers"), dict):
                evidence.add("claude")
                names.append("Claude Desktop configuration name and mcpServers")
        elif candidate.name == "config.toml":
            value, _, _ = toml_parts(candidate.read_bytes())
            if any(k in value for k in ("approval_policy", "sandbox_mode", "model_reasoning_effort")):
                evidence.add("codex")
                names.append("Codex config.toml and Codex configuration tables")
    if len(evidence) != 1:
        reason = "宿主证据冲突" if evidence else "没有明确宿主标记或配置 schema 证据"
        raise InstallError(f"auto: {reason}；请指定 --client pi、--client codex 或 --client claude，并提供 --agent-dir 或 --client-config。CLI 存在与模型名不代表宿主身份；未枚举环境值。")
    return evidence.pop(), names


def craft_profile(selected, contract=None):
    """Select per scope/record, never change a process-global backend module."""
    client = selected.get("client")
    if client not in ("pi", "codex"):
        if "craft" in selected.get("components", []) or contract is not None:
            raise InstallError("Craft is supported only for explicitly selected Pi or Codex")
        return cr
    profile = cc if client == "codex" else cr
    if contract is not None:
        profile.gate(contract)
    return profile


def craft_record_profile(record):
    contract = record.get("craft_contract")
    client = (record.get("scope") or {}).get("client") or record.get("craft_client")
    if client is None:
        # Original Pi journals had only the contract. New records bind client too.
        client = {cr.CONTRACT["name"]: "pi", cc.CONTRACT["name"]: "codex"}.get((contract or {}).get("name")) if isinstance(contract, dict) else None
    profile = craft_profile({"client": client, "components": ["craft"]})
    profile.gate(contract)
    return profile


def scope(args):
    raw = str(getattr(args, "components", "") or "").strip().lower()
    components = selected_components(args.components)
    if getattr(args, "with_shell_guard", False) and "shell_guard" not in components:
        components.append("shell_guard")
    if getattr(args, "with_craft", False) and "craft" not in components:
        components.append("craft")
    root = abs_path(args.root)
    previous = load_json(root / ".installer/receipt.json", {})
    if previous.get("craft") or "craft" in (previous.get("scope") or {}).get("components", []):
        craft_record_profile(previous)
        if "craft" not in components:
            components.append("craft")
    craft_options = {}
    for key in ("craft_bundle", "craft_pi_node", "craft_pi_entry", "craft_pi_distribution", "craft_codex_cli"):
        raw_path = getattr(args, key, None) or (previous.get("craft_source") or {}).get(key)
        if raw_path:
            cr.no_links(Path(raw_path).expanduser().absolute())
        craft_options[key] = str(abs_path(raw_path)) if raw_path else None
    craft_options["craft_pi_version"] = getattr(args, "craft_pi_version", None) or (previous.get("craft_source") or {}).get("craft_pi_version")
    if any(craft_options.values()) and "craft" not in components:
        raise InstallError("Craft options require --with-craft or explicit craft component")
    if "craft" in components and not {"reverse", "spec_kit"}.issubset(components):
        raise InstallError("Craft requires explicitly selected reverse and spec-kit; dependencies are not silently installed")
    # Only a current managed selection survives updates; historic all never opts in.
    if previous.get("installed") and "shell_guard" in receipt_components(previous) and "shell_guard" not in components:
        components.append("shell_guard")
    explicit_spec_pin = getattr(args, "spec_kit_version", None)
    spec_pin = explicit_spec_pin
    if spec_pin is None and "spec_kit" in components and previous.get("installed") and not getattr(args, "upgrade_components", False):
        spec_pin = ((previous.get("components") or {}).get("spec_kit") or {}).get("version")
    if spec_pin is not None:
        if "spec_kit" not in components:
            raise InstallError("--spec-kit-version 需要选择 spec-kit 组件")
        if not isinstance(spec_pin, str) or not stable(spec_pin):
            raise InstallError("--spec-kit-version 必须是精确稳定版本（例如 1.3.1）")
    root = abs_path(args.root)
    guard_options = {}
    for key in ("shell_guard_root", "replace_shell_guard_root"):
        raw_path = getattr(args, key, None)
        if raw_path:
            sg.reject_links(Path(raw_path).expanduser().absolute())
        guard_options[key] = str(abs_path(raw_path)) if raw_path else None
    if "shell_guard" in components and not guard_options["shell_guard_root"] and (previous.get("shell_guard") or {}).get("mode") == "read-only-local-package":
        guard_options["shell_guard_root"] = previous["shell_guard"]["root"]
    raw_es = getattr(args, "everything_es", None)
    guard_options["everything_es"] = sg.executable_identity(raw_es)["path"] if raw_es else None
    raw_gui = getattr(args, "everything_gui", None)
    guard_options["everything_gui"] = sg.gui_identity(raw_gui)["path"] if raw_gui else None
    guard_options["everything_autostart"] = bool(getattr(args, "everything_autostart", False))
    if any(guard_options.values()) and "shell_guard" not in components:
        raise InstallError("shell-guard 路径/配置参数需要 --with-shell-guard 或显式 shell-guard 组件")
    explicit = abs_path(args.client_config) if args.client_config else None
    agent_hint = abs_path(args.agent_dir) if args.agent_dir else (explicit.parent if explicit else None)
    if needs_host(components) or (args.client == "auto" and (agent_hint or explicit)):
        if args.client == "none":
            raise InstallError("所选组件需要宿主；请指定 --client pi 或 --client codex")
        client, evidence = detect_client(args.client, explicit, agent_dir=agent_hint)
    else:
        client, evidence = ("none", ["no host component selected"]) if args.client == "auto" else detect_client(args.client, explicit, agent_dir=agent_hint)
    workflow_exclusions = getattr(args, "exclude_workflow_skill", []) or []
    if workflow_exclusions and (client != "codex" or "reverse" not in components):
        raise InstallError("--exclude-workflow-skill requires Codex and reverse; Pi uses --exclude-rea-skill; other hosts require their own native adapter")
    if client == "none" and (args.agent_dir or explicit):
        raise InstallError("--client none 不能同时指定 agent/config；请选择宿主或省略这些参数")
    if getattr(args, "codex_skills_root", None) and client != "codex":
        raise InstallError("--codex-skills-root 仅适用于 Codex reverse Skill")
    agent = agent_hint
    codex_skills = None
    if client == "codex" and "reverse" in components:
        for raw_path in (args.agent_dir, args.client_config, getattr(args, "codex_skills_root", None), args.project):
            if raw_path:
                ro.no_links(raw_path)
        codex_skills = abs_path(getattr(args, "codex_skills_root", None)) if getattr(args, "codex_skills_root", None) else (agent / "skills" if agent else (Path.home() / ".codex" / "skills").resolve())
    if needs_agent(components, client) and agent is None:
        raise InstallError("所选组件需要 --agent-dir 或 --client-config；不会默认写用户 profile")
    config_name = {"pi": "mcp.json", "codex": "config.toml", "claude": "claude_desktop_config.json"}.get(client)
    config = explicit if client == "claude" and explicit else ((agent / config_name) if agent and config_name else None)
    if explicit and config != explicit and client != "claude":
        raise InstallError(f"--client-config 必须是指定 agent 目录中的 {config.name}；Pi settings.json 与 mcp.json 共用该目录")
    project = abs_path(args.project) if args.project else None
    if needs_project(components) and project is None:
        raise InstallError("所选 Spec Kit 组件需要 --project 指定独立成果项目")
    if client == "claude" and "reverse" in components and project is None:
        raise InstallError("claude 使用 reverse 入口需要 --project 写入项目入口")
    reverse = abs_path(args.reverse_root) if args.reverse_root else None
    if "shell_guard" in components and client != "pi":
        raise InstallError("shell-guard 插件仅适用于 Pi")
    if "craft" in components:
        craft_profile({"client": client, "components": components})
        required = ("craft_bundle", "craft_codex_cli") if client == "codex" else ("craft_bundle", "craft_pi_node", "craft_pi_entry", "craft_pi_version", "craft_pi_distribution")
        forbidden = ("craft_pi_node", "craft_pi_entry", "craft_pi_version", "craft_pi_distribution") if client == "codex" else ("craft_codex_cli",)
        if any(craft_options[key] for key in forbidden):
            raise InstallError("Craft runtime options do not match selected client")
        if not all(craft_options[key] for key in required):
            raise InstallError("Craft unsupported artifact until published; provide " + ", ".join("--" + key.replace("_", "-") for key in required))
    tools = [REPO, root / "versions", root / ".installer"]
    if craft_options["craft_bundle"]:
        bundle_path = Path(craft_options["craft_bundle"])
        if bundle_path == root or root.is_relative_to(bundle_path) or bundle_path.is_relative_to(root):
            raise InstallError("Craft source bundle must be outside installation root")
        tools.append(bundle_path)
    if agent:
        tools.append(agent)
    if reverse:
        tools.append(reverse)
    tools.extend(Path(p) for key, p in guard_options.items() if p and key in ("shell_guard_root", "replace_shell_guard_root", "everything_gui"))
    if project:
        for tool in tools:
            if project == tool or project.is_relative_to(tool) or tool.is_relative_to(project):
                raise InstallError(f"成果项目与工具/配置范围重叠: {tool}")
        if project == root or root.is_relative_to(project):
            raise InstallError("成果项目不能包含安装根")
    if codex_skills:
        for tool in [REPO, root / "versions", root / ".installer", reverse, *[Path(p) for key, p in guard_options.items() if p and key in ("shell_guard_root", "replace_shell_guard_root", "everything_gui")]]:
            if tool and (codex_skills == tool or codex_skills.is_relative_to(tool) or tool.is_relative_to(codex_skills)):
                raise InstallError(f"Codex Skills 根不能与安装/源范围重叠: {tool}")
        if agent and codex_skills == agent:
            raise InstallError("Codex Skills 根不能就是 CODEX_HOME 根；请选择 CODEX_HOME/skills")
        if project and (project == codex_skills or project.is_relative_to(codex_skills) or codex_skills.is_relative_to(project)):
            raise InstallError("Codex Skills 根不能与成果项目重叠")
    if root == REPO or root.is_relative_to(REPO):
        raise InstallError("--root 必须在 installer 源码仓库之外")
    if bool(args.spec_kit_tools) != bool(args.spec_kit_bin):
        raise InstallError("--spec-kit-tools 与 --spec-kit-bin 必须一起提供")
    if client != "pi" and (args.rea_manual or args.exclude_rea_skill):
        raise InstallError("--rea-manual / --exclude-rea-skill 仅适用于 Pi")
    if client == "pi" and (args.rea_manual or args.exclude_rea_skill) and agent is None:
        raise InstallError("--rea-manual / --exclude-rea-skill 需要 --agent-dir 或 --client-config；不会默认写用户 profile")
    reuse = {key: str(abs_path(getattr(args, key))) if getattr(args, key) else None for key in ("rea_prefix", "spec_kit_tools", "spec_kit_bin")}
    for directory in [root / "versions", root / ".installer", *[Path(p) for p in reuse.values() if p]]:
        if project and (project == directory or project.is_relative_to(directory) or directory.is_relative_to(project)):
            raise InstallError("成果项目与复用工具目录重叠")
    detection = None if args.node else shutil.which("node")
    node = str(abs_path(args.node)) if args.node else (str(abs_path(detection)) if detection else None)
    return {"components": components, "root": str(root), "client": client, "evidence": evidence, "agent_dir": str(agent) if agent else None, "codex_skills_root": str(codex_skills) if codex_skills else None, "client_config": str(config) if config else None, "project": str(project) if project else None, "reverse_root": str(reverse) if reverse else None, "node": node, "uv": shutil.which("uv"), "git": shutil.which("git"), **reuse, **guard_options, **craft_options, **({"spec_kit_version": spec_pin} if explicit_spec_pin is not None else {})}


def reverse_identity(path):
    path = Path(path)
    required = ["RULES.md", "skills/config/routing.json", "skills/SKILL.md", "skills/MASTER-ROUTING.md", "skills/ops/scope-contract.md", "skills/ops/evidence-finding-path.md"]
    # Upstream's master skill can be at skills/SKILL.md or root SKILL.md.
    master = "skills/SKILL.md"
    if not (path / "skills/SKILL.md").is_file() and (path / "SKILL.md").is_file():
        required[2] = "SKILL.md"
        master = "SKILL.md"
    for name in required:
        if not (path / name).is_file():
            raise InstallError(f"reverse 工作副本缺少原生入口: {name}")
    routers = [name for name in ("skills/scripts/master-route.ps1", "skills/scripts/master-route.sh") if (path / name).is_file()]
    if not routers:
        raise InstallError("reverse 缺少原生 master-route；不会生成第二套路由")
    commit = run(["git", "-C", path, "rev-parse", "HEAD"], cwd=path)
    dirty = bool(run(["git", "-C", path, "status", "--porcelain", "--untracked-files=normal"], cwd=path))
    source = source_tree_hash(path)
    algorithm = "git-ls-files" if source is not None else "tree-walk"
    plugin_root = path / "plugins/reverse-skill"
    plugin_manifest = plugin_root / ".codex-plugin/plugin.json"
    plugin_skill = plugin_root / "skills/reverse-skill-router/SKILL.md"
    plugin_files = []
    codex_plugin = None
    if plugin_manifest.is_file() and plugin_skill.is_file():
        codex_plugin = str(plugin_root)
        plugin_files = [str(plugin_manifest.relative_to(path)), str(plugin_skill.relative_to(path))]
    entry_names = required + routers + plugin_files
    return {"root": str(path.resolve()), "commit": commit, "dirty": dirty, "entry_hashes": {name: digest((path / name).read_bytes()) for name in entry_names}, "working_tree_sha256": source if source is not None else tree_hash(path, exclude_git=True), "source_hash_algorithm": algorithm, "routers": routers, "master": master, "codex_plugin": codex_plugin}


def reverse_identity_matches(stored, current):
    """Compare stored identity fields while retaining compatibility with older receipts."""
    if not isinstance(stored, dict) or not isinstance(current, dict):
        return False
    for key, value in stored.items():
        if key == "working_tree_sha256" and not stored.get("source_hash_algorithm"):
            # Legacy receipts recorded commit/dirty state but did not define the
            # algorithm used for a full source hash.
            continue
        if key == "entry_hashes":
            # Entry inventories are append-only compatibility evidence. Older
            # receipts can contain a strict subset when a newer adapter adds
            # optional router/plugin entries; every recorded byte must still
            # match the current source.
            if not isinstance(value, dict) or not isinstance(current.get(key), dict):
                return False
            if any(current[key].get(name) != digest_value for name, digest_value in value.items()):
                return False
            continue
        if current.get(key) != value:
            return False
    return True


def git_source_names(path):
    """Read-only tracked plus non-ignored untracked file list; None when git refuses or is unavailable."""
    environment = os.environ.copy()
    environment.update({"GIT_TERMINAL_PROMPT": "0", "GIT_OPTIONAL_LOCKS": "0", "LC_ALL": "C"})
    try:
        completed = subprocess.run(["git", "-C", str(path), "ls-files", "--cached", "--others", "--exclude-standard", "-z"], capture_output=True, timeout=180, env=environment)
    except (OSError, subprocess.TimeoutExpired):
        return None
    if completed.returncode:
        return None
    names = completed.stdout.decode("utf-8", "surrogateescape").split("\0")
    return sorted({Path(name).as_posix() for name in names if name})


def source_tree_hash(path):
    """Hash only Git source content (tracked and non-ignored new files); ignored runtime artifacts stay out."""
    directory = Path(path)
    if not (directory / ".git").exists():
        return None
    names = git_source_names(directory)
    if names is None:
        return None
    hasher = hashlib.sha256()
    for name in names:
        item = directory / name
        relative = Path(name).as_posix()
        if item.is_symlink():
            hasher.update(relative.encode() + b"\0link\0" + os.readlink(item).encode())
        elif item.is_file():
            hasher.update(relative.encode() + b"\0")
            with item.open("rb") as stream:
                for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                    hasher.update(chunk)
        else:
            # A tracked file deleted from the worktree is a real source change.
            hasher.update(relative.encode() + b"\0missing\0")
    return hasher.hexdigest()


def tree_hash(path, exclude_git=False, *, installer_outputs=False):
    """Hash stable files without writing bytecode; Git roots use source-only hashing, others a plain walk."""
    directory = Path(path)
    if exclude_git:
        source = source_tree_hash(directory)
        if source is not None:
            return source
    hasher = hashlib.sha256()
    for item in sorted(directory.rglob("*")):
        relative = item.relative_to(directory)
        if "__pycache__" in relative.parts or item.suffix == ".pyc":
            continue
        if exclude_git and ".git" in relative.parts:
            continue
        if installer_outputs and relative.parts[0] == ".local":
            # Only the installer's root output directory is outside its source.
            continue
        if item.is_symlink():
            hasher.update(relative.as_posix().encode() + b"\0link\0" + os.readlink(item).encode())
            continue
        if item.is_file():
            hasher.update(relative.as_posix().encode() + b"\0")
            with item.open("rb") as stream:
                for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                    hasher.update(chunk)
    return hasher.hexdigest()


def specify_init_args(specify, target, client):
    args = [specify, "init", target, "--integration", client, "--script", "py", "--non-interactive"]
    if client in ("codex", "claude"):
        args.append("--ignore-agent-tools")
    return args


def retired_project_continuity_migration(selected):
    """Freeze one safe removal of the retired package from an old Pi receipt."""
    previous = load_json(Path(selected["root"]) / ".installer/receipt.json", {})
    recorded = (previous.get("scope") or {}).get("components") or []
    old = previous.get("project_continuity")
    if not previous.get("installed") or (not isinstance(old, dict) and "project_continuity" not in recorded):
        return None
    if selected.get("client") != "pi" or not selected.get("agent_dir"):
        raise InstallError("活动 receipt 含已移除的 project-continuity，但当前计划没有可管理的 Pi agent；拒绝静默保留插件")
    old = old if isinstance(old, dict) else {}
    paths = previous.get("paths") or {}
    root = old.get("root") or paths.get("project_continuity")
    plugin_dir = old.get("plugin_dir")
    package_name = old.get("name") or ((previous.get("components") or {}).get("project_continuity") or {}).get("package_name")
    if not root or not plugin_dir or not package_name:
        raise InstallError("活动 receipt 含已移除的 project-continuity，但缺少可识别的包路径/身份；请先人工移除其 Pi 注册")
    root = str(abs_path(root))
    settings = sg.settings_at(selected["agent_dir"])
    packages = settings.get("packages", [])
    matches = [item for item in packages if pu.registration_matches(item, root, selected["agent_dir"])]
    same_sources = [item for item in packages if pu.same_registration_source(item, root, selected["agent_dir"])]
    if len(matches) > 1 or (not matches and same_sources):
        raise InstallError("活动 receipt 含 project-continuity，但未找到唯一的精确 Pi 包注册；拒绝静默保留插件")
    registration = matches[0] if matches else None

    for item in packages:
        if pu.exposes_plugin_registration(item, root, plugin_dir, selected["agent_dir"]):
            raise InstallError("活动 receipt 含 project-continuity，且 Pi settings 还有 hub/父目录注册；请先清理重复注册")
        source = pu.registration_source(item)
        package_root = pu.resolved_registration_source(item, selected["agent_dir"])
        package = load_json(package_root / "package.json", {}) if package_root and (package_root / "package.json").is_file() else {}
        if (isinstance(package, dict) and package.get("name") == package_name and not pu.same_registration_source(item, root, selected["agent_dir"])) or (isinstance(source, str) and package_name in source and not pu.same_registration_source(item, root, selected["agent_dir"])):
            raise InstallError("活动 receipt 含 project-continuity，且 settings 还有无法归属的同名注册；拒绝静默保留插件")
    return {"root": root, "plugin_dir": plugin_dir, "package_name": package_name, "registration": registration}


def _craft_target_path_preflight(selected, components, resources):
    """Portable Win32 scope for Craft writes; read-only, before lock/Journal/commands."""
    if os.name != "nt" or "craft" not in selected.get("components", []):
        return
    root = Path(selected["root"])
    # Content-addressed version keys are 20 ASCII units; reserve retry -8 hex.
    version = root / "versions" / ("0" * 20 + "-00000000")
    profile = craft_profile(selected)
    bundle_dir = cc.BUNDLE_DIRECTORY if profile is cc else "craft-bundle"
    resource_dir = cc.RESOURCE_DIRECTORY if profile is cc else "craft-pi"
    targets = [(bundle_dir + "/" + name, version / bundle_dir / name)
               for name in components["craft"]["files"]]
    targets += [(resource_dir + "/" + name, version / resource_dir / name)
                for name in resources["files"]]
    if profile is cc:
        targets.extend(("codex-adapter/" + p.name, p) for p in (
            Path(selected["agent_dir"]) / "AGENTS.md",
            Path(selected["agent_dir"]) / "config.toml",
            Path(selected["codex_skills_root"]) / "reverse-workflow/SKILL.md"))
    else:
        adapter = root / "adapters" / adapter_identity_key() / "pi"
        targets += [("pi-adapter/" + p.relative_to(REPO / "adapters/pi").as_posix(),
                     adapter / p.relative_to(REPO / "adapters/pi"))
                    for p in (REPO / "adapters/pi").rglob("*") if p.is_file()]
        targets.append(("pi-adapter/receipt-location.json", adapter / "receipt-location.json"))
    targets += [("version-complete", version / "complete.json"),
                ("receipt", root / ".installer/receipt.json")]
    if selected.get("agent_dir") and profile is not cc:
        agent = Path(selected["agent_dir"])
        targets += [("pi-settings", agent / "settings.json"),
                    ("pi-global-skill", agent / "skills/reverse-workflow/SKILL.md")]
    tx = root / ".installer/transactions/20000101T000000Z-00000000"
    targets += [("transaction/" + name, tx / name) for name in
                ("journal.json", "plan.json", "agent/" + ("config.toml" if profile is cc else "mcp.json"))]
    def units(path):
        return len(str(path).encode("utf-16-le")) // 2
    failures = []
    for label, target in targets:
        count, parent = units(target), units(target.parent)
        # atomic() uses .installer- plus 8 random chars (19 total); reserve 24.
        temporary = parent + 1 + 24
        if count > 259 or parent > 247 or temporary > 259:
            failures.append((max(count, temporary, parent + 12), label, count, parent, temporary))
    if failures:
        _, label, count, parent, temporary = max(failures)
        raise InstallError(f"craft-path-too-long: 选择更短安装根；{label}；UTF16 file={count}/259, "
                           f"parent={parent}/247, atomic-temp={temporary}/259 "
                           "(24-unit basename budget; retry suffix reserved)")


def installer_identity():
    """Identify the installer checkout used to produce a plan/receipt."""
    source = source_tree_hash(REPO)
    commit = None
    dirty = None
    branch = None
    if (REPO / ".git").exists():
        try:
            commit = run(["git", "-C", REPO, "rev-parse", "HEAD"], cwd=REPO)
            dirty = bool(run(["git", "-C", REPO, "status", "--porcelain", "--untracked-files=normal"], cwd=REPO))
        except InstallError:
            commit = None
            dirty = None
        try:
            branch = run(["git", "-C", REPO, "symbolic-ref", "--quiet", "--short", "HEAD"], cwd=REPO) or None
        except InstallError:
            pass  # Detached/unavailable branch is unknown, never assumed main.
    return {"root": str(REPO.resolve()), "commit": commit, "branch": branch, "dirty": dirty, "working_tree_sha256": source if source is not None else tree_hash(REPO, exclude_git=True, installer_outputs=True), "source_hash_algorithm": "git-ls-files" if source is not None else "tree-walk"}


def make_plan(args, fetch=None):
    selected = scope(args)
    cr = craft_profile(selected)
    codex_entry_preflight(selected)
    previous = load_json(Path(selected["root"]) / ".installer/receipt.json", {})
    workflow_exclusions = list(getattr(args, "exclude_workflow_skill", []) or [])
    routing = ro.plan(selected, workflow_exclusions, previous.get("routing_ownership"))
    manifest = load_json(REPO / "components.json")
    craft_local = craft_inputs = None
    if "craft" in selected["components"]:
        craft_local = {**cr.bundle(selected["craft_bundle"]), "repository": manifest["craft"]["repository"]}
        craft_inputs = cr.resource_identity(cr.resource_files(REPO, Path(selected["root"]) / ".installer/receipt.json"))
        _craft_target_path_preflight(selected, {"craft": craft_local}, craft_inputs)
    craft_reverse = cr.reverse_contract(selected.get("reverse_root")) if "craft" in selected["components"] else None
    # Resolve only selected components; explicit local working copies need no upstream lookup.
    local_keys = {"reverse": "reverse_root", "shell_guard": "shell_guard_root"}
    keys = [key for key in selected["components"] if key != "craft" and not selected.get(local_keys.get(key, ""))]
    previous = load_json(Path(selected["root"]) / ".installer/receipt.json", {})
    reuse_receipt_versions = bool(previous.get("installed")) and not getattr(args, "upgrade_components", False)
    rea_version = ((previous.get("components") or {}).get("rea") or {}).get("version") if reuse_receipt_versions else None
    spec_version = selected.get("spec_kit_version")
    if spec_version is None and reuse_receipt_versions and "spec_kit" in keys:
        spec_version = ((previous.get("components") or {}).get("spec_kit") or {}).get("version")
    components = resolve(manifest, **({"fetch": fetch} if fetch else {}), components=keys,
                         **({"spec_kit_version": spec_version} if spec_version else {}),
                         **({"rea_version": rea_version} if rea_version and "rea" in keys else {}))
    if selected.get("spec_kit_version") is None and reuse_receipt_versions and "spec_kit" in components:
        components["spec_kit"].pop("version_selection", None)
    if "reverse" in selected["components"]:
        if selected["reverse_root"]:
            identity = reverse_identity(selected["reverse_root"])
            components["reverse"] = {"repository": manifest["reverse"]["repository"], "ref": "local-working-copy", "commit": identity["commit"], "published_commit": None, "local_identity": identity, "mode": "read-only-working-copy"}
        else:
            components["reverse"]["mode"] = "clone-frozen-commit"
    craft_runtime = craft_update = craft_resources = None
    if "craft" in selected["components"]:
        components["craft"] = craft_local
        craft_resources = craft_inputs
        craft_runtime = (cc.runtime_identity if cr is cc else cr.pi_runtime)(selected, components["craft"], run)
        craft_update = cr.update_record(load_json(Path(selected["root"]) / ".installer/receipt.json", {}), components["craft"])
        old_craft = load_json(Path(selected["root"]) / ".installer/receipt.json", {}).get("craft") or {}
        if cr is not cc:
            cr.registration(sg.settings_at(selected["agent_dir"]), selected["agent_dir"], (old_craft.get("resources"),))
    retirement = retired_project_continuity_migration(selected)
    guard_migration = executable = gui_executable = None
    if "shell_guard" in selected["components"]:
        entry = manifest["shell_guard"]
        if selected.get("shell_guard_root"):
            local = sg.validate_package(selected["shell_guard_root"], entry)
            components["shell_guard"] = {**local, "mode": "read-only-local-package", "plugin_dir": entry["plugin_dir"], "repository": entry["repository"]}
        previous = load_json(Path(selected["root"]) / ".installer/receipt.json", {})
        guard_migration, executable, gui_executable = sg.plan_inputs(selected, previous, entry)
    missing = []
    if "rea" in selected["components"]:
        if not selected["node"]: missing.append("node")
    if "spec_kit" in selected["components"] and not selected["spec_kit_tools"] and not selected["uv"]:
        missing.append("uv")
    if "reverse" in selected["components"] and not selected["reverse_root"] and not selected["git"]:
        missing.append("git")
    for key, option in (("shell_guard", "shell_guard_root"),):
        if key in selected["components"] and not selected.get(option) and not selected["git"]:
            missing.append("git")
    config = Path(selected["client_config"]) if selected["client_config"] else None
    settings = Path(selected["agent_dir"]) / "settings.json" if selected["agent_dir"] and selected["client"] == "pi" else None
    input_paths = [p for p in (config, settings) if p is not None]
    if selected["client"] == "codex" and "reverse" in selected["components"] and selected.get("agent_dir"):
        input_paths.extend([
            Path(selected["agent_dir"]) / "AGENTS.md",
            Path(selected["codex_skills_root"]) / "reverse-workflow/SKILL.md",
        ])
    if routing:
        input_paths.extend(Path(item["path"]) for item in routing["disabled_skills"])
    inputs = {str(p): digest(p.read_bytes()) if p.exists() else None for p in input_paths}
    commands = []
    if routing:
        for item in routing["disabled_skills"]:
            commands.append(("Keep existing native Skill disable: " if item["native_disabled"] else "Journal Codex native [[skills.config]] enabled=false: ") + item["path"])
    if "rea" in selected["components"]:
        if selected["client"] == "claude":
            commands.append("事务内自动合并 Claude Desktop JSON 的 mcpServers.rea；不调用 REA setup，保留其他字段")
        else:
            commands.append(("核验只读复用 REA prefix: " + selected["rea_prefix"] + " @" + components["rea"]["version"]) if selected["rea_prefix"] else ("npm install --prefix <root>/versions/<frozen-id>/rea --registry https://registry.npmjs.org rea-agents@" + components["rea"]["version"]))
            commands.extend([f"rea setup --client {selected['client']} --skill=false --dry-run --json", f"rea setup --client {selected['client']} --skill=false --yes --json"])
    if "spec_kit" in selected["components"]:
        commands.append(("核验只读复用 Spec Kit tools/bin: " + selected["spec_kit_tools"] + " / " + selected["spec_kit_bin"] + " @" + components["spec_kit"]["version"]) if selected["spec_kit_tools"] else ("uv --no-config tool install --default-index https://pypi.org/simple specify-cli==" + components["spec_kit"]["version"]))
        if selected.get("project"):
            init_preview = specify_init_args("<specify>", "<staging-project>", selected["client"])
            commands.append(" ".join(init_preview))
    if retirement:
        commands.append("移除旧 receipt 中可唯一识别的 project-continuity Pi 包注册；旧包目录保留在历史版本目录")
    if "shell_guard" in selected["components"]:
        component = components["shell_guard"]
        commands.append(("核验只读 shell-guard 独立包与冻结 tree hash: " + component["root"]) if selected.get("shell_guard_root") else ("git clone --no-checkout " + component["repository"] + " <version>/agent-plugins-shell-guard; git checkout --detach " + component["commit"]))
        commands.append("仅注册 shell-guard 独立子目录；Everything 只合并明确提供的 esPath/guiPath/autostart；迁移按冻结旧注册/hash 条件替换")
    if "craft" in selected["components"]:
        commands.append("Verify explicit Codex CLI binary/version/hash against the reviewed stock runtime profile; journal the exact profile and two-binary bundle/resources; retain the single global reverse-workflow entry" if cr is cc else "Verify explicit Pi node/entry/version and exact local Craft bundle; copy to isolated version; journal execution resources and unique package registration")
    return {"installer_source": installer_identity(), "craft_reverse_contract": craft_reverse, "craft_contract": copy.deepcopy(cr.CONTRACT) if "craft" in selected["components"] else None, "craft_resources": craft_resources, "craft_runtime": craft_runtime, "craft_update": craft_update, "installer_version": INSTALLER_VERSION, "retired_project_continuity": retirement, "shell_guard_migration": guard_migration, "everything_es_identity": executable, "everything_gui_identity": gui_executable, "schema_version": 2 if "craft" in selected["components"] else 1, "adapter_version": ADAPTER_VERSION, "scope": selected, "components": components, "config_inputs": inputs, "missing_prerequisites": missing, "commands": commands, "routing_control_status": ro.host_status(selected), "routing_ownership": routing, "resource_selection": {"exclude_workflow_skill": [str(ro.no_links(p).resolve()) for p in workflow_exclusions], "rea_manual": args.rea_manual, "exclude_rea_skill": [str(abs_path(p)) for p in args.exclude_rea_skill]}, "limits": limits(selected)}


PI_RECEIPT_LINE = "读取此技能目录相对路径 `../../receipt-location.json`，再读取其中 `receipt` 指向的本机 JSON。"


def pi_adapt(text, receipt_path):
    if PI_RECEIPT_LINE not in text:
        return text
    absolute = f"直接读取本机安装回执 `{receipt_path}`（这是回执本体，不是 receipt-location.json）。"
    return text.replace(PI_RECEIPT_LINE, absolute, 1)


def pi_global_skill_text(receipt_path):
    source = (REPO / "adapters/pi/skills/reverse-workflow/SKILL.md").read_text(encoding="utf-8")
    if PI_RECEIPT_LINE not in source:
        raise InstallError("Pi reverse-workflow skill 缺少可适配的 receipt 定位文本")
    return pi_adapt(source, receipt_path)


def limits(selected=None):
    result = {"host_resource_loading": "unverified", "mcp_handshake_and_tools_schema": "unverified", "reverse_real_task": "unverified", "spec_kit_real_workflow": "unverified", "provider_installation": "not_implemented", "portable_node_download": "not_implemented; use --node", "codex_plugin_registration": "not_implemented; global Codex Skill uses the receipt and optionally references an existing plugin", "existing_project_template_upgrade": "not_implemented; preserve existing project templates", "package_artifact_provenance": "official npm lock integrity checked; PyPI hashes recorded, uv resolution used, wheel not independently rehashed", "craft_runtime": "unverified; no provider, owner, policy, cancellation or task execution", "craft_public_distribution": "public Windows x64 pin and release asset verified; host/provider/business acceptance remains separate", "all_agents": "pi/codex/claude supported; host loading and real task validation remain unverified"}
    if selected and selected.get("client") == "codex" and "craft" in selected.get("components", []):
        result["craft_public_distribution"] = "explicit Codex native bundle identity only; publication/release pin remains unverified"
        result["craft_runtime"] = "unverified; exact external CLI and reviewed stock startup/thread/turn profile frozen; offline native entry inspection is separate from provider/model/permission/cleanup qualification"
    return result


def validate_plan(plan):
    selected = plan.get("scope") or {}
    cr = craft_profile(selected, plan.get("craft_contract"))
    schema = 2 if "craft" in selected.get("components", []) else 1
    if type(plan.get("schema_version")) is not int or plan["schema_version"] != schema or plan.get("adapter_version") != ADAPTER_VERSION:
        raise InstallError("计划 schema/adapter 版本不兼容；Craft requires schema 2, core requires schema 1；重新 plan")
    _craft_target_path_preflight(selected, plan.get("components") or {}, plan.get("craft_resources") or {})
    if "project_continuity" in selected.get("components", []):
        raise InstallError("冻结计划仍选择已移除的 project-continuity；请重新 plan")
    if plan.get("installer_source") != installer_identity():
        raise InstallError("安装器源码在 plan 后发生漂移；重新从当前 main 生成计划")
    checked = scope(SimpleNamespace(**{**selected, **plan["resource_selection"], "components": ",".join(selected["components"]), "node": selected.get("node"), "uv": selected.get("uv"), "git": selected.get("git")}))
    for key in ("components", "root", "client", "agent_dir", "codex_skills_root", "client_config", "project", "reverse_root", "shell_guard_root", "replace_shell_guard_root", "everything_es", "everything_gui", "everything_autostart", "craft_bundle", "craft_pi_node", "craft_pi_entry", "craft_pi_distribution", "craft_pi_version", "craft_codex_cli", "node", "rea_prefix", "spec_kit_tools", "spec_kit_bin"):
        if checked.get(key) != selected.get(key):
            raise InstallError("冻结计划包含非规范路径或范围；重新 plan")
    if checked.get("spec_kit_version") != selected.get("spec_kit_version"):
        raise InstallError("冻结计划的 Spec Kit 版本选择不一致")
    if selected.get("spec_kit_version") is not None and plan.get("components", {}).get("spec_kit", {}).get("version") != selected["spec_kit_version"]:
        raise InstallError("冻结计划的 Spec Kit 版本与显式 pin 不一致")
    expected_configs = []
    if selected["client_config"]:
        expected_configs.append(Path(selected["client_config"]))
    if selected["client"] == "pi" and selected["agent_dir"]:
        expected_configs.append(Path(selected["agent_dir"]) / "settings.json")
    if selected["client"] == "codex" and "reverse" in selected["components"] and selected.get("agent_dir"):
        expected_configs.extend([
            Path(selected["agent_dir"]) / "AGENTS.md",
            Path(selected["codex_skills_root"]) / "reverse-workflow/SKILL.md",
        ])
    previous = load_json(Path(selected["root"]) / ".installer/receipt.json", {})
    routing = ro.validate(plan.get("routing_ownership"), selected, plan["resource_selection"].get("exclude_workflow_skill", []), previous.get("routing_ownership"))
    if routing and plan.get("routing_ownership") is not None:
        expected_configs.extend(Path(item["path"]) for item in routing["disabled_skills"])
    if set(plan["config_inputs"]) != {str(p) for p in expected_configs}:
        raise InstallError("冻结计划的配置输入范围不一致")
    manifest = load_json(REPO / "components.json")
    retirement = retired_project_continuity_migration(selected)
    if plan.get("retired_project_continuity") != retirement:
        raise InstallError("旧 receipt 的 project-continuity 退役信息自 plan 后发生变化；重新 plan")
    planned = plan.get("components") or {}
    for key in selected["components"]:
        component = planned.get(key)
        if not isinstance(component, dict) or component.get("repository") != manifest[key]["repository"]:
            raise InstallError("计划的组件来源不在固定来源清单中")
        if key in ("rea", "spec_kit") and not stable(component.get("version")):
            raise InstallError("计划缺少精确稳定版本")
        if key == "reverse" and not re.fullmatch(r"[0-9a-f]{40}", str(component.get("commit"))):
            raise InstallError("计划缺少精确 reverse commit")
    if "craft" in selected["components"]:
        cr.validate_plan(plan, manifest["craft"])
        cr.validate_resources(plan, REPO)
        if (cc.runtime_identity if cr is cc else cr.pi_runtime)(selected, planned["craft"], run) != plan.get("craft_runtime"):
            raise InstallError("Craft explicit runtime drift since plan")
    elif plan.get("craft_contract") or plan.get("craft_runtime") or plan.get("craft_resources") or plan.get("craft_reverse_contract"):
        raise InstallError("Unselected Craft contract/runtime in plan")
    if "shell_guard" in selected["components"]:
        sg.validate_plan(plan, manifest["shell_guard"])
    elif plan.get("shell_guard_migration") or plan.get("everything_es_identity") or plan.get("everything_gui_identity") or selected.get("everything_autostart"):
        raise InstallError("未选择 shell-guard 却包含配置/迁移身份")
    for name, expected in plan["config_inputs"].items():
        p = Path(name)
        if (digest(p.read_bytes()) if p.exists() else None) != expected:
            raise InstallError(f"配置自 plan 后发生漂移，拒绝应用: {p}；重新生成计划")
    codex_entry_preflight(selected)


@contextlib.contextmanager
def locked(root):
    directory = Path(root) / ".installer"
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "transaction.lock"
    try:
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError as exc:
        raise InstallError("已有安装/恢复事务；若上次崩溃，请确认无进程后移除 transaction.lock") from exc
    os.close(fd)
    try:
        yield
    finally:
        path.unlink(missing_ok=True)


def node_and_npm(node, engine, cwd, env):
    if not node or not Path(node).is_file():
        raise InstallError("未找到 Node；用 --node 指定符合 REA engines.node 的旁置 node 可执行文件")
    node = str(Path(node).resolve())
    # Require npm paired with this exact runtime; never fall back to a different PATH npm.
    candidates = [Path(node).parent / "node_modules/npm/bin/npm-cli.js", Path(node).parent.parent / "lib/node_modules/npm/bin/npm-cli.js", Path(node).resolve().parent / "node_modules/npm/bin/npm-cli.js"]
    npm = next((p for p in candidates if p.is_file()), None)
    if npm is None:
        raise InstallError("所选 Node 旁找不到官方 npm-cli.js；请提供含 npm 的官方 Node 分发包")
    # Delegate evolving semver engines to npm's own bundled implementation.
    semver = npm.parents[1] / "node_modules/semver"
    script = "const s=require(process.argv[1]);if(!s.satisfies(process.versions.node,process.argv[2]))process.exit(2);console.log(process.versions.node)"
    try:
        version = run([node, "-e", script, semver, engine], cwd=cwd, env=env)
    except InstallError as exc:
        raise InstallError(f"Node 不满足官方 REA engines.node={engine}，或 npm 的 semver 不可用；使用 --node 选择配套运行时") from exc
    return node, npm, version


def package_paths(version_dir):
    directory = Path(version_dir)
    return {"rea_prefix": directory / "rea", "rea_package": directory / "rea/node_modules/rea-agents", "uv_tools": directory / "spec-kit/tools", "uv_bin": directory / "spec-kit/bin", "reverse": directory / "reverse-skill", "shell_guard_repo": directory / "agent-plugins-shell-guard"}


def process_env(root, paths, agent, client, node):
    env = os.environ.copy()
    env.update({"UV_TOOL_DIR": str(paths["uv_tools"]), "UV_TOOL_BIN_DIR": str(paths["uv_bin"]), "UV_CACHE_DIR": str(root / ".installer/cache/uv"), "npm_config_cache": str(root / ".installer/cache/npm"), "PI_CODING_AGENT_DIR": str(agent), "CODEX_HOME": str(agent), "PYTHONDONTWRITEBYTECODE": "1", "GIT_TERMINAL_PROMPT": "0"})
    for key in list(env):
        if key.startswith("UV_INDEX") or key in ("UV_DEFAULT_INDEX", "UV_INDEX_URL", "UV_EXTRA_INDEX_URL", "PIP_INDEX_URL", "PIP_EXTRA_INDEX_URL"):
            env.pop(key)
    env["PATH"] = str(Path(node).parent) + os.pathsep + env.get("PATH", "")
    return env


def recover_pending_transactions(root):
    """Rollback transactions interrupted before Journal.finish().

    Recovery is automatic only when every owned file is still at its recorded
    post-write state (or already at its pre-write state). A later user edit is
    a hard stop so the installer never guesses which bytes to preserve.
    """
    root = Path(root)
    directory = root / ".installer/transactions"
    if not directory.is_dir():
        return []
    recovered = []
    for journal_path in sorted(directory.glob("*/journal.json"), reverse=True):
        data = load_json(journal_path, {})
        if data.get("status") != "pending":
            continue
        if "craft_contract" in data:
            craft_record_profile(data)
        preview = restore_journal(journal_path, apply=False, defer_receipt=root / ".installer/receipt.json")
        conflicts = [item for item in preview if item.get("conflicts")]
        if conflicts:
            names = ", ".join(item["path"] for item in conflicts[:3])
            raise InstallError(f"发现未完成事务 {journal_path.parent.name} 且文件已有后续修改；先审阅并 restore，拒绝继续安装: {names}")
        restore_journal(journal_path, apply=True, defer_receipt=root / ".installer/receipt.json")
        data["status"] = "recovered"
        data["recovery"] = {"mode": "automatic-safe-rollback", "files": preview}
        atomic(journal_path, encode_json(data))
        recovered.append(journal_path.parent.name)
    return recovered


def install(plan, args):
    validate_plan(plan)
    root = Path(plan["scope"]["root"])
    with locked(root):
        # A killed process leaves a pending journal. Reconcile it before
        # resolving package identities or touching a new host configuration.
        recover_pending_transactions(root)
        # Recheck after acquiring lock.
        validate_plan(plan)
        return _install(plan, args)


IDENTITY_KEYS = ("root", "client", "agent_dir", "codex_skills_root", "client_config", "project")
ALL_COMPONENTS = list(COMPONENTS)


def normalized_identity(scope_value, components=None):
    value = scope_value if isinstance(scope_value, dict) else {}
    recorded_components = list(components) if components is not None else value.get("components")
    if not recorded_components:
        recorded_components = ["rea", "spec_kit", "reverse"]
    identity = {}
    for key in IDENTITY_KEYS:
        raw = value.get(key)
        if key == "codex_skills_root" and not raw and value.get("client") == "codex" and "reverse" in recorded_components:
            # Legacy Codex receipts predate the explicit user Skills root.
            raw = Path(value.get("agent_dir")) / "skills" if value.get("agent_dir") else (Path.home() / ".codex" / "skills")
        if key == "client":
            identity[key] = str(raw) if raw else None
        else:
            identity[key] = str(abs_path(raw)) if raw else None
    return identity


def identity_compatible(previous_scope, previous_components, selected_scope):
    previous_identity = normalized_identity(previous_scope, previous_components)
    selected_identity = normalized_identity(selected_scope, selected_scope.get("components"))
    if previous_identity == selected_identity:
        return True
    # Adding reverse to an existing Codex package-only root establishes the
    # user Skills location for the first time; it does not move that root.
    if (
        previous_identity.get("client") == selected_identity.get("client") == "codex"
        and "reverse" not in previous_components
        and "reverse" in (selected_scope.get("components") or [])
        and not (previous_scope or {}).get("codex_skills_root")
    ):
        previous_without_skills = dict(previous_identity)
        selected_without_skills = dict(selected_identity)
        previous_without_skills["codex_skills_root"] = None
        selected_without_skills["codex_skills_root"] = None
        return previous_without_skills == selected_without_skills
    return False


def receipt_components(receipt):
    recorded = (receipt.get("scope") or {}).get("components")
    if recorded:
        return list(recorded)
    # Legacy receipts recorded before project_continuity existed: expect the historic three.
    return ["rea", "spec_kit", "reverse"]


def config_rea_entry(client, config):
    config = Path(config) if config else None
    if config is None or not config.is_file():
        return None
    data = load_json(config, {}) if client in ("pi", "claude") else toml_parts(config.read_bytes())[0]
    table = data.get("mcpServers" if client in ("pi", "claude") else "mcp_servers", {})
    return table.get("rea")


def adapter_identity_key(client="pi"):
    """Content address only the adapter resources used by this host transaction."""
    hasher = hashlib.sha256()
    base = REPO / "adapters" / client
    for item in sorted(base.rglob("*"), key=lambda p: p.relative_to(base).as_posix()):
        if item.is_file():
            hasher.update(item.relative_to(base).as_posix().encode() + b"\0" + item.read_bytes())
    return digest(encode_json({"adapter": ADAPTER_VERSION, "client": client, "sources": hasher.hexdigest()}))[:20]


def ownership_key(path):
    return os.path.normcase(str(Path(path).resolve()))


def ownership_index(root, previous):
    """Hashes recorded for files this installer wrote, including older transactions that left them unchanged."""
    recorded = {}

    def absorb(entries):
        for entry in entries or []:
            if isinstance(entry, dict) and entry.get("path") and entry.get("after_sha256"):
                recorded.setdefault(ownership_key(entry["path"]), set()).add(str(entry["after_sha256"]))

    absorb(previous.get("config_diff"))
    for path, value in (previous.get("entry_hashes") or {}).items():
        if path and value:
            recorded.setdefault(ownership_key(path), set()).add(str(value))
    candidates = [Path(root) / ".installer/transactions" / str(transaction) for transaction in (previous.get("history") or [])]
    if previous.get("backup"):
        candidates.append(Path(previous["backup"]))
    for directory in candidates:
        journal_path = directory / "journal.json" if directory.is_dir() else directory
        if journal_path.is_file():
            absorb(load_json(journal_path, {}).get("files"))
    return recorded


def owned_skill_hashes(previous, receipt_path):
    """Exact bytes of the previous installer's Pi adapter, adapted with this receipt path."""
    hashes = set()
    adapter_root = (previous.get("adapter") or {}).get("root")
    if not adapter_root:
        return hashes
    try:
        text = (Path(adapter_root) / "skills/reverse-workflow/SKILL.md").read_text(encoding="utf-8")
    except (OSError, ValueError):
        return hashes
    adapted = pi_adapt(text, str(receipt_path))
    if adapted != text:
        hashes.add(digest(adapted.encode()))
    return hashes


def owned_project_file(path, ownership):
    """True only when an existing project file is installer-written and unchanged."""
    path = Path(path)
    if path.is_symlink():
        return False
    try:
        data = path.read_bytes()
    except OSError:
        return False
    return digest(data) in ownership.get(ownership_key(path), ())


def check_host_file(ownership, path, data, *, client, legacy=(), owner_receipt=None):
    """Read-only check shared by plan and activation."""
    path = Path(path)
    if path.is_symlink() or (path.exists() and not path.is_file()):
        raise InstallError(f"{client} 宿主文件路径不是普通文件: {path}")
    current = path.read_bytes() if path.exists() else None
    if current is not None and current != data:
        allowed = set(ownership.get(ownership_key(path), ())) | set(legacy)
        if digest(current) not in allowed:
            other = re.search(r"([A-Za-z]:[\\/][^\s`\"']*?|/[^\s`\"']*?)[\\/]\.installer[\\/]receipt\.json", current.decode("utf-8", "replace"))
            if other and owner_receipt is not None and abs_path(Path(other.group(1)) / ".installer/receipt.json") != abs_path(owner_receipt):
                raise InstallError(f"{client} 宿主文件属于另一安装根 {other.group(1)}，拒绝覆盖: {path}；同一 agent/项目只能由一个安装根管理，请先 restore 并清理旧 root，或改用独立的 --agent-dir/--project")
            raise InstallError(f"{client} 宿主文件已被用户修改，拒绝覆盖: {path}；请审阅受管入口冲突")


def write_host_file(journal, ownership, path, data, *, client, legacy=(), owner_receipt=None, entries=None):
    check_host_file(ownership, path, data, client=client, legacy=legacy, owner_receipt=owner_receipt)
    journal.write(path, data)
    if entries is not None:
        entries[str(Path(path).resolve())] = digest(data)


def codex_agents_merge(path, body, receipt_path, previous, ownership):
    path = Path(path)
    if path.is_symlink() or (path.exists() and not path.is_file()):
        raise InstallError(f"Codex AGENTS.md 路径不是普通文件: {path}")
    current = path.read_bytes() if path.exists() else b""
    block = section_block(body, receipt_path)
    section = managed_section(current)
    if section:
        owner, start, end, existing = section
        if ownership_key(owner) != ownership_key(receipt_path):
            raise InstallError(f"Codex AGENTS.md section 属于另一安装根，拒绝覆盖: {path}")
        recorded = previous.get("managed_agents") or {}
        if existing != block and digest(existing) != recorded.get("sha256"):
            raise InstallError(f"Codex AGENTS.md 受管 section 已被用户修改，拒绝覆盖: {path}")
        return current[:start] + block + current[end:], block
    if current and digest(current) in ownership.get(ownership_key(path), ()):
        # Migrate an unchanged legacy installer-owned whole file.
        return block, block
    # An unmarked legacy bridge still owns its receipt. Do not combine two
    # installations merely because the new Skills directory happens to be empty.
    text = current.decode("utf-8", "replace")
    receipt_refs = re.findall(r'''[`"']((?:[A-Za-z]:[\\/]|/)[^`\r\n"']*[\\/]\.installer[\\/]receipt\.json)[`"']''', text)
    receipt_refs.extend(re.findall(r'''(?:^|\s)((?:[A-Za-z]:[\\/]|/)[^\s`"']*[\\/]\.installer[\\/]receipt\.json)''', text))
    if receipt_refs:
        if any(ownership_key(ref) != ownership_key(receipt_path) for ref in receipt_refs):
            raise InstallError(f"Codex AGENTS.md 旧入口属于另一安装根，拒绝追加第二入口: {path}")
        raise InstallError(f"Codex AGENTS.md 旧受管入口没有匹配的所有权记录或已被用户修改；请审阅冲突: {path}")
    # Existing user instructions remain byte-for-byte before the managed bridge.
    separator = b"\n" if current and not current.endswith(b"\n") else b""
    return current + separator + block, block


def codex_entry_preflight(selected):
    if selected.get("client") != "codex" or "reverse" not in selected.get("components", []):
        return None
    receipt_path = Path(selected["root"]) / ".installer/receipt.json"
    previous = load_json(receipt_path, {})
    ownership = ownership_index(selected["root"], previous)
    skill_path = Path(selected["codex_skills_root"]) / "reverse-workflow/SKILL.md"
    skill = (REPO / "adapters/codex/SKILL.md").read_text(encoding="utf-8").replace("{{RECEIPT}}", str(receipt_path)).encode()
    body = (REPO / "adapters/codex/AGENTS.md").read_text(encoding="utf-8").replace("{{RECEIPT}}", str(receipt_path)).replace("{{CODEX_SKILL_ENTRY}}", str(skill_path)).encode()
    agents_path = Path(selected["agent_dir"]) / "AGENTS.md"
    agents, block = codex_agents_merge(agents_path, body, receipt_path, previous, ownership)
    check_host_file(ownership, skill_path, skill, client="Codex", owner_receipt=receipt_path)
    return agents_path, agents, block, skill_path, skill


def _install(plan, args):
    selected, components = plan["scope"], plan["components"]
    cr = craft_profile(selected, plan.get("craft_contract"))
    selection = list(selected["components"])
    root = Path(selected["root"])
    agent = Path(selected["agent_dir"]) if selected.get("agent_dir") else None
    project = Path(selected["project"]) if selected.get("project") else None
    config = Path(selected["client_config"]) if selected.get("client_config") else None
    client = selected["client"]
    manifest = load_json(REPO / "components.json")
    receipt_path = root / ".installer/receipt.json"
    previous = load_json(receipt_path, {})
    installed = bool(previous.get("installed"))
    previous_selection = receipt_components(previous) if installed else []
    if installed:
        previous_scope = previous.get("scope") or {}
        previous_components = receipt_components(previous)
        if previous_scope.get("client") == "codex" and previous_scope.get("project") and not selected.get("project") and "reverse" in previous_components:
            raise InstallError("旧 Codex receipt 仍管理项目范围；全局化迁移不会静默删除项目入口。使用同一 project 完成保守更新，或选择新的安装 root 重新建立 CODEX_HOME 全局安装")
        if not identity_compatible(previous_scope, previous_components, selected):
            raise InstallError("安装根已属于另一客户端/agent/项目范围；请选新 root，或 restore 后安装")
        removed = set(previous_selection) - set(selection)
        if removed and (removed != {"project_continuity"} or not plan.get("retired_project_continuity")):
            raise InstallError("不能在同一 root 收缩或更换组件范围（已安装 " + ", ".join(previous_selection) + "；本次 " + ", ".join(selection) + "）；请 restore 到目标组件的事务，或用新 root 安装")
        if "project_continuity" in previous_selection and not plan.get("retired_project_continuity"):
            raise InstallError("活动 receipt 含已移除的 project-continuity，但没有安全退役计划；拒绝静默保留插件")
        if "shell_guard" in previous_selection:
            failures = sg.failures(previous, manifest["shell_guard"], run)
            if failures:
                raise InstallError("活动 shell-guard 漂移；拒绝更新: " + "; ".join(failures))
        if "craft" in previous_selection:
            errors = craft_record_profile(previous).failures(previous)
            if errors:
                raise InstallError("Active Craft drift; refusing update: " + "; ".join(errors))
        recorded_config = previous.get("managed_rea_config")
        if recorded_config is not None and config_rea_entry(client, config) != recorded_config:
            raise InstallError("活动 REA 配置含后续用户修改或已缺失；拒绝覆盖，请先审阅差异并保留/迁移自定义项")
    identity = components.get("reverse", {}).get("local_identity") if "reverse" in selection else None
    if identity and not reverse_identity_matches(identity, reverse_identity(identity["root"])):
        raise InstallError("reverse 工作副本自 plan 后发生漂移；重新 plan")
    if plan["missing_prerequisites"]:
        raise InstallError("缺少依赖: " + ", ".join(plan["missing_prerequisites"]) + "；请自行准备后重新 plan")
    version_key = digest(encode_json({"components": {key: components[key] for key in selection}, "node": selected.get("node"), "adapter": ADAPTER_VERSION, "installer": INSTALLER_VERSION}))[:20]
    version_dir = root / "versions" / version_key
    if version_dir.exists() and not (version_dir / "complete.json").exists():
        completed = sorted((root / "versions").glob(version_key + "-*/complete.json"))
        version_dir = completed[-1].parent if completed else root / "versions" / (version_key + "-" + uuid.uuid4().hex[:8])
    paths = package_paths(version_dir)
    if selected.get("rea_prefix"):
        paths["rea_prefix"] = Path(selected["rea_prefix"])
        paths["rea_package"] = paths["rea_prefix"] / "node_modules/rea-agents"
    if selected.get("spec_kit_tools"):
        paths["uv_tools"] = Path(selected["spec_kit_tools"])
        paths["uv_bin"] = Path(selected["spec_kit_bin"])
    if "reverse" in selection and selected.get("reverse_root"):
        paths["reverse"] = Path(selected["reverse_root"])
    retirement = plan.get("retired_project_continuity")
    if retirement and not installed:
        raise InstallError("旧 project-continuity 退役计划要求活动 installed receipt")
    transaction = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ-") + uuid.uuid4().hex[:8]
    tx = root / ".installer/transactions" / transaction
    journal = Journal(tx)
    if "craft" in selection:
        journal.data["craft_contract"] = copy.deepcopy(cr.CONTRACT)
        journal.data["craft_client"] = client
        journal.save()
    atomic(tx / "plan.json", encode_json(plan))
    try:
        stage = tx / "agent"
        stage.mkdir(parents=True)
        before_config = b""
        if config is not None:
            before_config = config.read_bytes() if config.exists() else (b"{}\n" if client in ("pi", "claude") else b"")
            atomic(stage / config.name, before_config)
        env = process_env(root, paths, stage, client, selected.get("node") or sys.executable)
        node = npm = node_version = None
        if "rea" in selection:
            node, npm, node_version = node_and_npm(selected.get("node"), components["rea"]["node_engine"], root, env)
        complete = load_json(version_dir / "complete.json", {})
        if complete:
            if "rea" in selection:
                if not Path(paths["rea_package"]).is_dir():
                    raise InstallError("既有 REA 原包缺失；拒绝复用，保留现场")
                if tree_hash(paths["rea_package"]) != complete.get("rea_sha256"):
                    raise InstallError("既有 REA 原包发生漂移；拒绝复用，保留现场")
            if "spec_kit" in selection and complete.get("spec_kit_sha256"):
                if not Path(paths["uv_tools"]).is_dir():
                    raise InstallError("既有 Spec Kit 隔离工具环境缺失；拒绝复用")
                if tree_hash(paths["uv_tools"]) != complete["spec_kit_sha256"]:
                    raise InstallError("既有 Spec Kit 隔离工具环境发生漂移；拒绝复用")
        else:
            if version_dir.exists():
                raise InstallError("存在未完成的版本目录；检查失败事务后移走该目录再重试")
            version_dir.mkdir(parents=True)
        if "rea" in selection:
            if not complete and not selected.get("rea_prefix"):
                run([node, npm, "install", "--prefix", paths["rea_prefix"], "--no-audit", "--no-fund", "--registry", "https://registry.npmjs.org", "rea-agents@" + components["rea"]["version"]], cwd=root, env=env)
            package = load_json(paths["rea_package"] / "package.json", {})
            if package.get("name") != "rea-agents" or package.get("version") != components["rea"]["version"]:
                raise InstallError("npm 安装包身份与冻结计划不一致")
            if not complete and not selected.get("rea_prefix"):
                lock = load_json(paths["rea_prefix"] / "package-lock.json", {})
                if lock.get("packages", {}).get("node_modules/rea-agents", {}).get("integrity") != components["rea"]["integrity"]:
                    raise InstallError("REA npm lock integrity 与冻结元数据不一致")
        specify = None
        if "spec_kit" in selection:
            if not complete and not selected.get("spec_kit_tools"):
                run([selected["uv"], "--no-config", "tool", "install", "--default-index", "https://pypi.org/simple", "--python", sys.executable, "specify-cli==" + components["spec_kit"]["version"]], cwd=root, env=env)
            specify = paths["uv_bin"] / ("specify.exe" if os.name == "nt" else "specify")
            if not specify.is_file():
                raise InstallError("uv 工具目录缺少 specify 可执行文件")
            spec_version = object_output(run([specify, "version", "--json"], cwd=root, env=env), "specify version")
            if spec_version.get("cli_version") != components["spec_kit"]["version"]:
                raise InstallError("specify version 的 cli_version 与计划不一致")
        reverse = None
        if "reverse" in selection:
            if identity is not None:
                reverse = identity
            else:
                if not complete or not Path(paths["reverse"]).is_dir():
                    run([selected["git"], "clone", "--no-checkout", components["reverse"]["repository"], paths["reverse"]], cwd=root, env=env)
                    run([selected["git"], "-C", paths["reverse"], "checkout", "--detach", components["reverse"]["commit"]], cwd=root, env=env)
                reverse = reverse_identity(paths["reverse"])
            if reverse["commit"] != components["reverse"]["commit"]:
                raise InstallError("reverse checkout commit 不符")
        guard = None
        if "shell_guard" in selection:
            entry = manifest["shell_guard"]
            component = components["shell_guard"]
            guard_root = Path(selected["shell_guard_root"]) if selected.get("shell_guard_root") else paths["shell_guard_repo"] / entry["plugin_dir"]
            if not selected.get("shell_guard_root"):
                if not complete:
                    run([selected["git"], "clone", "--no-checkout", component["repository"], paths["shell_guard_repo"]], cwd=root, env=env)
                    run([selected["git"], "-C", paths["shell_guard_repo"], "checkout", "--detach", component["commit"]], cwd=root, env=env)
                sg.checkout_identity(guard_root, component, run)
            local = sg.validate_package(guard_root, entry)
            if complete and complete.get("shell_guard_sha256") != local["tree_hash"]:
                raise InstallError("shell-guard 插件发生漂移或缺少 hash；拒绝复用")
            guard = {**component, **local}
        craft_installed = None
        if "craft" in selection:
            cr.reverse_contract(selected.get("reverse_root"), plan["craft_reverse_contract"])
            craft_installed = cr.install_bundle(components["craft"], version_dir / (cc.BUNDLE_DIRECTORY if cr is cc else "craft-bundle"), journal)
            if cr is cc and cc.profile_identity(craft_installed) != plan["craft_runtime"].get("profile"):
                raise InstallError("Craft Codex copied runtime profile identity differs from frozen plan")
        desired_config = None
        managed_rea = None
        if "rea" in selection:
            if client == "claude":
                desired = json.loads(before_config or b"{}")
                # Preserve explicit local provider environment/options; never invent machine paths.
                managed_rea = copy.deepcopy(desired.get("mcpServers", {}).get("rea") or {})
                managed_rea.update({"command": str(node), "args": [str(paths["rea_package"] / "scripts/rea.mjs"), "mcp"]})
                desired.setdefault("mcpServers", {})["rea"] = managed_rea
                desired_config = encode_json(desired)
            else:
                rea = [node, paths["rea_package"] / "scripts/rea.mjs"]
                setup = rea + ["setup", "--client", client, "--skill=false"]
                dryrun = object_output(run(setup + ["--dry-run", "--json"], cwd=root, env=env), "REA setup dry-run")
                atomic(tx / "setup-dryrun.json", encode_json(dryrun))
                applied = object_output(run(setup + ["--yes", "--json"], cwd=root, env=env), "REA setup yes")
                atomic(tx / "setup-result.json", encode_json(applied))
                staged_config = (stage / config.name).read_bytes()
                if client == "pi":
                    original, modified = json.loads(before_config), json.loads(staged_config)
                    managed_rea = copy.deepcopy(modified.get("mcpServers", {}).get("rea"))
                    if not managed_rea:
                        raise InstallError("官方 setup 未生成 mcpServers.rea")
                    for value in (original, modified):
                        value.setdefault("mcpServers", {}).pop("rea", None)
                        if not value["mcpServers"]: value.pop("mcpServers")
                    if original != modified:
                        raise InstallError("官方 setup 修改了非 REA 字段；拒绝合并")
                    desired = json.loads(before_config)
                    desired.setdefault("mcpServers", {})["rea"] = managed_rea
                    desired_config = encode_json(desired)
                else:
                    desired_config = codex_merge(before_config, staged_config)
                    parsed, _, _ = toml_parts(desired_config)
                    managed_rea = parsed.get("mcp_servers", {}).get("rea")
                    if not managed_rea:
                        raise InstallError("官方 setup 未生成 mcp_servers.rea")
            if abs_path(managed_rea.get("command", ".")) != abs_path(node) or str(paths["rea_package"] / "scripts/rea.mjs") not in managed_rea.get("args", []):
                raise InstallError("官方 setup 没有登记本事务的绝对 Node/REA 入口")
            if any(key in managed_rea for key in ("disabled_tools", "enabled_tools", "toolExposure")):
                raise InstallError("REA 注册含工具过滤；本组合要求完整 tools")
        generated = tx / "project"
        generated_files = []
        ownership = ownership_index(root, previous)
        init_project = "spec_kit" in selection and "spec_kit" not in previous_selection and project is not None
        if init_project:
            foreign = [] if not project.exists() else [p for p in project.rglob("*") if (p.is_file() or p.is_symlink()) and not owned_project_file(p, ownership)]
            if foreign:
                raise InstallError("首次 init 的成果目录必须不存在或为空；不会覆盖既有项目。请选择独立新项目（发现非本安装根文件: " + str(foreign[0]) + "）")
            run(specify_init_args(specify, generated, client), cwd=root, env=env)
            if not (generated / ".specify").is_dir():
                raise InstallError("specify init 未生成 .specify")
            native = generated / (".pi/prompts" if client == "pi" else (".claude" if client == "claude" else ".agents/skills"))
            if not native.is_dir() or not any(native.rglob("*.md")):
                raise InstallError(f"Spec Kit 未生成已支持的 {client} 原生资源；保留暂存结果，拒绝切换")
            generated_files = [p for p in generated.rglob("*") if p.is_file()]
            for item in generated.rglob("*"):
                if item.is_symlink():
                    raise InstallError("Spec Kit 生成结果含符号链接；当前迁移器不支持，保留暂存目录")
            staged_path_strings = (str(generated).encode(), generated.as_posix().encode())
            if any(any(marker in p.read_bytes() for marker in staged_path_strings) for p in generated_files):
                raise InstallError("Spec Kit 生成文件绑定暂存绝对路径；当前迁移器无法保证可移植，拒绝切换")
        # Recheck every frozen input before the first scoped mutation.
        validate_plan(plan)
        resources = {"rea_manual": bool(plan["resource_selection"]["rea_manual"]), "exclude_rea_skill": [str(abs_path(p)) for p in plan["resource_selection"]["exclude_rea_skill"]], "rea_manual_skill": None}
        adapter_key = adapter_identity_key() if client == "pi" else None
        adapter = None
        entry_hashes = {}
        managed_agents = None
        if client == "pi" and ("reverse" in selection or resources["rea_manual"]):
            adapter = root / "adapters" / adapter_key / "pi"
            if "reverse" in selection:
                legacy_skill = owned_skill_hashes(previous, receipt_path)
                for source in (REPO / "adapters/pi").rglob("*"):
                    if source.is_file():
                        target = adapter / source.relative_to(REPO / "adapters/pi")
                        data = source.read_bytes()
                        entry_hashes[str(target.resolve())] = digest(data)
                        journal.write(target, data)
            else:
                target = adapter / "manual/rea-manual/SKILL.md"
                data = (REPO / "adapters/pi/manual/rea-manual/SKILL.md").read_bytes()
                entry_hashes[str(target.resolve())] = digest(data)
                journal.write(target, data)
            location = encode_json({"receipt": str(receipt_path)})
            entry_hashes[str((adapter / "receipt-location.json").resolve())] = digest(location)
            journal.write(adapter / "receipt-location.json", location)
            if "reverse" in selection:
                write_host_file(journal, ownership, agent / "skills/reverse-workflow/SKILL.md", pi_global_skill_text(receipt_path).encode(), client="Pi", legacy=legacy_skill, owner_receipt=receipt_path, entries=entry_hashes)
        elif "reverse" in selection and client == "codex":
            agents_path, agents, block, skill_path, skill = codex_entry_preflight(selected)
            journal.write(agents_path, agents, "section")
            managed_agents = {"path": str(agents_path.resolve()), "owner": str(receipt_path.resolve()), "sha256": digest(block)}
            write_host_file(journal, ownership, skill_path, skill, client="Codex", owner_receipt=receipt_path, entries=entry_hashes)
        elif "reverse" in selection and client == "claude":
            skill = (REPO / "adapters/claude/skills/reverse-workflow/SKILL.md").read_text(encoding="utf-8").replace("{{RECEIPT}}", str(receipt_path)).encode()
            write_host_file(journal, ownership, agent / "skills/reverse-workflow/SKILL.md", skill, client="Claude", owner_receipt=receipt_path, entries=entry_hashes)
            entry = (REPO / "adapters/claude/CLAUDE.md").read_text(encoding="utf-8").replace("{{RECEIPT}}", str(receipt_path)).encode()
            write_host_file(journal, ownership, project / "CLAUDE.md", entry, client="Claude", owner_receipt=receipt_path, entries=entry_hashes)
        craft_data = None
        if "craft" in selection:
            craft_resources = version_dir / (cc.RESOURCE_DIRECTORY if cr is cc else "craft-pi")
            craft_files = cr.resource_files(REPO, receipt_path)
            if cr.resource_identity(craft_files) != plan["craft_resources"]:
                raise InstallError("Craft execution resource source inventory/hash drift before write")
            for name, data in craft_files.items():
                target = cr.no_links(craft_resources / name)
                write_host_file(journal, ownership, target, data, client="Craft", owner_receipt=receipt_path, entries=entry_hashes)
            craft_data = {**craft_installed, "contract": copy.deepcopy(cr.CONTRACT), "resources": str(craft_resources),
                          "resource_hashes": {k: digest(v) for k, v in craft_files.items()},
                          (cc.RUNTIME_KEY if cr is cc else "pi_runtime"): plan["craft_runtime"]}
            if cr is cc:
                craft_data["entry"] = str(craft_resources / "entry.py")
        if client == "pi" and agent is not None and (adapter is not None or resources["exclude_rea_skill"] or retirement or "shell_guard" in selection):
            settings_path = agent / "settings.json"
            settings = load_json(settings_path, {})
            before_settings = copy.deepcopy(settings)
            old_adapter = (previous.get("adapter") or {}).get("root")
            wanted = str(adapter) if adapter is not None and "reverse" in selection else None
            packages = settings.get("packages", [])
            if not isinstance(packages, list):
                raise InstallError("Pi settings.packages 必须是数组")
            packages = [p for p in packages if not (old_adapter and old_adapter != wanted and (p == old_adapter or (isinstance(p, dict) and p.get("source") == old_adapter)))]
            if wanted and not any(p == wanted or (isinstance(p, dict) and p.get("source") == wanted) for p in packages):
                packages.append(wanted)
            if retirement and retirement.get("registration") is not None:
                matches = [p for p in packages if pu.registration_matches(p, retirement["root"], agent)]
                if len(matches) != 1 or matches[0] != retirement["registration"]:
                    raise InstallError("旧 project-continuity 注册自 plan 后发生变化；拒绝静默保留插件")
                packages.remove(matches[0])
            skills = settings.get("skills", [])
            if not isinstance(skills, list):
                raise InstallError("Pi settings.skills 必须是数组")
            skills = list(skills)
            for resource in resources["exclude_rea_skill"]:
                exclusion = "-" + str(abs_path(resource))
                if exclusion not in skills:
                    skills.append(exclusion)
            if resources["rea_manual"]:
                manual = str(adapter / "manual/rea-manual/SKILL.md")
                resources["rea_manual_skill"] = manual
                if manual not in skills:
                    skills.append(manual)
            if packages:
                settings["packages"] = packages
            else:
                settings.pop("packages", None)
            if skills:
                settings["skills"] = skills
            else:
                settings.pop("skills", None)
            if "shell_guard" in selection:
                settings = sg.merge_settings(settings, selected, guard["root"], previous, plan.get("shell_guard_migration"), manifest["shell_guard"])
            craft_replacements = []
            if "craft" in selection:
                settings, craft_replacements = cr.merge_settings(settings, agent, previous, craft_data["resources"])
            if settings != before_settings:
                observed = digest(settings_path.read_bytes()) if settings_path.exists() else None
                if observed != plan["config_inputs"][str(settings_path)]:
                    raise InstallError("Pi settings 在激活前发生漂移；事务回退")
                replacements = list(craft_replacements)
                if "shell_guard" in selection:
                    old_root = ((previous.get("shell_guard") or {}).get("root") or (plan.get("shell_guard_migration") or {}).get("root"))
                    if old_root and guard and not sg.same_path(old_root, guard["root"]):
                        old_items = [p for p in before_settings.get("packages", []) if sg.same_path(sg.local_source(p, agent), old_root)]
                        new_items = [p for p in settings.get("packages", []) if sg.same_path(sg.local_source(p, agent), guard["root"])]
                        if old_items and new_items:
                            replacements.append({"before": old_items[0], "after": new_items[0]})
                if replacements:
                    journal.write(settings_path, encode_json(settings), "json", replacements=replacements)
                else:
                    journal.write(settings_path, encode_json(settings), "json")
        if desired_config is not None:
            observed = digest(config.read_bytes()) if config.exists() else None
            if observed != plan["config_inputs"][str(config)]:
                raise InstallError("MCP 配置在激活前发生漂移；事务回退")
            journal.write(config, desired_config, "json" if client in ("pi", "claude") else "toml")
        routing_paths = [item["path"] for item in (plan.get("routing_ownership") or {}).get("disabled_skills", [])]
        if routing_paths:
            current_config = ro.config_bytes(selected)
            expected_config = desired_config if desired_config is not None else (before_config or b"")
            if current_config != expected_config:
                raise InstallError("Codex Skill configuration drift before activation; transaction rollback")
            journal.write(config, ro.disable(current_config, routing_paths), "codex-skills")
        for source in generated_files:
            target = project / source.relative_to(generated)
            if target.exists() and target.read_bytes() != source.read_bytes():
                raise InstallError(f"项目生成文件冲突: {target}")
            journal.write(target, source.read_bytes())
        if "rea" in selection:
            final_rea_hash = tree_hash(paths["rea_package"])
            if complete.get("rea_sha256") and final_rea_hash != complete["rea_sha256"]:
                raise InstallError("官方命令运行期间 REA 原包发生改变；拒绝记录为原包成功")
            complete["rea_sha256"] = final_rea_hash
        if "spec_kit" in selection:
            complete["specify_sha256"] = digest(specify.read_bytes())
            spec_tree_hash = tree_hash(paths["uv_tools"])
            if complete.get("spec_kit_sha256") and complete["spec_kit_sha256"] != spec_tree_hash:
                raise InstallError("Spec Kit 隔离工具环境发生漂移；拒绝复用")
            complete["spec_kit_sha256"] = spec_tree_hash
        if "reverse" in selection:
            complete["reverse_sha256"] = tree_hash(paths["reverse"], exclude_git=True)
        if "shell_guard" in selection:
            guard_migration = plan.get("shell_guard_migration")
            if guard_migration and sg.validate_package(guard_migration["root"], manifest["shell_guard"], development=True)["tree_hash"] != guard_migration["tree_hash"]:
                raise InstallError("shell-guard 迁移源在安装期间漂移；事务回退")
            if plan.get("everything_es_identity") and not sg.same_executable(sg.executable_identity(selected["everything_es"]), plan["everything_es_identity"]):
                raise InstallError("Everything CLI 在安装期间漂移；事务回退")
            if plan.get("everything_gui_identity") and not sg.same_executable(sg.gui_identity(selected["everything_gui"]), plan["everything_gui_identity"]):
                raise InstallError("Everything GUI 在安装期间漂移；事务回退")
            if sg.tree_hash(guard["root"]) != guard["tree_hash"]:
                raise InstallError("shell-guard 插件在安装期间漂移；事务回退")
            if guard["mode"] == "clone-frozen-commit":
                sg.checkout_identity(guard["root"], components["shell_guard"], run)
            complete["shell_guard_sha256"] = guard["tree_hash"]
        if "craft" in selection:
            if not cr.same_content(cr.bundle(craft_installed["root"]), components["craft"]):
                raise InstallError("Craft installed bundle drift before receipt")
            cr.validate_plan(plan, manifest["craft"])
            cr.validate_resources(plan, REPO)
            if (cc.runtime_identity if cr is cc else cr.pi_runtime)(selected, components["craft"], run) != plan["craft_runtime"]:
                raise InstallError("Craft explicit runtime drift before receipt activation")
            complete["craft_sha256"] = craft_installed["sha256"]
        if "craft" in selection:
            journal.write(version_dir / "complete.json", encode_json(complete))
        else:
            atomic(version_dir / "complete.json", encode_json(complete))
        receipt_paths = {}
        if "rea" in selection:
            receipt_paths.update({"rea_prefix": str(paths["rea_prefix"]), "rea_package": str(paths["rea_package"])})
        if "spec_kit" in selection:
            receipt_paths.update({"uv_tools": str(paths["uv_tools"]), "uv_bin": str(paths["uv_bin"])})
        if "reverse" in selection:
            receipt_paths["reverse"] = str(paths["reverse"])
        if "shell_guard" in selection:
            receipt_paths["shell_guard"] = guard["root"]
        if "craft" in selection:
            receipt_paths["craft"] = craft_installed["root"]
        checks = {"selected_components": "passed", "scoped_config": "passed"}
        if "rea" in selection:
            checks["package_identity"] = "passed"
            checks["official_setup_staged"] = "passed"
        if "spec_kit" in selection:
            checks["specify_version"] = "passed"
        checks["project_init"] = "created" if init_project else ("preserved-existing" if selected.get("project") else "not-selected")
        managed_shell_guard = copy.deepcopy(previous.get("shell_guard_config") or {})
        if selected.get("everything_es"):
            managed_shell_guard.update({"esPath": selected["everything_es"], "executable": plan["everything_es_identity"]})
        if selected.get("everything_gui"):
            managed_shell_guard.update({"guiPath": selected["everything_gui"], "gui_executable": plan["everything_gui_identity"]})
        if selected.get("everything_autostart"):
            managed_shell_guard["autostart"] = True
        managed_shell_guard = managed_shell_guard or None
        receipt = {
            "schema_version": 1,
            "installed": True,
            "meaning": "official packages and scoped configuration installed; host acceptance is separate",
            "adapter_version": ADAPTER_VERSION,
            "installer_version": INSTALLER_VERSION,
            "client_version": "unverified; host CLI not executed",
            "transaction": transaction,
            "history": list(previous.get("history") or []) + [transaction],
            "previous_transaction": previous.get("transaction"),
            "scope": {"components": selection, **{key: selected[key] for key in IDENTITY_KEYS}},
            "components": components,
            "paths": receipt_paths,
            "runtime": {"node": node, "node_version": node_version, "node_sha256": digest(Path(node).read_bytes()) if node else None, "specify": str(specify) if specify else None},
            "reverse": reverse,
            "craft": craft_data,
            "installer_source": plan.get("installer_source"),
            "craft_reverse_contract": plan.get("craft_reverse_contract"),
            "craft_contract": copy.deepcopy(cr.CONTRACT) if craft_data else None,
            "craft_source": {key: selected[key] for key in (cc.SOURCE_OPTIONS if cr is cc else ("craft_bundle", "craft_pi_node", "craft_pi_entry", "craft_pi_distribution", "craft_pi_version"))} if craft_data else None,
            "craft_update": plan.get("craft_update"),
            "shell_guard": guard,
            "shell_guard_config": managed_shell_guard,
            "adapter": {"root": str(adapter) if adapter else None, "key": adapter_key, "codex_plugin_reference": (reverse or {}).get("codex_plugin")},
            "routing_control_status": ro.host_status(selected),
            "routing_ownership": ro.activated(plan.get("routing_ownership")),
            "resource_selection": resources,
            "entry_hashes": entry_hashes,
            "managed_rea_config": managed_rea,
            "managed_agents": managed_agents,
            "hashes": complete,
            "checks": checks,
            "validation": limits(selected),
            "config_diff": [{"path": e["path"], "before_sha256": e["before_sha256"], "after_sha256": e["after_sha256"]} for e in journal.data["files"]],
            "backup": str(journal.path),
        }
        routing_failures = ro.failures({"scope": selected, "routing_ownership": ro.activated(plan.get("routing_ownership"))})
        if routing_failures:
            raise InstallError("Routing ownership drift before receipt: " + "; ".join(routing_failures))
        journal.write(receipt_path, encode_json(receipt), "file")
        journal.finish("committed")
        return receipt
    except Exception as exc:
        journal.data["failure"] = {"type": type(exc).__name__, "message": str(exc)}
        journal.data["rollback"] = restore_journal(journal.path, apply=True, defer_receipt=receipt_path)
        journal.finish("failed")
        raise


def verify(root):
    root = Path(root)
    receipt = load_json(root / ".installer/receipt.json", {})
    if not receipt.get("installed"):
        raise InstallError("没有活动 installed receipt；先 install --apply，或检查失败事务")
    failures = ro.failures(receipt)
    selection = set(receipt_components(receipt))
    paths = receipt.get("paths", {})
    hashes = receipt.get("hashes", {})
    scope = receipt.get("scope", {})
    runtime = receipt.get("runtime") or {}
    client = scope.get("client", "none")
    agent = Path(scope["agent_dir"]) if scope.get("agent_dir") else None
    project = Path(scope["project"]) if scope.get("project") else None
    if "rea" in selection:
        if paths.get("rea_package") and tree_hash(paths["rea_package"]) != hashes.get("rea_sha256"):
            failures.append("REA original package identity drift")
        if runtime.get("node") and runtime.get("node_sha256"):
            try:
                if digest(Path(runtime["node"]).read_bytes()) != runtime["node_sha256"]:
                    failures.append("Node runtime identity drift")
            except OSError:
                failures.append("Node runtime missing")
        if not receipt.get("managed_rea_config"):
            failures.append("REA managed configuration missing")
        else:
            config_path = Path(scope["client_config"]) if scope.get("client_config") else None
            try:
                if config_path is None or not config_path.is_file():
                    failures.append("REA host configuration missing")
                else:
                    entry = config_rea_entry(client, config_path) or {}
                    if entry.get("command") != runtime.get("node") or str(Path(paths["rea_package"]) / "scripts/rea.mjs") not in entry.get("args", []):
                        failures.append("REA MCP launcher drift")
                    if entry != receipt["managed_rea_config"]:
                        failures.append("REA managed configuration drift")
            except (InstallError, OSError, ValueError) as exc:
                failures.append("REA host configuration unreadable: " + str(exc))
    if "spec_kit" in selection:
        if paths.get("uv_tools") and tree_hash(paths["uv_tools"]) != hashes.get("spec_kit_sha256"):
            failures.append("Spec Kit environment identity drift")
        specify = runtime.get("specify")
        if not specify or not Path(specify).is_file():
            failures.append("specify executable missing")
        elif hashes.get("specify_sha256") and digest(Path(specify).read_bytes()) != hashes["specify_sha256"]:
            failures.append("specify executable identity drift")
        if project:
            native = project / (".pi/prompts" if client == "pi" else (".claude" if client == "claude" else ".agents/skills"))
            if not (project / ".specify").is_dir():
                failures.append("Spec Kit project .specify directory missing")
            if not native.is_dir() or not any(native.rglob("*.md")):
                failures.append("Spec Kit project native resources missing")
    if "reverse" in selection:
        stored_reverse = receipt.get("reverse") or {}
        reverse_root = stored_reverse.get("root")
        if not reverse_root or not reverse_identity_matches(stored_reverse, reverse_identity(reverse_root)):
            failures.append("reverse working copy drift")
        elif hashes.get("reverse_sha256") and hashes["reverse_sha256"] != stored_reverse.get("working_tree_sha256"):
            failures.append("reverse working copy identity drift")
    if "craft" in selection or receipt.get("craft"):
        try:
            failures.extend(craft_record_profile(receipt).failures(receipt))
        except (InstallError, TypeError, ValueError) as exc:
            failures.append(str(exc))
    if "shell_guard" in selection:
        failures.extend(sg.failures(receipt, load_json(REPO / "components.json")["shell_guard"], run))
    resources = receipt.get("resource_selection") or {}
    if client == "pi":
        settings = load_json(agent / "settings.json", {}) if agent else {}
        packages = settings.get("packages", [])
        packages = packages if isinstance(packages, list) else []
        adapter_root = (receipt.get("adapter") or {}).get("root")
        if adapter_root and "reverse" in selection:
            if not any(p == adapter_root or (isinstance(p, dict) and p.get("source") == adapter_root) for p in packages):
                failures.append("Pi package registration missing or changed")
            global_skill = agent / "skills/reverse-workflow/SKILL.md"
            if not global_skill.is_file() or str(root / ".installer/receipt.json") not in global_skill.read_text(encoding="utf-8"):
                failures.append("Pi global skill missing or receipt path drift")
        skills = settings.get("skills", [])
        skills = skills if isinstance(skills, list) else []
        for resource in resources.get("exclude_rea_skill") or []:
            if "-" + str(resource) not in skills:
                failures.append("Pi REA skill exclusion missing: " + str(resource))
        manual = resources.get("rea_manual_skill")
        if manual:
            if not Path(manual).is_file():
                failures.append("Pi rea-manual skill file missing: " + str(manual))
            elif manual not in skills:
                failures.append("Pi rea-manual skill registration missing")
    elif client == "codex" and "reverse" in selection:
        global_agents = agent / "AGENTS.md"
        if not global_agents.is_file() or str(root / ".installer/receipt.json") not in global_agents.read_text(encoding="utf-8"):
            failures.append("Codex AGENTS.md missing or receipt path drift")
        global_skill = Path(normalized_identity(scope, selection)["codex_skills_root"]) / "reverse-workflow/SKILL.md"
        if not global_skill.is_file() or str(root / ".installer/receipt.json") not in global_skill.read_text(encoding="utf-8"):
            failures.append("Codex global Skill missing or receipt path drift")
        managed_agents = receipt.get("managed_agents")
        if managed_agents:
            try:
                section = managed_section(global_agents.read_bytes())
                if not section or ownership_key(section[0]) != ownership_key(root / ".installer/receipt.json") or digest(section[3]) != managed_agents.get("sha256"):
                    failures.append("Codex AGENTS.md managed section drift")
            except (InstallError, OSError):
                failures.append("Codex AGENTS.md managed section unreadable")
    elif client == "claude" and "reverse" in selection:
        global_skill = agent / "skills/reverse-workflow/SKILL.md"
        if not global_skill.is_file() or str(root / ".installer/receipt.json") not in global_skill.read_text(encoding="utf-8"):
            failures.append("Claude global skill missing or receipt path drift")
        if not project or not (project / "CLAUDE.md").is_file():
            failures.append("Claude project entry missing")
    for path, expected in (receipt.get("entry_hashes") or {}).items():
        target = Path(path)
        try:
            observed = digest(target.read_bytes()) if target.is_file() else None
        except OSError:
            observed = None
        if observed != expected:
            failures.append("installer entry drift: " + str(path))
    return {"ok": not failures, "failures": failures, "routing_control_status": ro.host_status(scope), "transaction": receipt["transaction"], "validation": receipt.get("validation", limits()), "note": "verify 只核选定组件身份和实际配置；不会启动宿主/MCP或声称真实任务通过"}


def accept(root):
    root = Path(root)
    receipt = load_json(root / ".installer/receipt.json", {})
    if not receipt.get("installed"):
        raise InstallError("没有活动 installed receipt；先 install --apply")
    static = verify(root)
    if not static["ok"]:
        return {"ok": False, "root": str(root), "checks": [{"name": "static_verify", "ok": False, "detail": static["failures"]}], "unverified": [], "note": "Static verification failed; acceptance commands were not executed"}
    selected = set(receipt.get("scope", {}).get("components", ["rea", "spec_kit", "reverse"]))
    result = {"ok": True, "root": str(root), "components": sorted(selected), "checks": [], "unverified": []}
    if "shell_guard" in selected:
        result["unverified"].append("shell-guard host loading, tool interception and Everything availability; not a sandbox")
    def check(name, ok, detail, fatal=True):
        result["checks"].append({"name": name, "ok": bool(ok), "detail": detail})
        if not ok and fatal: result["ok"] = False
    if "craft" in selected:
        result["unverified"].append("Craft native host/provider/model/effort, bounded tools, cancellation, cleanup and independent business acceptance; offline inspection does not qualify execution")
        profile = craft_record_profile(receipt)
        if profile is cc:
            try:
                inspection = profile.inspect_backend(receipt, run)
                check("craft_codex_offline_entry_contract", True, {**inspection, "qualification": "offline metadata only; live execution unverified"})
            except (InstallError, OSError, ValueError, KeyError, TypeError) as exc:
                check("craft_codex_offline_entry_contract", False, str(exc))
    if "rea" in selected:
        node = receipt["runtime"]["node"]
        package = Path(receipt["paths"]["rea_package"])
        env = os.environ.copy()
        managed_env = receipt.get("managed_rea_config", {}).get("env", {}) or {}
        for key, value in managed_env.items():
            if value is not None: env[key] = str(value)
        try:
            raw = run([node, package / "scripts/rea.mjs", "mcp", "doctor", "--format", "json", "--full-output"], cwd=root, env=env)
            doctor = json.loads(raw)
            data = doctor.get("data", doctor)
            inventory = data.get("inventory", {}).get("tools", {})
            ok = bool(data.get("healthy")) and inventory.get("missing") == [] and inventory.get("unexpected") == [] and inventory.get("duplicates") == []
            check("rea_mcp", ok, {"healthy": data.get("healthy"), "server": data.get("server"), "tools": {k: inventory.get(k) for k in ("expected", "observed", "missing", "unexpected", "duplicates")}})
            provider = subprocess.run([node, package / "scripts/rea.mjs", "doctor", "--provider", "jadx", "--format", "json", "--full-output"], cwd=root, env=env, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120)
            provider_raw = json.loads(provider.stdout) if provider.stdout.strip() else {"ok": False, "error": "no provider doctor output"}
            provider_data = provider_raw.get("data") or provider_raw.get("error") or provider_raw
            jadx_checks = provider_data.get("scope_checks", [])
            jadx = next((item for item in jadx_checks if item.get("name") == "jadx"), {})
            check("rea_provider_jadx", bool(jadx.get("ok")), {"returncode": provider.returncode, "classification": jadx.get("classification"), "detail": jadx.get("detail"), "remediation": jadx.get("remediation")}, fatal=False)
        except (InstallError, ValueError, OSError) as exc:
            check("rea_mcp", False, str(exc))
    if "reverse" in selected:
        reverse = receipt.get("reverse") or {}
        try:
            current = reverse_identity(reverse["root"])
            same_commit = current.get("commit") == reverse.get("commit")
            check("reverse_identity", same_commit and bool(current.get("routers")), {"commit": current.get("commit"), "dirty": current.get("dirty"), "routers": current.get("routers"), "warning": "working tree dirty; commit before publishing a release" if current.get("dirty") else None})
            with tempfile.TemporaryDirectory(prefix="reverse-acceptance-") as temp:
                hint = "offline apk reverse"
                if os.name == "nt":
                    router = Path(reverse["root"]) / "skills/scripts/master-route.ps1"
                    command = ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(router), "-Hint", hint, "-OutDir", temp]
                else:
                    router = Path(reverse["root"]) / "skills/scripts/master-route.sh"
                    command = ["bash", str(router), "--hint", hint, "--out-dir", temp]
                completed = subprocess.run(command, cwd=reverse["root"], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120)
                scope_file = Path(temp) / "route-scope.md"
                check("reverse_router", completed.returncode == 0 and scope_file.is_file(), {"returncode": completed.returncode, "scope": str(scope_file) if scope_file.is_file() else None})
        except (InstallError, OSError, subprocess.TimeoutExpired) as exc:
            check("reverse_router", False, str(exc))
    if "spec_kit" in selected:
        specify = Path(receipt["runtime"]["specify"])
        try:
            version = object_output(run([specify, "version", "--json"], cwd=root), "specify version")
            expected = receipt["components"]["spec_kit"]["version"]
            check("spec_kit_version", version.get("cli_version") == expected, {"expected": expected, "observed": version.get("cli_version")})
            if receipt["scope"].get("project"):
                with tempfile.TemporaryDirectory(prefix="speckit-acceptance-") as temp:
                    project = Path(temp) / "project"
                    init_args = specify_init_args(specify, project, receipt["scope"]["client"])
                    completed = subprocess.run(init_args, cwd=root, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=180)
                    check("spec_kit_init", completed.returncode == 0 and (project / ".specify").is_dir(), {"returncode": completed.returncode, "native": str(project / ".specify") if (project / ".specify").is_dir() else None})
        except (InstallError, OSError, subprocess.TimeoutExpired) as exc:
            check("spec_kit", False, str(exc))
    result["note"] = "accept 只使用临时验收目录和官方诊断；不会修改活动宿主配置、REA/Spec Kit 包或用户成果项目"
    return result


def restore(root, transaction=None, apply=False):
    root = Path(root)
    receipt = load_json(root / ".installer/receipt.json", {})
    if receipt.get("craft") or "craft" in (receipt.get("scope") or {}).get("components", []):
        craft_record_profile(receipt)
    transaction = transaction or receipt.get("transaction")
    if not transaction or not re.fullmatch(r"[A-Za-z0-9-]+", transaction):
        raise InstallError("需要有效的 --transaction，或活动 receipt")
    path = root / ".installer/transactions" / transaction / "journal.json"
    if not path.is_file():
        raise InstallError("找不到事务备份: " + transaction)
    if receipt.get("transaction") and transaction != receipt["transaction"]:
        raise InstallError("只允许恢复活动事务；请按最新到最旧依次回退，避免跨版本覆盖")
    journal_record = load_json(path)
    journal_contract = journal_record.get("craft_contract")
    if journal_contract is not None:
        craft_record_profile(journal_record)
    if apply:
        with locked(root):
            return {"transaction": transaction, "applied": True, "files": restore_journal(path, apply=True, defer_receipt=root / ".installer/receipt.json")}
    return {"transaction": transaction, "applied": False, "files": restore_journal(path, defer_receipt=root / ".installer/receipt.json")}
