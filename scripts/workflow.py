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

from configuration import Journal, atomic, codex_merge, digest, encode_json, load_json, restore_journal, toml_parts
from versions import InstallError, resolve, stable

REPO = Path(__file__).resolve().parents[1]
ADAPTER_VERSION = "0.2.0"


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
    aliases = {"rea": "rea", "spec-kit": "spec_kit", "spec_kit": "spec_kit", "reverse": "reverse"}
    result = []
    for raw in str(value).split(","):
        key = aliases.get(raw.strip().lower())
        if key is None or key in result:
            raise InstallError("--components 只能包含不重复的 rea, spec-kit, reverse，或 all")
        result.append(key)
    if not result:
        raise InstallError("--components 不能为空")
    return result


def needs_host(components):
    return "rea" in components or "spec_kit" in components


def needs_project(components):
    return "spec_kit" in components


def needs_agent(components):
    return "rea" in components


def detect_client(client, config=None, env=None):
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
    if config and config.exists():
        if config.suffix == ".json":
            value = load_json(config, {})
            if str(value.get("$schema", "")).startswith("https://pi.dev/schemas/"):
                evidence.add("pi")
                names.append("Pi configuration schema")
        elif config.name == "config.toml":
            value, _, _ = toml_parts(config.read_bytes())
            if any(k in value for k in ("approval_policy", "sandbox_mode", "model_reasoning_effort")):
                evidence.add("codex")
                names.append("Codex configuration keys")
    if len(evidence) != 1:
        reason = "宿主证据冲突" if evidence else "没有明确宿主标记或配置 schema 证据"
        raise InstallError(f"auto: {reason}；请指定 --client pi 或 --client codex，并提供 --agent-dir 或 --client-config。CLI 存在与模型名不代表宿主身份；未枚举环境值。")
    return evidence.pop(), names


def scope(args):
    components = selected_components(args.components)
    root = abs_path(args.root)
    explicit = abs_path(args.client_config) if args.client_config else None
    if needs_host(components):
        if args.client == "none":
            raise InstallError("所选组件需要宿主；请指定 --client pi 或 --client codex")
        client, evidence = detect_client(args.client, explicit)
    else:
        client, evidence = ("none", ["no host component selected"]) if args.client == "auto" else detect_client(args.client, explicit)
    if client == "none" and (args.agent_dir or explicit):
        raise InstallError("--client none 不能同时指定 agent/config；请选择宿主或省略这些参数")
    agent = abs_path(args.agent_dir) if args.agent_dir else (explicit.parent if explicit else None)
    if needs_agent(components) and agent is None:
        raise InstallError("所选组件需要 --agent-dir 或 --client-config；不会默认写用户 profile")
    config = (agent / ("mcp.json" if client == "pi" else "config.toml")) if agent and client != "none" else None
    if explicit and config != explicit:
        raise InstallError(f"--client-config 必须是指定 agent 目录中的 {config.name}；Pi settings.json 与 mcp.json 共用该目录")
    project = abs_path(args.project) if args.project else None
    if needs_project(components) and project is None:
        raise InstallError("所选 Spec Kit 组件需要 --project 指定独立成果项目")
    if client == "codex" and "reverse" in components and project is None:
        raise InstallError("Codex 使用 reverse 入口需要 --project 写入薄项目 skill")
    reverse = abs_path(args.reverse_root) if args.reverse_root else None
    tools = [REPO, root / "versions", root / ".installer"]
    if agent:
        tools.append(agent)
    if reverse:
        tools.append(reverse)
    if project:
        for tool in tools:
            if project == tool or project.is_relative_to(tool) or tool.is_relative_to(project):
                raise InstallError(f"成果项目与工具/配置范围重叠: {tool}")
        if project == root or root.is_relative_to(project):
            raise InstallError("成果项目不能包含安装根")
    if root == REPO or root.is_relative_to(REPO):
        raise InstallError("--root 必须在 installer 源码仓库之外")
    if bool(args.spec_kit_tools) != bool(args.spec_kit_bin):
        raise InstallError("--spec-kit-tools 与 --spec-kit-bin 必须一起提供")
    if client != "pi" and (args.rea_manual or args.exclude_rea_skill):
        raise InstallError("--rea-manual / --exclude-rea-skill 仅适用于 Pi")
    reuse = {key: str(abs_path(getattr(args, key))) if getattr(args, key) else None for key in ("rea_prefix", "spec_kit_tools", "spec_kit_bin")}
    for directory in [root / "versions", root / ".installer", *[Path(p) for p in reuse.values() if p]]:
        if project and (project == directory or project.is_relative_to(directory) or directory.is_relative_to(project)):
            raise InstallError("成果项目与复用工具目录重叠")
    return {"components": components, "root": str(root), "client": client, "evidence": evidence, "agent_dir": str(agent) if agent else None, "client_config": str(config) if config else None, "project": str(project) if project else None, "reverse_root": str(reverse) if reverse else None, "node": str(abs_path(args.node)) if args.node else shutil.which("node"), "uv": shutil.which("uv"), "git": shutil.which("git"), **reuse}


def reverse_identity(path):
    path = Path(path)
    required = ["RULES.md", "skills/config/routing.json", "skills/SKILL.md"]
    # Upstream's master skill can be at skills/SKILL.md or root SKILL.md.
    if not (path / "skills/SKILL.md").is_file() and (path / "SKILL.md").is_file():
        required[-1] = "SKILL.md"
    for name in required:
        if not (path / name).is_file():
            raise InstallError(f"reverse 工作副本缺少原生入口: {name}")
    routers = [name for name in ("skills/scripts/master-route.ps1", "skills/scripts/master-route.sh") if (path / name).is_file()]
    if not routers:
        raise InstallError("reverse 缺少原生 master-route；不会生成第二套路由")
    commit = run(["git", "-C", path, "rev-parse", "HEAD"], cwd=path)
    dirty = bool(run(["git", "-C", path, "status", "--porcelain", "--untracked-files=normal"], cwd=path))
    return {"root": str(path.resolve()), "commit": commit, "dirty": dirty, "entry_hashes": {name: digest((path / name).read_bytes()) for name in required + routers}, "working_tree_sha256": tree_hash(path, exclude_git=True), "routers": routers, "master": required[-1], "codex_plugin": str(path / "plugins/reverse-skill") if (path / "plugins/reverse-skill/.codex-plugin/plugin.json").is_file() else None}


def tree_hash(path, exclude_git=False):
    """Hash stable files without writing bytecode; UV runtime symlinks are recorded."""
    hasher = hashlib.sha256()
    for item in sorted(Path(path).rglob("*")):
        relative = item.relative_to(path)
        if "__pycache__" in relative.parts or item.suffix == ".pyc":
            continue
        if exclude_git and (".git" in relative.parts or "__pycache__" in relative.parts):
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
    if client == "codex":
        args.append("--ignore-agent-tools")
    return args


def make_plan(args, fetch=None):
    selected = scope(args)
    manifest = load_json(REPO / "components.json")
    components = resolve(manifest, **({"fetch": fetch} if fetch else {}))
    if selected["reverse_root"]:
        identity = reverse_identity(selected["reverse_root"])
        components["reverse"]["published_commit"] = components["reverse"]["commit"]
        components["reverse"]["commit"] = identity["commit"]
        components["reverse"]["local_identity"] = identity
        components["reverse"]["mode"] = "read-only-working-copy"
    else:
        components["reverse"]["mode"] = "clone-frozen-commit"
    missing = []
    if "rea" in selected["components"]:
        if not selected["node"]: missing.append("node")
    if "spec_kit" in selected["components"] and not selected["spec_kit_tools"] and not selected["uv"]:
        missing.append("uv")
    if "reverse" in selected["components"] and not selected["reverse_root"] and not selected["git"]:
        missing.append("git")
    config = Path(selected["client_config"]) if selected["client_config"] else None
    settings = Path(selected["agent_dir"]) / "settings.json" if selected["agent_dir"] and selected["client"] == "pi" else None
    input_paths = [p for p in (config, settings) if p is not None]
    inputs = {str(p): digest(p.read_bytes()) if p.exists() else None for p in input_paths}
    commands = []
    if "rea" in selected["components"]:
        commands.append(("核验只读复用 REA prefix: " + selected["rea_prefix"] + " @" + components["rea"]["version"]) if selected["rea_prefix"] else ("npm install --prefix <root>/versions/<frozen-id>/rea --registry https://registry.npmjs.org rea-agents@" + components["rea"]["version"]))
        commands.extend([f"rea setup --client {selected['client']} --skill=false --dry-run --json", f"rea setup --client {selected['client']} --skill=false --yes --json"])
    if "spec_kit" in selected["components"]:
        commands.append(("核验只读复用 Spec Kit tools/bin: " + selected["spec_kit_tools"] + " / " + selected["spec_kit_bin"] + " @" + components["spec_kit"]["version"]) if selected["spec_kit_tools"] else ("uv --no-config tool install --default-index https://pypi.org/simple specify-cli==" + components["spec_kit"]["version"]))
        commands.append(f"specify init <staging-project> --integration {selected['client']} --script py --non-interactive" + (" --ignore-agent-tools" if selected["client"] == "codex" else ""))
    return {"schema_version": 1, "adapter_version": ADAPTER_VERSION, "scope": selected, "components": components, "config_inputs": inputs, "missing_prerequisites": missing, "commands": commands, "resource_selection": {"rea_manual": args.rea_manual, "exclude_rea_skill": [str(abs_path(p)) for p in args.exclude_rea_skill]}, "limits": limits()}


def limits():
    return {"host_resource_loading": "unverified", "mcp_handshake_and_tools_schema": "unverified", "reverse_real_task": "unverified", "spec_kit_real_workflow": "unverified", "provider_installation": "not_implemented", "portable_node_download": "not_implemented; use --node", "codex_plugin_registration": "not_implemented; official existing plugin referenced through project thin skill", "existing_project_template_upgrade": "not_implemented; preserve existing project templates", "package_artifact_provenance": "official npm lock integrity checked; PyPI hashes recorded, uv resolution used, wheel not independently rehashed", "all_agents": "unsupported; pi/codex only"}


def validate_plan(plan):
    if plan.get("schema_version") != 1 or plan.get("adapter_version") != ADAPTER_VERSION:
        raise InstallError("计划 schema/adapter 版本不兼容；重新 plan")
    selected = plan["scope"]
    checked = scope(SimpleNamespace(**{**selected, **plan["resource_selection"], "components": ",".join(selected["components"]), "node": selected.get("node"), "uv": selected.get("uv"), "git": selected.get("git")}))
    for key in ("components", "root", "client", "agent_dir", "client_config", "project", "reverse_root", "node", "rea_prefix", "spec_kit_tools", "spec_kit_bin"):
        if checked[key] != selected[key]:
            raise InstallError("冻结计划包含非规范路径或范围；重新 plan")
    expected_configs = []
    if selected["client_config"]:
        expected_configs.append(Path(selected["client_config"]))
    if selected["client"] == "pi" and selected["agent_dir"]:
        expected_configs.append(Path(selected["agent_dir"]) / "settings.json")
    if set(plan["config_inputs"]) != {str(p) for p in expected_configs}:
        raise InstallError("冻结计划的配置输入范围不一致")
    manifest = load_json(REPO / "components.json")
    for key in ("rea", "spec_kit", "reverse"):
        if plan["components"][key]["repository"] != manifest[key]["repository"]:
            raise InstallError("计划的组件来源不在固定来源清单中")
    for key in plan["scope"]["components"]:
        if key in ("rea", "spec_kit") and not stable(plan["components"][key]["version"]):
            raise InstallError("计划缺少精确稳定版本")
    if "reverse" in plan["scope"]["components"] and not re.fullmatch(r"[0-9a-f]{40}", plan["components"]["reverse"]["commit"]):
        raise InstallError("计划缺少精确 reverse commit")
    for name, expected in plan["config_inputs"].items():
        p = Path(name)
        if (digest(p.read_bytes()) if p.exists() else None) != expected:
            raise InstallError(f"配置自 plan 后发生漂移，拒绝应用: {p}；重新生成计划")


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
    return {"rea_prefix": directory / "rea", "rea_package": directory / "rea/node_modules/rea-agents", "uv_tools": directory / "spec-kit/tools", "uv_bin": directory / "spec-kit/bin", "reverse": directory / "reverse-skill"}


def process_env(root, paths, agent, client, node):
    env = os.environ.copy()
    env.update({"UV_TOOL_DIR": str(paths["uv_tools"]), "UV_TOOL_BIN_DIR": str(paths["uv_bin"]), "UV_CACHE_DIR": str(root / ".installer/cache/uv"), "npm_config_cache": str(root / ".installer/cache/npm"), "PI_CODING_AGENT_DIR": str(agent), "CODEX_HOME": str(agent), "PYTHONDONTWRITEBYTECODE": "1", "GIT_TERMINAL_PROMPT": "0"})
    for key in list(env):
        if key.startswith("UV_INDEX") or key in ("UV_DEFAULT_INDEX", "UV_INDEX_URL", "UV_EXTRA_INDEX_URL", "PIP_INDEX_URL", "PIP_EXTRA_INDEX_URL"):
            env.pop(key)
    env["PATH"] = str(Path(node).parent) + os.pathsep + env.get("PATH", "")
    return env


def install(plan, args):
    validate_plan(plan)
    root = Path(plan["scope"]["root"])
    with locked(root):
        # Recheck after acquiring lock.
        validate_plan(plan)
        return _install(plan, args)


def _install_selected(plan, args):
    selected, components = plan["scope"], plan["components"]
    root = Path(selected["root"])
    agent = Path(selected["agent_dir"]) if selected["agent_dir"] else None
    project = Path(selected["project"]) if selected["project"] else None
    receipt_path = root / ".installer/receipt.json"
    previous = load_json(receipt_path, {})
    version_key = digest(encode_json({"components": {k: components[k] for k in selected["components"]}, "node": selected.get("node"), "adapter": ADAPTER_VERSION}))[:20]
    version_dir = root / "versions" / version_key
    paths = package_paths(version_dir)
    if selected.get("rea_prefix"):
        paths["rea_prefix"] = Path(selected["rea_prefix"])
        paths["rea_package"] = paths["rea_prefix"] / "node_modules/rea-agents"
    if selected.get("spec_kit_tools"):
        paths["uv_tools"] = Path(selected["spec_kit_tools"])
        paths["uv_bin"] = Path(selected["spec_kit_bin"])
    if "reverse" in selected["components"] and selected.get("reverse_root"):
        paths["reverse"] = Path(selected["reverse_root"])
    identity = components["reverse"].get("local_identity") if "reverse" in selected["components"] else None
    transaction = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ-") + uuid.uuid4().hex[:8]
    tx = root / ".installer/transactions" / transaction
    journal = Journal(tx)
    atomic(tx / "plan.json", encode_json(plan))
    try:
        stage = tx / "agent"
        stage.mkdir(parents=True)
        before_config = b""
        config = Path(selected["client_config"]) if selected["client_config"] else None
        if "rea" in selected["components"]:
            before_config = config.read_bytes() if config.exists() else (b"{}\n" if selected["client"] == "pi" else b"")
            atomic(stage / config.name, before_config)
        env = process_env(root, paths, stage, selected["client"], selected.get("node") or sys.executable)
        node = None
        npm = None
        if "rea" in selected["components"]:
            node, npm, node_version = node_and_npm(selected["node"], components["rea"]["node_engine"], root, env)
            if not selected.get("rea_prefix"):
                run([node, npm, "install", "--prefix", paths["rea_prefix"], "--no-audit", "--no-fund", "--registry", "https://registry.npmjs.org", "rea-agents@" + components["rea"]["version"]], cwd=root, env=env)
            package = load_json(paths["rea_package"] / "package.json", {})
            if package.get("name") != "rea-agents" or package.get("version") != components["rea"]["version"]:
                raise InstallError("npm 安装包身份与冻结计划不一致")
            if not selected.get("rea_prefix"):
                lock = load_json(paths["rea_prefix"] / "package-lock.json", {})
                if lock.get("packages", {}).get("node_modules/rea-agents", {}).get("integrity") != components["rea"]["integrity"]:
                    raise InstallError("REA npm lock integrity 与冻结元数据不一致")
        if "spec_kit" in selected["components"]:
            if not selected.get("spec_kit_tools"):
                run([selected["uv"], "--no-config", "tool", "install", "--default-index", "https://pypi.org/simple", "--python", sys.executable, "specify-cli==" + components["spec_kit"]["version"]], cwd=root, env=env)
            specify = paths["uv_bin"] / ("specify.exe" if os.name == "nt" else "specify")
            if not specify.is_file():
                raise InstallError("uv 工具目录缺少 specify 可执行文件")
            spec_version = object_output(run([specify, "version", "--json"], cwd=root, env=env), "specify version")
            if spec_version.get("cli_version") != components["spec_kit"]["version"]:
                raise InstallError("specify version 的 cli_version 与计划不一致")
        if "reverse" in selected["components"]:
            if identity is None:
                run([selected["git"], "clone", "--no-checkout", components["reverse"]["repository"], paths["reverse"]], cwd=root)
                run([selected["git"], "-C", paths["reverse"], "checkout", "--detach", components["reverse"]["commit"]], cwd=root)
            reverse = identity or reverse_identity(paths["reverse"])
            if reverse["commit"] != components["reverse"]["commit"]:
                raise InstallError("reverse checkout commit 不符")
        desired_config = None
        managed_rea = None
        if "rea" in selected["components"]:
            rea = [node, paths["rea_package"] / "scripts/rea.mjs"]
            setup = rea + ["setup", "--client", selected["client"], "--skill=false"]
            dryrun = object_output(run(setup + ["--dry-run", "--json"], cwd=root, env=env), "REA setup dry-run")
            atomic(tx / "setup-dryrun.json", encode_json(dryrun))
            applied = object_output(run(setup + ["--yes", "--json"], cwd=root, env=env), "REA setup yes")
            atomic(tx / "setup-result.json", encode_json(applied))
            staged_config = (stage / config.name).read_bytes()
            if selected["client"] == "pi":
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
                managed_rea = parsed["mcp_servers"]["rea"]
            if abs_path(managed_rea.get("command", ".")) != abs_path(node) or str(paths["rea_package"] / "scripts/rea.mjs") not in managed_rea.get("args", []):
                raise InstallError("官方 setup 没有登记本事务的绝对 Node/REA 入口")
            if any(key in managed_rea for key in ("disabled_tools", "enabled_tools", "toolExposure")):
                raise InstallError("REA 注册含工具过滤；本组合要求完整 tools")
        generated_files = []
        if "spec_kit" in selected["components"]:
            specify = paths["uv_bin"] / ("specify.exe" if os.name == "nt" else "specify")
            generated = tx / "project"
            if project.exists() and any(project.iterdir()):
                raise InstallError("首次 init 的成果目录必须不存在或为空；不会覆盖既有项目")
            run(specify_init_args(specify, generated, selected["client"]), cwd=root, env=env)
            if not (generated / ".specify").is_dir():
                raise InstallError("specify init 未生成 .specify")
            generated_files = [p for p in generated.rglob("*") if p.is_file()]
        validate_plan(plan)
        adapter = root / "adapters" / version_key / selected["client"] if selected["client"] != "none" else None
        if "reverse" in selected["components"] and selected["client"] == "pi":
            for source in (REPO / "adapters/pi").rglob("*"):
                if source.is_file(): journal.write(adapter / source.relative_to(REPO / "adapters/pi"), source.read_bytes())
            journal.write(adapter / "receipt-location.json", encode_json({"receipt": str(receipt_path)}))
            settings_path = agent / "settings.json"
            settings = load_json(settings_path, {})
            packages = settings.setdefault("packages", [])
            packages[:] = [p for p in packages if p != str(previous.get("adapter", {}).get("root"))]
            if str(adapter) not in packages: packages.append(str(adapter))
            journal.write(settings_path, encode_json(settings))
        elif "reverse" in selected["components"] and selected["client"] == "codex":
            skill = (REPO / "adapters/codex/SKILL.md").read_text(encoding="utf-8").replace("{{RECEIPT}}", str(receipt_path))
            journal.write(project / ".agents/skills/reverse-workflow/SKILL.md", skill.encode())
        if desired_config is not None:
            journal.write(config, desired_config, "json" if selected["client"] == "pi" else "toml")
        for source in generated_files:
            journal.write(project / source.relative_to(generated), source.read_bytes())
        hashes = {}
        if "rea" in selected["components"]: hashes["rea_sha256"] = tree_hash(paths["rea_package"])
        if "spec_kit" in selected["components"]: hashes["spec_kit_sha256"] = tree_hash(paths["uv_tools"])
        if "reverse" in selected["components"]: hashes["reverse_sha256"] = tree_hash(paths["reverse"], exclude_git=True)
        receipt_paths = {k: str(paths[k]) for k in ("rea_prefix", "rea_package", "uv_tools", "uv_bin", "reverse") if k in paths and ((k.startswith("rea") and "rea" in selected["components"]) or (k.startswith("uv") and "spec_kit" in selected["components"]) or (k == "reverse" and "reverse" in selected["components"]))}
        runtime = {"node": node, "node_version": node_version if node else None, "specify": str(specify) if "spec_kit" in selected["components"] else None}
        receipt = {"schema_version": 1, "installed": True, "meaning": "selected official components installed; host acceptance is separate", "adapter_version": ADAPTER_VERSION, "transaction": transaction, "scope": {k: selected[k] for k in ("components", "root", "client", "agent_dir", "client_config", "project")}, "components": components, "paths": receipt_paths, "runtime": runtime, "reverse": reverse if "reverse" in selected["components"] else None, "adapter": {"root": str(adapter) if adapter else None}, "hashes": hashes, "checks": {"selected_components": "passed", "scoped_config": "passed"}, "validation": limits(), "config_diff": [{"path": e["path"], "before_sha256": e["before_sha256"], "after_sha256": e["after_sha256"]} for e in journal.data["files"]], "backup": str(journal.path), "managed_rea_config": managed_rea}
        journal.write(receipt_path, encode_json(receipt))
        journal.finish("committed")
        return receipt
    except Exception as exc:
        journal.data["failure"] = {"type": type(exc).__name__, "message": str(exc)}
        journal.data["rollback"] = restore_journal(journal.path, apply=True)
        journal.finish("failed")
        raise


def _install(plan, args):
    if set(plan["scope"]["components"]) != {"rea", "spec_kit", "reverse"}:
        return _install_selected(plan, args)
    selected, components = plan["scope"], plan["components"]
    root, agent, project = map(Path, (selected["root"], selected["agent_dir"], selected["project"]))
    receipt_path = root / ".installer/receipt.json"
    previous = load_json(receipt_path, {})
    if previous.get("installed") and previous["scope"] != {k: selected[k] for k in ("root", "client", "agent_dir", "client_config", "project")}:
        raise InstallError("安装根已属于另一配置/项目范围；请选新 root，或 restore 后安装")
    if previous.get("installed") and previous.get("managed_rea_config") is not None:
        current_bytes = Path(selected["client_config"]).read_bytes()
        current_config = json.loads(current_bytes) if selected["client"] == "pi" else toml_parts(current_bytes)[0]
        current_entry = current_config.get("mcpServers" if selected["client"] == "pi" else "mcp_servers", {}).get("rea")
        if current_entry != previous["managed_rea_config"]:
            raise InstallError("活动 REA 配置含后续用户修改；拒绝覆盖，请先审阅差异并保留/迁移自定义项")
    identity = components["reverse"].get("local_identity")
    if identity and reverse_identity(identity["root"]) != identity:
        raise InstallError("reverse 工作副本自 plan 后发生漂移；重新 plan")
    if plan["missing_prerequisites"]:
        raise InstallError("缺少依赖: " + ", ".join(plan["missing_prerequisites"]) + "；请自行准备后重新 plan")
    version_key = digest(encode_json({"components": components, "node": selected["node"], "adapter": ADAPTER_VERSION}))[:20]
    version_dir = root / "versions" / version_key
    if version_dir.exists() and not (version_dir / "complete.json").exists():
        completed_candidates = sorted((root / "versions").glob(version_key + "-*/complete.json"))
        version_dir = completed_candidates[-1].parent if completed_candidates else root / "versions" / (version_key + "-" + uuid.uuid4().hex[:8])
    paths = package_paths(version_dir)
    if selected.get("rea_prefix"):
        paths["rea_prefix"] = Path(selected["rea_prefix"])
        paths["rea_package"] = paths["rea_prefix"] / "node_modules/rea-agents"
    if selected.get("spec_kit_tools"):
        paths["uv_tools"] = Path(selected["spec_kit_tools"])
        paths["uv_bin"] = Path(selected["spec_kit_bin"])
    transaction = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ-") + uuid.uuid4().hex[:8]
    tx = root / ".installer/transactions" / transaction
    journal = Journal(tx)
    atomic(tx / "plan.json", encode_json(plan))
    try:
        stage = tx / "agent"
        stage.mkdir()
        config = Path(selected["client_config"])
        before_config = config.read_bytes() if config.exists() else (b"{}\n" if selected["client"] == "pi" else b"")
        atomic(stage / config.name, before_config)
        env = process_env(root, paths, stage, selected["client"], selected["node"])
        node, npm, node_version = node_and_npm(selected["node"], components["rea"]["node_engine"], root, env)
        complete = load_json(version_dir / "complete.json", {})
        if complete:
            if tree_hash(paths["rea_package"]) != complete["rea_sha256"]:
                raise InstallError("既有 REA 原包发生漂移；拒绝复用，保留现场")
        else:
            if version_dir.exists():
                raise InstallError("存在未完成的版本目录；检查失败事务后移走该目录再重试")
            version_dir.mkdir(parents=True)
            if not selected.get("rea_prefix"):
                run([node, npm, "install", "--prefix", paths["rea_prefix"], "--no-audit", "--no-fund", "--registry", "https://registry.npmjs.org", "rea-agents@" + components["rea"]["version"]], cwd=root, env=env)
            package = load_json(paths["rea_package"] / "package.json", {})
            if package.get("name") != "rea-agents" or package.get("version") != components["rea"]["version"]:
                raise InstallError("npm 安装包身份与冻结计划不一致")
            lock = load_json(paths["rea_prefix"] / "package-lock.json", {})
            actual_integrity = lock.get("packages", {}).get("node_modules/rea-agents", {}).get("integrity")
            if actual_integrity != components["rea"]["integrity"]:
                raise InstallError("REA npm lock integrity 与冻结元数据不一致")
            if not selected.get("spec_kit_tools"):
                run([selected["uv"], "--no-config", "tool", "install", "--default-index", "https://pypi.org/simple", "--python", sys.executable, "specify-cli==" + components["spec_kit"]["version"]], cwd=root, env=env)
            if identity is None:
                run([selected["git"], "clone", "--no-checkout", components["reverse"]["repository"], paths["reverse"]], cwd=root, env=env)
                run([selected["git"], "-C", paths["reverse"], "checkout", "--detach", components["reverse"]["commit"]], cwd=root, env=env)
            complete = {"rea_sha256": tree_hash(paths["rea_package"])}
        reverse = identity or reverse_identity(paths["reverse"])
        if reverse["commit"] != components["reverse"]["commit"]:
            raise InstallError("reverse checkout commit 不符")
        specify = paths["uv_bin"] / ("specify.exe" if os.name == "nt" else "specify")
        if not specify.is_file():
            raise InstallError("uv 工具目录缺少 specify 可执行文件")
        spec_version = object_output(run([specify, "version", "--json"], cwd=root, env=env), "specify version")
        if spec_version.get("cli_version") != components["spec_kit"]["version"]:
            raise InstallError("specify version 的 cli_version 与计划不一致")
        rea = [node, paths["rea_package"] / "scripts/rea.mjs"]
        setup = rea + ["setup", "--client", selected["client"], "--skill=false"]
        dryrun = object_output(run(setup + ["--dry-run", "--json"], cwd=root, env=env), "REA setup dry-run")
        atomic(tx / "setup-dryrun.json", encode_json(dryrun))
        applied = object_output(run(setup + ["--yes", "--json"], cwd=root, env=env), "REA setup yes")
        atomic(tx / "setup-result.json", encode_json(applied))
        staged_config = (stage / config.name).read_bytes()
        if selected["client"] == "pi":
            original, modified = json.loads(before_config), json.loads(staged_config)
            rea_entry = copy.deepcopy(modified.get("mcpServers", {}).get("rea"))
            if not rea_entry:
                raise InstallError("官方 setup 未生成 mcpServers.rea")
            for value in (original, modified):
                value.setdefault("mcpServers", {}).pop("rea", None)
                if not value["mcpServers"]:
                    value.pop("mcpServers")
            if original != modified:
                raise InstallError("官方 setup 修改了非 REA 字段；拒绝合并")
            desired = json.loads(before_config)
            desired.setdefault("mcpServers", {})["rea"] = rea_entry
            desired_config = encode_json(desired)
        else:
            desired_config = codex_merge(before_config, staged_config)
            parsed, _, _ = toml_parts(desired_config)
            if not parsed.get("mcp_servers", {}).get("rea"):
                raise InstallError("官方 setup 未生成 mcp_servers.rea")
        # Always check direct launcher identity. Do not restrict tools or exposure.
        parsed_entry = (json.loads(desired_config)["mcpServers"]["rea"] if selected["client"] == "pi" else parsed["mcp_servers"]["rea"])
        if abs_path(parsed_entry.get("command", ".")) != abs_path(node) or str(paths["rea_package"] / "scripts/rea.mjs") not in parsed_entry.get("args", []):
            raise InstallError("官方 setup 没有登记本事务的绝对 Node/REA 入口")
        if any(key in parsed_entry for key in ("disabled_tools", "enabled_tools", "toolExposure")):
            raise InstallError("REA 注册含工具过滤；本组合要求完整 tools")
        generated = tx / "project"
        generated_files = []
        if not previous.get("installed"):
            if project.exists() and any(project.iterdir()):
                raise InstallError("首次 init 的成果目录必须不存在或为空；不会覆盖既有项目。请选择独立新项目")
            run(specify_init_args(specify, generated, selected["client"]), cwd=root, env=env)
            if not (generated / ".specify").is_dir():
                raise InstallError("specify init 未生成 .specify")
            native = generated / (".pi/prompts" if selected["client"] == "pi" else ".agents/skills")
            if not native.is_dir() or not any(native.rglob("*.md")):
                raise InstallError(f"Spec Kit 未生成已支持的 {selected['client']} 原生资源；保留暂存结果，拒绝切换")
            generated_files = [p for p in generated.rglob("*") if p.is_file()]
            for item in generated.rglob("*"):
                if item.is_symlink():
                    raise InstallError("Spec Kit 生成结果含符号链接；当前迁移器不支持，保留暂存目录")
            staged_path_strings = (str(generated).encode(), generated.as_posix().encode())
            if any(any(marker in p.read_bytes() for marker in staged_path_strings) for p in generated_files):
                raise InstallError("Spec Kit 生成文件绑定暂存绝对路径；当前迁移器无法保证可移植，拒绝切换")
        # Recheck all inputs before the first scoped configuration mutation.
        validate_plan(plan)
        adapter = root / "adapters" / version_key / selected["client"]
        if selected["client"] == "pi":
            for source in (REPO / "adapters/pi").rglob("*"):
                if source.is_file():
                    target = adapter / source.relative_to(REPO / "adapters/pi")
                    if target.exists() and target.read_bytes() != source.read_bytes():
                        raise InstallError(f"已有适配器含后续修改，拒绝覆盖: {target}")
                    journal.write(target, source.read_bytes())
            journal.write(adapter / "receipt-location.json", encode_json({"receipt": str(receipt_path)}))
            settings_path = agent / "settings.json"
            settings = load_json(settings_path, {})
            packages = settings.setdefault("packages", [])
            if not isinstance(packages, list):
                raise InstallError("Pi settings.packages 必须是数组")
            old_adapter = previous.get("adapter", {}).get("root")
            packages[:] = [p for p in packages if p != old_adapter and not (isinstance(p, dict) and p.get("source") == old_adapter)]
            if str(adapter) not in packages:
                packages.append(str(adapter))
            skills = settings.setdefault("skills", [])
            if not isinstance(skills, list):
                raise InstallError("Pi settings.skills 必须是数组")
            for resource in plan["resource_selection"]["exclude_rea_skill"]:
                exclusion = "-" + str(abs_path(resource))
                if exclusion not in skills:
                    skills.append(exclusion)
            if plan["resource_selection"]["rea_manual"]:
                manual = str(adapter / "manual/rea-manual/SKILL.md")
                if manual not in skills:
                    skills.append(manual)
            journal.write(settings_path, encode_json(settings), "json")
        else:
            # Codex uses a project skill to supply the local path to upstream's plugin skill.
            skill = (REPO / "adapters/codex/SKILL.md").read_text(encoding="utf-8")
            skill = skill.replace("{{RECEIPT}}", str(receipt_path))
            target = project / ".agents/skills/reverse-workflow/SKILL.md"
            if target.exists() and target.read_bytes() != skill.encode():
                raise InstallError("Codex 项目入口已被用户修改，拒绝覆盖")
            journal.write(target, skill.encode())
        # The settings merge above is ours; independently recheck the MCP input.
        observed = digest(config.read_bytes()) if config.exists() else None
        if observed != plan["config_inputs"][str(config)]:
            raise InstallError("MCP 配置在激活前发生漂移；事务回退")
        journal.write(config, desired_config, "json" if selected["client"] == "pi" else "toml")
        for source in generated_files:
            target = project / source.relative_to(generated)
            if target.exists() and target.read_bytes() != source.read_bytes():
                raise InstallError(f"项目生成文件冲突: {target}")
            journal.write(target, source.read_bytes())
        final_rea_hash = tree_hash(paths["rea_package"])
        if final_rea_hash != complete["rea_sha256"]:
            raise InstallError("官方命令运行期间 REA 原包发生改变；拒绝记录为原包成功")
        complete["specify_sha256"] = digest(specify.read_bytes())
        spec_tree_hash = tree_hash(paths["uv_tools"])
        if complete.get("spec_kit_sha256") and complete["spec_kit_sha256"] != spec_tree_hash:
            raise InstallError("Spec Kit 隔离工具环境发生漂移；拒绝复用")
        complete["spec_kit_sha256"] = spec_tree_hash
        atomic(version_dir / "complete.json", encode_json(complete))
        receipt = {"schema_version": 1, "installed": True, "meaning": "official packages and scoped configuration installed; host acceptance is separate", "adapter_version": ADAPTER_VERSION, "client_version": "unverified; host CLI not executed", "transaction": transaction, "history": previous.get("history", []) + [transaction], "previous_transaction": previous.get("transaction"), "scope": {k: selected[k] for k in ("root", "client", "agent_dir", "client_config", "project")}, "managed_rea_config": parsed_entry, "components": components, "paths": {k: str(v) for k, v in paths.items()}, "runtime": {"node": node, "node_version": node_version, "node_sha256": digest(Path(node).read_bytes()), "specify": str(specify)}, "reverse": reverse, "adapter": {"root": str(adapter), "codex_plugin_reference": reverse["codex_plugin"]}, "hashes": complete, "checks": {"package_identity": "passed", "official_setup_staged": "passed", "scoped_config": "passed", "specify_version": "passed", "project_init": "preserved-existing" if previous.get("installed") else "passed"}, "validation": limits(), "config_diff": [{"path": e["path"], "before_sha256": e["before_sha256"], "after_sha256": e["after_sha256"]} for e in journal.data["files"]], "backup": str(journal.path)}
        # Receipt itself participates in rollback, so a failed commit cannot lie.
        journal.write(receipt_path, encode_json(receipt), "file")
        journal.finish("committed")
        return receipt
    except Exception as exc:
        journal.data["failure"] = {"type": type(exc).__name__, "message": str(exc)}
        journal.data["rollback"] = restore_journal(journal.path, apply=True)
        journal.finish("failed")
        raise


def verify_selected(receipt):
    failures = []
    selected = set(receipt["scope"].get("components", []))
    paths = receipt.get("paths", {})
    hashes = receipt.get("hashes", {})
    if "rea" in selected:
        if tree_hash(paths["rea_package"]) != hashes.get("rea_sha256"):
            failures.append("REA original package identity drift")
        if not receipt.get("managed_rea_config"):
            failures.append("REA managed configuration missing")
    if "spec_kit" in selected:
        if tree_hash(paths["uv_tools"]) != hashes.get("spec_kit_sha256"):
            failures.append("Spec Kit environment identity drift")
        if not Path(receipt["runtime"]["specify"]).is_file():
            failures.append("specify executable missing")
    if "reverse" in selected:
        if tree_hash(paths["reverse"], exclude_git=True) != hashes.get("reverse_sha256"):
            failures.append("reverse working copy identity drift")
        reverse = receipt.get("reverse")
        if not reverse or reverse_identity(reverse["root"]) != reverse:
            failures.append("reverse working copy drift")
    return {"ok": not failures, "failures": failures, "transaction": receipt["transaction"], "validation": receipt.get("validation", limits()), "note": "verify 只核选定组件身份和配置；不会启动宿主/MCP或声称真实任务通过"}


def verify(root):
    receipt = load_json(Path(root) / ".installer/receipt.json", {})
    if not receipt.get("installed"):
        raise InstallError("没有活动 installed receipt；先 install --apply，或检查失败事务")
    selected = set(receipt.get("scope", {}).get("components", ["rea", "spec_kit", "reverse"]))
    if selected != {"rea", "spec_kit", "reverse"}:
        return verify_selected(receipt)
    failures = []
    for label, observed, expected in [
        ("REA original package", tree_hash(receipt["paths"]["rea_package"]), receipt["hashes"]["rea_sha256"]),
        ("Spec Kit environment", tree_hash(receipt["paths"]["uv_tools"]), receipt["hashes"]["spec_kit_sha256"]),
        ("Node runtime", digest(Path(receipt["runtime"]["node"]).read_bytes()), receipt["runtime"]["node_sha256"]),
        ("specify executable", digest(Path(receipt["runtime"]["specify"]).read_bytes()), receipt["hashes"]["specify_sha256"]),
    ]:
        if observed != expected:
            failures.append(label + " identity drift")
    if reverse_identity(receipt["reverse"]["root"]) != receipt["reverse"]:
        failures.append("reverse working copy drift")
    config = Path(receipt["scope"]["client_config"])
    client = receipt["scope"]["client"]
    data = load_json(config, {}) if client == "pi" else toml_parts(config.read_bytes())[0]
    entry = data.get("mcpServers" if client == "pi" else "mcp_servers", {}).get("rea", {})
    if entry.get("command") != receipt["runtime"]["node"] or str(Path(receipt["paths"]["rea_package"]) / "scripts/rea.mjs") not in entry.get("args", []):
        failures.append("REA MCP launcher drift")
    if entry != receipt["managed_rea_config"]:
        failures.append("REA managed configuration drift")
    if client == "pi":
        packages = load_json(Path(receipt["scope"]["agent_dir"]) / "settings.json", {}).get("packages", [])
        if receipt["adapter"]["root"] not in packages:
            failures.append("Pi package registration missing or changed")
    else:
        if not (Path(receipt["scope"]["project"]) / ".agents/skills/reverse-workflow/SKILL.md").is_file():
            failures.append("Codex project entry missing")
    return {"ok": not failures, "failures": failures, "transaction": receipt["transaction"], "validation": receipt["validation"], "note": "verify 只核身份和配置；不会启动宿主/MCP或声称真实任务通过"}


def accept(root):
    root = Path(root)
    receipt = load_json(root / ".installer/receipt.json", {})
    if not receipt.get("installed"):
        raise InstallError("没有活动 installed receipt；先 install --apply")
    selected = set(receipt.get("scope", {}).get("components", ["rea", "spec_kit", "reverse"]))
    result = {"ok": True, "root": str(root), "components": sorted(selected), "checks": []}
    def check(name, ok, detail, fatal=True):
        result["checks"].append({"name": name, "ok": bool(ok), "detail": detail})
        if not ok and fatal: result["ok"] = False
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
            with tempfile.TemporaryDirectory(prefix="speckit-acceptance-") as temp:
                project = Path(temp) / "project"
                init_args = [str(specify), "init", str(project), "--integration", receipt["scope"]["client"], "--script", "py", "--non-interactive"]
                if receipt["scope"]["client"] == "codex":
                    init_args.append("--ignore-agent-tools")
                completed = subprocess.run(init_args, cwd=root, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=180)
                check("spec_kit_init", completed.returncode == 0 and (project / ".specify").is_dir(), {"returncode": completed.returncode, "native": str(project / ".specify") if (project / ".specify").is_dir() else None})
        except (InstallError, OSError, subprocess.TimeoutExpired) as exc:
            check("spec_kit", False, str(exc))
    result["note"] = "accept 只使用临时验收目录和官方诊断；不会修改活动宿主配置、REA/Spec Kit 包或用户成果项目"
    return result


def restore(root, transaction=None, apply=False):
    root = Path(root)
    receipt = load_json(root / ".installer/receipt.json", {})
    transaction = transaction or receipt.get("transaction")
    if not transaction or not re.fullmatch(r"[A-Za-z0-9-]+", transaction):
        raise InstallError("需要有效的 --transaction，或活动 receipt")
    path = root / ".installer/transactions" / transaction / "journal.json"
    if not path.is_file():
        raise InstallError("找不到事务备份: " + transaction)
    if receipt.get("transaction") and transaction != receipt["transaction"]:
        raise InstallError("只允许恢复活动事务；请按最新到最旧依次回退，避免跨版本覆盖")
    if apply:
        with locked(root):
            return {"transaction": transaction, "applied": True, "files": restore_journal(path, apply=True)}
    return {"transaction": transaction, "applied": False, "files": restore_journal(path)}
