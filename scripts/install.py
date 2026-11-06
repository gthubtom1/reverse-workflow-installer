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
    result.add_argument("--components", default="all", help="组件范围：all（默认）或逗号分隔的 rea,reverse,spec-kit,project-continuity；范围冻结在 plan")
    result.add_argument("--client", choices=("pi", "codex", "claude", "auto", "none"), default="auto")
    result.add_argument("--agent-dir", help="显式 Pi agent 目录或 Codex HOME；不默写用户 profile")
    result.add_argument("--client-config", help="显式 Pi mcp.json 或 Codex config.toml；与 --agent-dir 必须一致")
    result.add_argument("--project", help="独立成果项目；首次 init 必须为空/不存在")
    result.add_argument("--reverse-root", help="只读复用本地 reverse 工作副本，记录实际 commit/脏状态/摘要")
    result.add_argument("--continuity-root", help="只读复用本地 project-continuity 插件包，校验身份并要求匹配清单 name/version/extensions")
    result.add_argument("--without-project-continuity", action="store_true", help="默认 all+pi 组合显式禁用 project-continuity 插件")
    result.add_argument("--node", help="旁置 Node 可执行文件；npm 必须来自同一分发包")
    result.add_argument("--rea-prefix", help="显式只读复用已有 npm prefix，须恰为冻结版本")
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
                for flag in ("agent_dir", "client_config", "project", "reverse_root", "continuity_root", "node", "rea_prefix", "spec_kit_tools", "spec_kit_bin"):
                    supplied = getattr(arguments, flag)
                    if supplied and str(workflow.abs_path(supplied)) != result["scope"].get(flag):
                        raise InstallError(f"--{flag.replace('_', '-')} 与冻结 plan 不一致")
                if arguments.client != "auto" and arguments.client != result["scope"]["client"]:
                    raise InstallError("--client 与冻结 plan 不一致")
                if arguments.components != "all" and workflow.selected_components(arguments.components) != result["scope"]["components"]:
                    raise InstallError("--components 与冻结 plan 不一致")
                if arguments.rea_manual or arguments.exclude_rea_skill or arguments.without_project_continuity:
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
