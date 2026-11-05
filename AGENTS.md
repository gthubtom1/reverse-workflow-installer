# 执行安装的智能体

先读 README、[安装后快速开始](docs/quick-start.md)、components.json、docs/compatibility.md。写入范围由用户明确授权决定；已有授权内的确定步骤连续完成，不按每条命令重复索要许可。缺少宿主身份、登录或成果范围时只报告准确缺口。

1. 只读探测 Python、Git、uv、Node/npm 与用户指定目录。不要枚举环境变量值，不以模型名或 CLI 是否安装判断宿主。auto 不确定时使用用户明确指定的 pi/codex。
2. 用 scripts/install.py plan 指定 --root、--agent-dir 或 --client-config、--project。已有增强工作副本用 --reverse-root；已有独立原包用显式复用参数。展示可读范围、精确版本、命令、缺依赖与未验证项。推荐 --output .local/plan.json。
3. 按用户已有授权执行 install/update --plan-file .local/plan.json --apply。不要绕过漂移/冲突拒绝，不自行覆盖用户配置，不在工具 repo init 项目，不改 REA/Spec Kit/reverse 原文。没有授权时仅展示具体计划。
4. verify 核身份与配置。随后按实际宿主启动方式核加载资源、MCP initialize/tools/list 的完整 schema、原 router 与代表任务、Spec Kit 模板实际使用、新会话恢复；逐项记录真实输出。verify 静态通过不替代这些验收。
5. 失败时读取 root/.installer/transactions 的本地日志，报告是哪条官方命令/接口失败。restore 先预览，已有恢复授权时再 --apply；保留用户后续编辑。不要把含配置秘密的备份或 setup 输出贴到公开 issue。

开发测试使用 `python -B -m unittest discover -s tests -v`，所有测试夹具只写本仓 `.local/tests/`。不得为测试执行真实 npm/uv/setup/init，不接触真实 profile。CI 不需要网络下载安装组件。新增官方版本必须核实际 CLI/包布局；不发明参数、插件命令或就绪能力。

本仓只维护分发与宿主适配，领域知识和 PRIMARY 决策继续在 reverse 原仓库。公开内容不用绝对机器路径，不提交本机 receipt、目标样本、凭据或客户数据。未经当前任务授权不要 git add/commit/push。
