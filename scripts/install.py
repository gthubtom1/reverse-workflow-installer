#!/usr/bin/env python3
"""Python 3.11+ standard-library CLI; preview unless --apply is explicit."""
import argparse
import json
from pathlib import Path
import sys

if sys.version_info < (3, 11):
    raise SystemExit("需要 Python 3.11 或更新版本")

from configuration import atomic, encode_json, load_json
from versions import InstallError
import workflow


def parser():
    result = argparse.ArgumentParser(description="官方 REA + Spec Kit + reverse-skill 安装与恢复；默认只预览")
    result.add_argument("command", choices=("plan", "install", "verify", "accept", "update", "restore"))
    result.add_argument("--root", required=True, help="组件及本机 receipt 根；必须在安装器源码仓库之外")
    result.add_argument("--components", default="all", help="组件范围：all（默认）或逗号分隔的 rea,reverse,spec-kit,shell-guard,craft；shell-guard 默认关闭，范围冻结在 plan")
    result.add_argument("--client", choices=("pi", "codex", "claude", "auto", "none"), default="auto")
    result.add_argument("--agent-dir", help="显式 Pi agent 目录或 Codex HOME；Pi 不默写用户 profile，Codex reverse 按选定 scope 写入 AGENTS/Skills")
    result.add_argument("--codex-skills-root", help="Codex 用户 Skills 根；默认使用实际 CODEX_HOME/skills，支持显式覆盖")
    result.add_argument("--client-config", help="显式 Pi mcp.json 或 Codex config.toml；与 --agent-dir 必须一致")
    result.add_argument("--project", help="独立成果项目；首次 init 必须为空/不存在")
    result.add_argument("--reverse-root", help="只读复用本地 reverse 工作副本，记录实际 commit/脏状态/摘要")
    result.add_argument("--with-shell-guard", action="store_true", help="Pi 可选独立 shell-guard 插件；默认关闭")
    result.add_argument("--shell-guard-root", help="只读复用独立 shell-guard 包；需显式选择组件")
    result.add_argument("--replace-shell-guard-root", help="仅迁移此准确开发包的已有注册；plan 冻结路径与 tree hash")
    result.add_argument("--everything-es", help="Everything CLI 的现存绝对文件路径；仅写 shellGuard.everything.esPath")
    result.add_argument("--everything-gui", help="Everything GUI 的现存绝对文件路径；仅写 shellGuard.everything.guiPath")
    result.add_argument("--everything-autostart", action="store_true", help="明确允许 Everything IPC 失败时启动已配置 GUI 并重试一次")
    result.add_argument("--with-craft", action="store_true", help="Pi optional Craft execution backend; requires explicit reverse/spec-kit")
    result.add_argument("--craft-bundle", help="Explicit unpacked verified local Craft bundle (not a source checkout)")
    result.add_argument("--craft-pi-node", help="Explicit Node executable for standalone Pi; no PATH fallback")
    result.add_argument("--craft-pi-entry", help="Explicit official Pi CLI JavaScript entry")
    result.add_argument("--craft-pi-distribution", help="Explicit self-contained official Pi distribution with reviewed complete dependency-tree manifest")
    result.add_argument("--craft-pi-version", help="Exact Pi version expected by this verified bundle")
    result.add_argument("--node", help="旁置 Node 可执行文件；npm 必须来自同一分发包")
    result.add_argument("--rea-prefix", help="显式只读复用已有 npm prefix，须恰为冻结版本")
    result.add_argument("--spec-kit-version", help="显式选择 PyPI 已发布且未撤回的稳定版本（例如 1.3.1）；省略时沿用活动 receipt 版本，首次安装才选择最新稳定版")
    result.add_argument("--upgrade-components", action="store_true", help="已有安装更新时重新解析官方稳定版本；默认沿用活动 receipt 的组件身份")
    result.add_argument("--spec-kit-tools", help="显式只读复用 UV_TOOL_DIR；与 --spec-kit-bin 配对")
    result.add_argument("--spec-kit-bin", help="显式只读复用 UV_TOOL_BIN_DIR；含 specify 可执行文件")
    result.add_argument("--output", help="plan JSON 的显式输出文件；避免 shell 重定向产生 BOM")
    result.add_argument("--plan-file", help="install/update 使用之前保存的完整冻结 plan JSON；不重新解析 latest")
    result.add_argument("--transaction", help="restore 指定事务 ID；默认活动 receipt 的事务")
    result.add_argument("--exclude-rea-skill", action="append", default=[], help="Pi 按准确绝对资源路径排除已有宽泛 REA skill；可重复")
    result.add_argument("--rea-manual", action="store_true", help="Pi 注册仅显式调用的 rea-manual")
    result.add_argument("--apply", action="store_true", help="install/update/restore 的显式写入与执行开关")
    return result


def main(argv=None):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8")
    arguments = parser().parse_args(argv)
    try:
        if arguments.output and arguments.command != "plan":
            raise InstallError("--output 只适用于 plan")
        if arguments.spec_kit_version is not None and arguments.command not in ("plan", "install", "update"):
            raise InstallError("--spec-kit-version 只适用于 plan/install/update")
        if arguments.upgrade_components and arguments.command not in ("plan", "install", "update"):
            raise InstallError("--upgrade-components 只适用于 plan/install/update")
        if arguments.upgrade_components and arguments.plan_file:
            raise InstallError("--upgrade-components 不能与已冻结 --plan-file 同时使用")
        if (arguments.with_shell_guard or arguments.shell_guard_root or arguments.replace_shell_guard_root or arguments.everything_es or arguments.everything_gui or arguments.everything_autostart) and arguments.command not in ("plan", "install", "update"):
            raise InstallError("shell-guard 选择参数只适用于 plan/install/update")
        if (arguments.with_craft or arguments.craft_bundle or arguments.craft_pi_node or arguments.craft_pi_entry or arguments.craft_pi_distribution or arguments.craft_pi_version) and arguments.command not in ("plan", "install", "update"):
            raise InstallError("Craft selection options only apply to plan/install/update")
        if arguments.command == "verify":
            result = workflow.verify(workflow.abs_path(arguments.root))
            code = 0 if result["ok"] else 1
        elif arguments.command == "accept":
            result = workflow.accept(workflow.abs_path(arguments.root))
            code = 0 if result["ok"] else 1
        elif arguments.command == "restore":
            result = workflow.restore(workflow.abs_path(arguments.root), arguments.transaction, arguments.apply)
            code = 1 if any(f["conflicts"] for f in result["files"]) else 0
        else:
            if arguments.plan_file:
                result = load_json(arguments.plan_file)
                if result["scope"]["root"] != str(workflow.abs_path(arguments.root)):
                    raise InstallError("--root 与冻结 plan 不一致")
                # Configuration/client scope comes entirely from the frozen file.
                for flag in ("agent_dir", "codex_skills_root", "client_config", "project", "reverse_root", "shell_guard_root", "replace_shell_guard_root", "everything_es", "everything_gui", "node", "rea_prefix", "spec_kit_tools", "spec_kit_bin", "craft_bundle", "craft_pi_node", "craft_pi_entry", "craft_pi_distribution"):
                    supplied = getattr(arguments, flag)
                    if supplied and flag == "everything_es":
                        workflow.sg.executable_identity(supplied)
                    if supplied and flag == "everything_gui":
                        workflow.sg.gui_identity(supplied)
                    if supplied and flag in ("shell_guard_root", "replace_shell_guard_root"):
                        workflow.sg.reject_links(Path(supplied).expanduser().absolute())
                    if supplied and str(workflow.abs_path(supplied)) != result["scope"].get(flag):
                        raise InstallError(f"--{flag.replace('_', '-')} 与冻结 plan 不一致")
                if arguments.client != "auto" and arguments.client != result["scope"]["client"]:
                    raise InstallError("--client 与冻结 plan 不一致")
                supplied_components = workflow.selected_components(arguments.components)
                if arguments.with_shell_guard and "shell_guard" not in supplied_components:
                    supplied_components.append("shell_guard")
                if arguments.with_craft and "craft" not in supplied_components:
                    supplied_components.append("craft")
                if arguments.with_craft and "craft" not in result["scope"]["components"]:
                    raise InstallError("--with-craft differs from frozen plan")
                if arguments.craft_pi_version and arguments.craft_pi_version != result["scope"].get("craft_pi_version"):
                    raise InstallError("--craft-pi-version differs from frozen plan")
                if arguments.components != "all" and supplied_components != result["scope"]["components"]:
                    raise InstallError("--components 与冻结 plan 不一致")
                if arguments.with_shell_guard and "shell_guard" not in result["scope"]["components"]:
                    raise InstallError("--with-shell-guard 与冻结 plan 不一致")
                if arguments.everything_autostart != bool(result["scope"].get("everything_autostart")):
                    raise InstallError("--everything-autostart 与冻结 plan 不一致")
                if arguments.spec_kit_version is not None:
                    if "spec_kit" not in result["scope"]["components"]:
                        raise InstallError("--spec-kit-version 需要选择 spec-kit 组件")
                    if arguments.spec_kit_version != result["components"].get("spec_kit", {}).get("version"):
                        raise InstallError("--spec-kit-version 与冻结 plan 不一致")
                if arguments.rea_manual or arguments.exclude_rea_skill:
                    raise InstallError("资源选择已冻结在 plan 中；请重新 plan 后再使用 --plan-file")
                workflow.validate_plan(result)
            else:
                result = workflow.make_plan(arguments)
            if arguments.command == "plan" and arguments.output:
                atomic(Path(arguments.output).expanduser().resolve(), encode_json(result))
            if arguments.command in ("install", "update") and arguments.apply:
                result = workflow.install(result, arguments)
            code = 0
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return code
    except (InstallError, OSError, ValueError, KeyError, TypeError) as exc:
        print(json.dumps({"ok": False, "error": str(exc), "installed": False}, ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
