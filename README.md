# Reverse Workflow Installer

安装器与 Pi 入口包版本 **0.6.0**。Pi 可选的独立 [shell-guard](docs/shell-guard-install.md) 默认关闭；需要时显式使用 `--with-shell-guard`。默认 `all` 的既有选择规则保持不变。目标来源为已发布的 `shell-guard-v0.2.1`，安装器冻结其 commit/tree，不回退 main 或旧版本。本仓实现与离线验证不代表每台机器的宿主加载或 Everything 索引已经可用。

把官方 [REA](https://github.com/morluto/rea)、增强版 [reverse-skill](https://github.com/gthubtom1/reverse-skill)、官方 [GitHub Spec Kit](https://github.com/github/spec-kit) 和可选的官方 [grilling](https://github.com/mattpocock/skills) 访谈技能接入 **Pi 或 Codex** 的独立安装仓库。Python 3.11+，安装器只使用标准库。

REA 提供分析与证据工具；reverse-skill 的原生 router 决定专业 PRIMARY；Spec Kit 在你的独立成果项目里维护规格、计划和任务；`grilling` 在 Pi 中负责方案决策树、隐含前提和结论审查。本仓库负责安装、范围明确的配置、更新与恢复，不修改 REA、Spec Kit 或 `grilling` 官方正文。

## Pi user profiles and skills

本仓库还提供两组简单的、可被 AI 安装代理读取的用户级资源：

- [Pi profile templates](resources/pi-agent-profiles/README.md)：复制到当前 Pi agent 目录的 `AGENTS.md` 和 `agents/*.md`。
- [Portable Pi development skills](resources/pi-agent-skills/README.md)：复制到当前用户的全局 skills 目录，通常是 `%USERPROFILE%\\.agents\\skills\\`。
- [Profile 安装说明](docs/pi-agent-profiles.md) 和 [Skill 安装说明](docs/pi-agent-skills.md) 记录实际路径、冲突处理、reload 和新会话验收。

这些资源不修改 Python 安装器协议，也不包含模型账号、凭据、settings、sessions 或 memory。安装代理应先读取对应说明，按目标电脑实际的 `PI_CODING_AGENT_DIR`、用户目录和 skills 根目录复制文件；已有内容不同的文件先报告冲突，不要静默覆盖。

第一次安装完成后，请先阅读 [安装后快速开始](docs/quick-start.md)。它说明三个核心组件和 Pi `grilling` 伴随技能的分工、官方技能安装与 Pi 适配、`verify` 与 `accept` 的区别、宿主重载方式，以及可以直接复制到新对话的工作流开场白。

如果你需要知道一个目标从哪里开始、如何判断加壳、什么时候进入 REA、如何从 Triage 推进到 Static/Dynamic/Synthesis，请阅读 [Reverse 工作流使用手册](docs/reverse-workflow-playbook.md)。零基础用户直接从其中的 [零基础一键开始](docs/reverse-workflow-playbook.md#零基础一键开始) 复制模板即可。

安装器默认处理三件核心组件；Pi 的 `all` 安装与更新不会再选择 project-continuity，也不会加载旧回执中的该插件。更新旧回执时，只有在 receipt 能定位唯一、未过滤的 Pi 包注册时才会在事务中移除该注册；无法安全识别时明确失败。旧包目录保留在历史版本目录中。`grilling` 是 Pi 的官方伴随技能，不属于 `--components` 事务范围；官方 `grilling`、`domain-modeling`、`grill-me`、`grill-with-docs` 保持原文，installer 只生成自己的 Pi wrapper。三件核心组件可以分别安装；未选择的核心组件不会被解析、安装、注册或在 verify 中要求存在。

```text
# 只装 reverse-skill；不需要宿主配置
python scripts/install.py plan --components reverse --client none --root ../reverse-only --reverse-root ../reverse-skill --output .local/reverse-plan.json
python scripts/install.py install --components reverse --client none --root ../reverse-only --reverse-root ../reverse-skill --plan-file .local/reverse-plan.json --apply
python scripts/install.py verify --root ../reverse-only

# 只装官方 REA 到 Pi
python scripts/install.py plan --components rea --client pi --agent-dir ../rea-agent --root ../rea-only --node ../runtime/node.exe --output .local/rea-plan.json

# 只初始化官方 Spec Kit 成果项目
python scripts/install.py plan --components spec-kit --client pi --project ../spec-project --root ../spec-only --output .local/spec-plan.json
```

`--components all` 是默认值，支持的宿主包括 Pi、Codex 和 Claude Desktop。Claude Desktop 使用已有的 `claude_desktop_config.json` JSON MCP 配置，并在独立成果项目写入 `CLAUDE.md`；它不依赖 Claude CLI 在 PATH。只有选择了多个组件，安装器才会在同一事务中组合它们；组合验收也按 receipt 中的选择范围执行。REA 和 Spec Kit 的源码、包和行为始终由官方发行提供，安装器只负责范围、配置、版本、回滚和验收。


已经有 AI 助手时，可以把本仓库链接发给它并说：

> 请先阅读 README、AGENTS 和 [安装后快速开始](docs/quick-start.md)，把这套环境安装到当前智能体的独立配置目录，成果项目另建。先展示 plan，按我已有授权执行 --apply，安装后运行 verify 和 accept，最后分别报告静态安装、宿主加载和真实任务验证。

需要提前具备 Python 3.11+、Git、uv、符合本次 REA `engines.node` 的 Node（含同一分发包的 npm），以及已能正常登录使用的 Pi 或 Codex。安装器不会安装智能体、模型账号、Java/Ghidra，也不会改系统 PATH。Node 太旧时可下载官方旁置分发包并用 `--node` 指定 node 可执行文件；不会替换当前宿主的 Node。

下面是可直接调整相对路径的示例，在安装器仓库根运行。`../workflow` 是安装根，`../my-project` 是全新成果项目。配置根显式指定；不会默认写你的个人 profile。所有例子均不包含开发者机器路径。

```text
python scripts/install.py plan --root ../workflow --client pi --agent-dir ../workflow/pi-agent --project ../my-project --output .local/plan.json
python scripts/install.py install --root ../workflow --plan-file .local/plan.json --apply
python scripts/install.py verify --root ../workflow
```

Codex 将第一行的 `--client pi --agent-dir ../workflow/pi-agent` 改为 `--client codex --agent-dir ../workflow/codex-home`。启动宿主时，Pi 使用 `PI_CODING_AGENT_DIR` 指向同一 agent 目录，Codex 使用 `CODEX_HOME` 指向同一目录，并从成果项目工作。环境变量仅对该进程设置；无需修改系统设置。Pi Web/SDK 必须核对实际启动配置，不能把 CLI 示例当作 Web 已加载的证据。

`plan` 输出完整 JSON：范围、来源、精确版本、Node 要求、命令摘要、现有配置摘要、缺少依赖和未验证项。`--output` 将 UTF-8 无 BOM 计划保存到指定文件。**install/update/restore 不带 `--apply` 都只预览**；plan 可以查询网络和读取 Git，不运行包管理器。冻结计划应用前检测配置和 reverse 工作副本漂移，变化后重新 plan。shell-guard 还冻结独立包身份与内容、远程 commit/Git tree、显式 Everything CLI 的文件摘要，以及开发注册迁移源的旧 hash。`--shell-guard-root` 只读复用精确 0.2.1 包；`--everything-es` 接受现存 CLI 的绝对路径；`--everything-gui` 接受现存 Everything GUI 的绝对路径，`--everything-autostart` 仅在 CLI 报告 IPC/服务不可用时允许插件启动该 GUI 并重试一次；`--replace-shell-guard-root` 只迁移准确的单个开发包注册。重复注册、hub 碰撞或漂移会拒绝。

`--client auto` 只使用宿主标记或明确配置 schema 证据。不确定时会明确要求 `--client pi|codex`；机器安装了几个 CLI、模型叫不叫 Codex 都不能决定身份。可用 `--client-config` 替代 `--agent-dir`：Pi 必须指向 `mcp.json`，Codex 必须指向 `config.toml`，Pi 的 `settings.json` 在同目录。

## 复用已有独立安装

有本地增强仓库时增加 `--reverse-root ../reverse-skill`：只读记录实际 commit、脏状态和内容摘要，不 clone、不 checkout、不改 remote。允许正在开发的增强工作副本；回执会明确它与公开发行 commit 的区别。

有已安装的官方工具时，在 plan 增加以下参数；目录必须恰好满足本次冻结的稳定版本，安装器会校验身份：

```text
--node ../runtime/node/node.exe
--rea-prefix ../rea-official
--spec-kit-tools ../spec-kit-tools/environments
--spec-kit-bin ../spec-kit-tools/bin
```

最后两项成对指定，分别对应 `UV_TOOL_DIR` 和 `UV_TOOL_BIN_DIR`。Linux 的 `--node` 指向实际 node 可执行文件。没有这些复用参数时，安装器用官方 npm `--prefix` 和 uv 隔离目录自行安装到 `root/versions/<冻结身份>/`。它不会把目录存在等同于安装就绪；版本不符或原包漂移会停止。

REA/Spec Kit 每次新 plan 解析官方最新稳定包；reverse 使用指定增强仓库的正式 release，尚无 release 时解析 main 的确切 commit。不会静默装预发布版，也不会用旧兼容版本冒充最新。未来官方 CLI 或包布局变化导致检查不匹配时停止并报告缺口。

## 配置和项目里会发生什么

REA 先在事务暂存配置副本内执行官方 `setup --client <实际client> --skill=false --dry-run --json`，再执行相同范围的 `--yes --json`。只把其 REA 配置合并到你指定的配置根，保留其他 MCP、模型和资源。MCP 保留完整 tools，不注册第二个分析 router。`--skill=false` 表示 REA 作为 MCP 工具接入；统一工作流入口由 reverse-workflow 提供，不要把 REA 自己的 skill 缺失状态误解为 MCP 未安装。

Pi 注册本仓库的 skill-only package，只有一个组合入口和短 prompt，manifest 的 extensions/themes 均为空。显式选中 shell-guard 时，另注册其独立插件子目录；shell-guard 是部分命令形式的启发式检查，不是操作系统沙箱。Pi 的自动 skill 选择受宿主和模型行为影响，不能把 package 注册等同于每个新对话都会自动进入工作流；专业任务优先显式使用 `/skill:reverse-workflow`，并在新宿主启动后完成 `accept` 与对话冒烟测试。若旧宽泛 REA skill 已自动加载，在 plan 用可重复的 `--exclude-rea-skill <准确SKILL路径>` 作资源排除；不修改原文、不删除原文件。需要单独调用 REA 时可加 `--rea-manual`，它仅在 Pi 声明 `disable-model-invocation: true`。排除与实际加载效果仍需宿主验证。

Codex 使用官方 setup 与 Spec Kit Codex integration，并在成果项目生成薄 `.agents/skills/reverse-workflow/SKILL.md`，通过本机回执给现有 reverse Codex 插件提供显式本地路径。不假定某个插件注册命令存在；插件缺失时仍交原 RULES、原 router 和 PRIMARY。

Claude Desktop 使用显式的 `claude_desktop_config.json` JSON 配置。安装器只合并 `mcpServers.rea`，保留其他字段；并在成果项目生成 `CLAUDE.md`，把当前回执、reverse 原生 router、bounded REA work item 和零基础动态选项规则交给 Claude。Claude Desktop 不需要 Claude CLI 在 PATH；宿主真实加载仍需重启 Claude 后用新对话验证。
Spec Kit 用官方 `specify init --integration <实际client> --script py --non-interactive` 在暂存项目生成随包原生资源，检查后写入你的新成果项目。首次必须是空目录；不在工具源码仓库里 init。更新工具保留项目的 constitution、规格、代码和已有模板；已有项目模板迁移尚未自动化。

## 更新、检查和恢复

```text
python scripts/install.py update --root ../workflow --client pi --agent-dir ../workflow/pi-agent --project ../my-project --reverse-root ../reverse-skill
python scripts/install.py update --root ../workflow --client pi --agent-dir ../workflow/pi-agent --project ../my-project --reverse-root ../reverse-skill --apply
python scripts/install.py verify --root ../workflow
python scripts/install.py restore --root ../workflow
python scripts/install.py restore --root ../workflow --apply
```

带 `--plan-file` 可保证展示与应用使用同一版本。直接 `--apply` 则在该次调用开始解析并冻结一次。更新使用并列版本目录、先生成再切换，保留旧组件。旧 receipt 中若仍有 project-continuity，更新会按 receipt 识别唯一注册并移除；缺少唯一身份、出现重复或 hub 注册时停止。已经选中的 shell-guard 在 update 中继续保留，本地包复用路径也会沿用；旧 receipt 不会因此自动启用它。shell-guard 的 Everything 配置只合并明确提供且由 receipt 管理的 `esPath`、`guiPath` 和 `autostart` 字段，保留用户其他配置。首次新项目与现有项目是明确不同状态；不要换一个项目却复用已归属其他范围的 root。

本机回执、精确 paths/版本、配置 diff 摘要及完整恢复备份位于 `root/.installer/`。备份可能包含你原配置中的秘密，属于本地私有数据，禁止发布。`installed: true` **只表示包与指定配置事务已完成**。`verify` 核包、运行时、reverse 和注册身份，不启动宿主/MCP；它返回的 `validation` 保留加载、握手/schema、真实任务等未验证项。失败事务不会写成功回执，已有活动安装会回退保留。

restore 默认撤销最近活动事务；按字段/资源进行条件恢复，用户后续改动保留并列为 conflict。项目中已由你编辑的文件不会覆盖。旧包、缓存和备份保留，不自动卸载/删目录。详见 [更新与恢复](docs/updates.md)、[故障排查](docs/troubleshooting.md)。

安装完成后，`verify` 只检查身份、hash、配置和 receipt。要做本机真实验收，运行：

```text
python scripts/install.py accept --root ../workflow
```

`accept` 按 receipt 中的组件范围执行：REA 使用官方 `rea mcp doctor` 检查 stdio 启动、initialize、完整 tools/prompts catalog 和 request flow；reverse 在临时目录运行原生 master-router；Spec Kit 在临时目录执行官方 `specify init` 并检查原生模板。验收不会修改活动宿主配置、官方包或用户成果项目。shell-guard 的加载、拦截和 Everything 可用性保留为 unverified。验收通过后还要重启或 reload 宿主，再用 [安装后快速开始](docs/quick-start.md) 中的显式开场白做一次真实对话测试。


> 分析这个程序，把选定功能做成独立项目，并和原版对比；证据不足的地方保留 unknown。

> 继续上次项目，先说明已经验证的内容、未知项和下一步。

> 这个项目上游从 1.0 更新到 1.1 了，沿用我们的实现和界面，只适配变化并重新验证。

追版复用原 case、证据、Spec Kit feature/tasks 和旧成果；上游新版本的验证不能借用旧版通过记录。实际专业流程由增强 reverse 提供，不由安装器复制。新对话开场白、只读检查和复刻任务模板见 [安装后快速开始](docs/quick-start.md) 与 [使用说明](docs/usage.md)。

## 验证与支持边界

```text
python -B -m unittest discover -s tests -v
node --test tests/pi-grill-skills.test.mjs
```

测试全离线，用模拟 HTTP 和模拟官方 CLI 驱动真实配置/备份/回退文件操作；不下载、不运行安装命令、不访问用户 profile。Windows 本地测试已执行；Ubuntu/其他 Python 的 CI 配置已提供，实际 CI 结果以运行记录为准。

[兼容记录](docs/compatibility.md) 将文档支持、本机测试、宿主加载和完整任务分别列出。首版声明 Pi、Codex 和 Claude Desktop 的适配实现，不声称支持所有智能体，不保证自然语言每次自动加载技能、不保证任意目标等价。Pi 的 `grilling` 是独立用户级伴随技能，不属于核心安装事务；安装器把静态安装、宿主加载、MCP 验收、代表任务和对话触发分开记录；Node 下载、provider 安装、MCP 握手、代表任务及独立隔离交付由后续真实验收补齐。

维护两仓库时请使用 [维护与发布闭环](docs/maintenance.md)：同时核对规则、入口、教程、离线回归、本机回执、远程 main 和 reverse 正式 release。默认安装优先正式 release，单独推送 main 不会让新电脑自动拿到尚未发行的改动。

## 来源与许可

本仓库自有安装与适配代码为 [MIT](LICENSE)。REA、Spec Kit、reverse-skill 的版权和许可保持各自原件；本仓库不分发其修改版或将其成果冒充本方知识。作者与来源见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。
