# Reverse Workflow Installer

## 当前交付基线：新电脑必须读取 `main`

把本仓库 GitHub 主链接交给安装 AI 时，安装 AI 必须以仓库默认分支 `main` 的当前内容为准，先读取本 README、`AGENTS.md` 和 [`docs/host-adaptive-installation.md`](docs/host-adaptive-installation.md)，再生成目标电脑自己的 plan。

本次 Codex 全局适配已经包含在 `main`。Codex 的全局入口是目标电脑实际 `CODEX_HOME` 下的：

```text
CODEX_HOME/AGENTS.md
CODEX_HOME/config.toml
CODEX_HOME/skills/reverse-workflow/SKILL.md
```

旧的 `v0.7.0` release/tag 是之前的 installer core 发布身份，不是本次 Codex 全局适配的源码入口。新电脑安装不要 checkout 旧 tag，也不要从旧 release README 推断 Codex 路径；直接读取最新 `main`，并在 plan/receipt 中记录实际读取到的 main commit。installer core 的版本字段仍可保持 `0.7.0`，因为本次是 main 上的宿主适配更新；这不表示应回退到旧 tag。

安装 AI 不得把本机路径、旧 receipt、旧 release、项目级 Skill 或旧备份当作当前安装基线。它必须根据目标电脑实际的 `CODEX_HOME`、Pi agent 根、OS、架构、工具和配置证据动态适配。

**把官方仓库链接交给安装 AI时，入口顺序固定为：**

```text
读取 main
  → README.md
  → AGENTS.md
  → docs/host-adaptive-installation.md
  → docs/environment-recovery.md
  → 识别 Pi / Codex
  → 生成并展示 plan
  → 按官方流程安装所选组件
```


**把仓库链接交给安装 AI：先读 [宿主自适应安装流程](docs/host-adaptive-installation.md) 和 [公共整环境部署指南](docs/environment-recovery.md)。** 根据目标电脑的 OS、架构、已有工具、实际路径和目标宿主部署推荐的工作流、agents、skills 与适用扩展；可选能力按用途和支持范围选择。

安装器与 Pi 入口包源码版本 **0.7.0**，事务协议保持 **0.2.0**。0.7 新增可选 Craft 执行后端分发与受控入口，实际发布/安装分别核对公开 tag 与本机 receipt。Pi 可选的独立 [shell-guard](docs/shell-guard-install.md) 默认关闭；需要时显式使用 `--with-shell-guard`。默认 `all` 的既有选择规则保持不变。shell-guard 0.3.0 已完成适配：常见只读 `for`/`if`/`test`/`echo`/`printf` 形式允许；单个字面项目内 `rm` 移入 TEMP；Everything 行为与硬保护保持不变，不弹确认窗口。目标来源为已发布的 `shell-guard-v0.3.0`，安装器冻结其 commit/tree，不回退 main 或旧版本。

把官方 [REA](https://github.com/morluto/rea)、增强版 [reverse-skill](https://github.com/gthubtom1/reverse-skill)、官方 [GitHub Spec Kit](https://github.com/github/spec-kit) 和可选的官方 [grilling](https://github.com/mattpocock/skills) 访谈技能接入 **Pi 或 Codex** 的独立安装仓库。Python 3.11+，安装器只使用标准库。

REA 提供分析与证据工具；reverse-skill 的原生 router 决定专业 PRIMARY；Spec Kit 在你的独立成果项目里维护规格、计划和任务；`grilling` 在 Pi 中负责方案决策树、隐含前提和结论审查。本仓库负责安装、范围明确的配置、更新与恢复，不修改 REA、Spec Kit 或 `grilling` 官方正文。

可选 [Craft 本地 bundle](docs/craft-install.md) 提供隔离分发/更新/verify/restore 与 Pi 按需 execution 入口，默认关闭；普通 implementation-worker 继续默认，Craft 仅由原 R46/Spec runner 为明确批次 opt-in。需显式选择 Pi、reverse、Spec Kit，提供合格 bundle、独立 Pi Node/CLI/version，并通过 reverse descriptor/version/文件摘要与受管入口门。含 Craft 的冻结 plan 为 schema 2，普通核心 plan 与 receipt 为 schema 1；旧 verify/restore 不认证 Craft，使用新 reader。**源码、发行资产、安装、宿主加载和业务接受须分别取证**；安装/运行资格按实际身份与测试判断，不以 official latest 替代兼容补丁资产。

Craft 的后续入口：

- [上游维护手册](docs/craft-upstream-maintenance.md)与[新对话升级提示词](docs/craft-upgrade-prompt.md)：固定版本差异、最小适配、验证门和三层回滚。
- [精确公开 pin 获取 Craft/reverse](docs/craft-acquisition.md)：正式 [Windows x64 pin](releases/windows-x64.json) 固定 [Craft-Pi v0.1.1](https://github.com/gthubtom1/reverse-workflow-installer/releases/tag/craft-pi-v0.1.1) 与 [reverse v1.9.0](https://github.com/gthubtom1/reverse-skill/releases/tag/v1.9.0)。下载辅助脚本使用独立 [craft-acquisition-v0.1.1](https://github.com/gthubtom1/reverse-workflow-installer/releases/tag/craft-acquisition-v0.1.1) 或包含此修复的 main；安装器核心正式身份保持 [v0.7.0](https://github.com/gthubtom1/reverse-workflow-installer/releases/tag/v0.7.0)。先创建短父目录（如 `D:/cw`），再从辅助源码仓根运行 `python -B scripts/acquire_craft.py --pin-file releases/windows-x64.json --stage D:/cw/craft-0.1 --deadline-seconds 600`，stage 须不存在且绝对根不超过64个 UTF-16 units。辅助工具在网络/进程/写入前检查根路径，解压前再核实际成员预算；HTTP/1.1 是局部兼容选项，不保证网络 clone 必然成功。这里只获取已核包和源，Pi/Node 另用官方锁定流程。
- [原 R46/Spec 到生产 handoff 的指令](adapters/craft-pi/references/execution.md)：按实际 receipt、owner `--inspect` 与 bundled entry protocol 核 validate/prepare/run 能力；production prepare-contract 按包 manifest 定位，不猜开发目录或把接口实现当已接受。
- [runtime 源码与身份入口](adapters/craft-pi/runtime/README.md)和[打包/官方 Pi 获取](docs/craft-packaging.md)：新机器通过 `acquire-pi` 获取完整官方 Pi/Node 树及锁定依赖，不重分发 Pi ZIP、不复制个人配置；许可/发布资格另核。

原目标加壳时，先由原 PRIMARY/REA 在原 scope 内分析并保留原 identity 与派生材料限制，再由 Spec 冻结可实现行为；Craft 不必亲自脱壳。缺事实返回原链，检查只阻依赖任务；单个 A/B 样本无修复收益证据，不保证全软件 1:1 复刻。实际宿主重载/新会话加载仍须独立核验。

## Pi user profiles and skills

本仓库还提供两组简单的、可被 AI 安装代理读取的用户级资源：

- [Pi profile templates](resources/pi-agent-profiles/README.md)：简短工作原则与三个可选 profile：`subagent`、`reverse-operator`、`reverse-reviewer`；按任务选择直接工作或协作，按安装说明复制并清理已退役模板。
- [Portable Pi development skills](resources/pi-agent-skills/README.md)：复制到当前用户的全局 skills 目录，通常是 `%USERPROFILE%\\.agents\\skills\\`。
- [Impeccable 官方 Pi 设计技能](docs/impeccable.md)：固定来源原件、本地复制与换机安装交接；只有一个主技能，不默认开启 CLI、hooks 或浏览器能力。
- [Profile 安装说明](docs/pi-agent-profiles.md) 和 [Skill 安装说明](docs/pi-agent-skills.md) 记录实际路径、冲突处理、reload 和新会话验收。

这些资源不修改 Python 安装器协议，也不包含模型账号、凭据、settings、sessions 或 memory。安装代理应先读取对应说明，按目标电脑实际的 `PI_CODING_AGENT_DIR`、用户目录和 skills 根目录复制文件；已有内容不同的文件先报告冲突，不要静默覆盖。

第一次安装完成后，请先阅读 [安装后快速开始](docs/quick-start.md)，其中的 [独立复刻完整复制模板](docs/quick-start.md#需要独立复刻项目时) 串起原生 Spec、默认 Worker/可选 Craft、失败返回和独立验收；[工作流手册](docs/reverse-workflow-playbook.md) 说明分析分支与续做。最新操作指导看 main 的 docs；实际安装器和资产仍依正式 pin 固定，旧 tag 源码附带的 docs 保留历史，不能据其旧状态覆盖当前指导；执行参数依对应正式本地 help/合同核实。

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

Codex 将第一行的 `--client pi --agent-dir ../workflow/pi-agent` 改为 `--client codex --agent-dir ../workflow/codex-home`。启动宿主时，Pi 使用 `PI_CODING_AGENT_DIR` 指向同一 agent 目录，Codex 使用 `CODEX_HOME` 指向同一目录，并从成果项目工作。Codex reverse 安装的主入口是实际 `CODEX_HOME/AGENTS.md`、`CODEX_HOME/config.toml` 和 `CODEX_HOME/skills/reverse-workflow`。若目标电脑使用自定义 Codex Skills 根，显式增加 `--codex-skills-root <实际路径>`；项目目录不是 Reverse 全局安装的前提。环境变量仅对该进程设置；无需修改系统设置。Pi Web/SDK 必须核对实际启动配置，不能把 CLI 示例当作 Web 已加载的证据。

`plan` 输出完整 JSON：范围、来源、精确版本、Node 要求、命令摘要、现有配置摘要、缺少依赖和未验证项。`--output` 将 UTF-8 无 BOM 计划保存到指定文件。**install/update/restore 不带 `--apply` 都只预览**；plan 可以查询网络和读取 Git，不运行包管理器。冻结计划应用前检测配置和 reverse 工作副本漂移，变化后重新 plan。shell-guard 还冻结独立包身份与内容、远程 commit/Git tree、显式 Everything CLI 的文件摘要，以及开发注册迁移源的旧 hash。`--shell-guard-root` 只读复用精确 0.3.0 包；`--everything-es` 接受现存 CLI 的绝对路径；`--everything-gui` 接受现存 Everything GUI 的绝对路径，`--everything-autostart` 仅在 CLI 报告 IPC/服务不可用时允许插件启动该 GUI 并重试一次；`--replace-shell-guard-root` 只迁移准确的单个开发包注册。重复注册、hub 碰撞或漂移会拒绝。

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

REA/Spec Kit 首次新 plan 解析官方稳定包；已有 installed receipt 的 update 默认沿用 receipt 中的组件版本，避免 adapter/配置维护意外升级依赖。需要升级时显式使用 `--upgrade-components`，并重新核接口与组合兼容性；Spec Kit 也可用 `--spec-kit-version` 固定版本。reverse 使用指定增强仓库的正式 release，尚无 release 时解析 main 的确切 commit。不会静默装预发布版，也不会用旧兼容版本冒充最新。未来官方 CLI 或包布局变化导致检查不匹配时停止并报告缺口。

## 配置和项目里会发生什么

REA 先在事务暂存配置副本内执行官方 `setup --client <实际client> --skill=false --dry-run --json`，再执行相同范围的 `--yes --json`。只把其 REA 配置合并到你指定的配置根，保留其他 MCP、模型和资源。MCP 保留完整 tools，不注册第二个分析 router。`--skill=false` 表示 REA 作为 MCP 工具接入；统一工作流入口由 reverse-workflow 提供，不要把 REA 自己的 skill 缺失状态误解为 MCP 未安装。

Pi 注册本仓库的 skill-only package，只有一个组合入口和短 prompt，manifest 的 extensions/themes 均为空。显式选中 shell-guard 时，另注册其独立插件子目录；shell-guard 使用 AST 分类部分 Bash 命令并通过 `allow`、`trash`、`block` API 表达处理结果，不是操作系统沙箱。Pi 的自动 skill 选择受宿主和模型行为影响，不能把 package 注册等同于每个新对话都会自动进入工作流；专业任务优先显式使用 `/skill:reverse-workflow`，并在新宿主启动后完成 `accept` 与对话冒烟测试。若旧宽泛 REA skill 已自动加载，在 plan 用可重复的 `--exclude-rea-skill <准确SKILL路径>` 作资源排除；不修改原文、不删除原文件。需要单独调用 REA 时可加 `--rea-manual`，它仅在 Pi 声明 `disable-model-invocation: true`。排除与实际加载效果仍需宿主验证。

Codex 使用官方 setup 与 Spec Kit Codex integration，并在 `CODEX_HOME/skills/reverse-workflow/SKILL.md` 写入全局入口。Spec Kit 只有在用户明确提供成果项目时才生成官方项目模板；它不改变全局 Reverse 入口。不假定某个插件注册命令存在；插件缺失时仍交原 RULES、原 router 和 PRIMARY。

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

带 `--plan-file` 可保证展示与应用使用同一版本。已有 installed receipt 的直接 update 默认复用 receipt 中的 REA/Spec Kit 版本；只有显式增加 `--upgrade-components` 才重新解析官方稳定版本，升级前应核对兼容性。直接 `--apply` 则在该次调用开始解析并冻结一次。更新使用并列版本目录、先生成再切换，保留旧组件。旧 receipt 中若仍有 project-continuity，更新会按 receipt 识别唯一注册并移除；缺少唯一身份、出现重复或 hub 注册时停止。已经选中的 shell-guard 在 update 中继续保留，本地包复用路径也会沿用；旧 receipt 不会因此自动启用它。shell-guard 的 Everything 配置只合并明确提供且由 receipt 管理的 `esPath`、`guiPath` 和 `autostart` 字段，保留用户其他配置。首次新项目与现有项目是明确不同状态；不要换一个项目却复用已归属其他范围的 root。

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
