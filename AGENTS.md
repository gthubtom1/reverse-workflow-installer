# 执行安装的智能体

**新电脑安装必须以仓库默认分支 `main` 为准。** 先读取仓库 README、[当前宿主自适应安装流程](docs/host-adaptive-installation.md)、[安装后快速开始](docs/quick-start.md)、components.json 和 docs/compatibility.md。不要 checkout 旧 `v0.7.0` tag 来安装 Codex；本次 Codex 全局适配位于 main，Codex 主入口是实际 `CODEX_HOME/AGENTS.md`、`CODEX_HOME/config.toml` 和 `CODEX_HOME/skills/reverse-workflow`。记录 plan 中实际读取到的 main commit。

先读 README、[安装后快速开始](docs/quick-start.md)、components.json、docs/compatibility.md 和 [组合路由归属](docs/combined-routing.md)。写入范围由用户明确授权决定；已有授权内的确定步骤连续完成，不按每条命令重复索要许可。缺少宿主身份、登录或成果范围时只报告准确缺口。

1. 只读探测 Python、Git、uv、Node/npm 与用户指定目录。不要枚举环境变量值，不以模型名或 CLI 是否安装判断宿主。auto 不确定时使用用户明确指定的 pi/codex。
2. 用 scripts/install.py plan 指定 --root、--agent-dir 或 --client-config；选择 Spec Kit 项目模板时再加 --project。已有增强工作副本用 --reverse-root；已有独立原包用显式复用参数。展示可读范围、精确版本、命令、缺依赖与未验证项。推荐 --output .local/plan.json。组合安装只有 reverse-workflow 自动入口；Codex 已有上游广域 Craft/REA Skill 时先处理 plan 报出的入口冲突，明确选择 `--exclude-workflow-skill <准确SKILL.md>` 才可用原生控制迁移，不修改官方正文。
3. 按用户已有授权执行 install/update --plan-file .local/plan.json --apply。不要绕过漂移/冲突拒绝，不自行覆盖用户配置，不在工具 repo init 项目，不改 REA/Spec Kit/reverse 原文。没有授权时仅展示具体计划。
4. verify 核身份、配置和已知入口冲突；新增上游setup后必须再次verify。随后按实际宿主启动方式核加载资源（reverse-workflow启用，上游广域调查Skill未启用）、MCP initialize/tools/list 的完整 schema、原 router 与代表任务、Spec Kit 模板实际使用、新会话恢复；逐项记录真实输出。verify 静态通过不替代这些验收。上游Craft使用所选版本支持的 `setup --client codex --no-skill`，不能默认再启用其独立调查Skill。MCP安装、路由控制、R46执行后端资格分别报告；缺宿主原生控制或未资格化时明确unsupported/unqualified，不能以工具目录齐全声称完整组合适配。
5. 失败时读取 root/.installer/transactions 的本地日志，报告是哪条官方命令/接口失败。restore 先预览，已有恢复授权时再 --apply；保留用户后续编辑。不要把含配置秘密的备份或 setup 输出贴到公开 issue。

开发测试使用 `python -B -m unittest discover -s tests -v`，所有测试夹具只写本仓 `.local/tests/`。不得为测试执行真实 npm/uv/setup/init，不接触真实 profile。CI 不需要网络下载安装组件。新增官方版本必须核实际 CLI/包布局；不发明参数、插件命令或就绪能力。

本仓只维护分发与宿主适配，领域知识和 PRIMARY 决策继续在 reverse 原仓库。变更前后按 [维护与发布闭环](docs/maintenance.md) 核对规则、入口、教程、回归、活动部署与正式 release；不能只推 main 就声称换电脑会拿到新版本。公开内容不用绝对机器路径，不提交本机 receipt、目标样本、凭据或客户数据。未经当前任务授权不要 git add/commit/push。
