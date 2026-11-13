# 安装后快速开始

安装后不要先学习工具名称。你只需要把目标文件放到当前对话工作目录的根目录，在新对话里复制 [零基础一键开始](reverse-workflow-playbook.md#零基础一键开始) 的模板，由智能体在已授权范围内连续推进并汇报；它会自动处理 receipt、router、case 和 REA，只有真正需要你决定时才提问。

这套环境由三个核心组件、默认关闭的可选 shell-guard，以及一个 Pi 伴随技能组成。`grilling` 和 `domain-modeling` 保持官方原文，由官方 `npx skills` 安装；本仓库只生成自己的 Pi wrapper，不修改官方文件。

| 组件 | 负责内容 | 什么时候使用 |
|---|---|---|
| REA | MCP 分析工具、工具目录和证据相关能力 | PRIMARY 专业技能需要调用分析工具时 |
| reverse-skill | 原生路由、范围门禁、专业技能和证据流程 | 逆向、二进制、协议、前端签名、复刻、追版等任务开始时 |
| Spec Kit | 成果项目中的规格、计划、任务和模板 | 需要独立实现、复刻、验证或长期维护项目时 |
| shell-guard（可选） | AST 检查部分 Bash 命令；常见只读格式允许，单个字面项目内 `rm` 移到 TEMP；提供 Everything 文件名查询 | 仅 Pi，显式 `--with-shell-guard`；安装与静态校验不证明真实拦截，不是沙箱 |
| grilling | 方案决策树、隐含前提和结论审查 | 明确请求质询，或存在尚未解决的重要目标取舍时 |

`grilling` 不替代 reverse 路由，也不替代 REA 取证。需要读文件、跑命令或比对字节的问题由 agent/subagent 查证；`grilling` 只把查证后的事实带入决策访谈。

### 日常沟通顺序

开场一次说明目标、对象和允许的操作，之后由智能体连续推进并定期汇报。你不需要每个阶段复制提示词或回复编号；只有目标结果、影响/授权范围、交付取舍或用户独有材料存在真实分歧时，才复制相应的 `GOAL-*`、`SCOPE-*`、`DELIVERY-*` 卡。

只有最终结果取舍、补充授权、用户独有材料或无法自行解决的阻碍才需要你回答。查文件、选择工具、核对结论、委派子代理和清理后的可用工具切换由智能体负责。

`grilling` 适合你明确要求质询或目标取舍尚未确定时使用，也可以在开工时澄清目标；它不是每个结论、每次修改前的必经审批。纯报告核查先由 reverse/REA 取证，已经确定的决策不用重问。进入访谈后遵守官方共识规则。

需要保留现有官方 Spec Kit 版本时，生成 plan 可用 `--spec-kit-version`；已有安装更新默认沿用 receipt 版本，需要主动升级才使用 `--upgrade-components`，详见 [固定官方版本](version-pins.md)。上游更新不会让旧安装被冒充成新版通过。

### Pi Craft 可选执行后端

Craft 默认关闭，`all` 不会选择。普通 implementation-worker 仍是默认；只有原 R46/Spec implement runner 为依赖已满足的明确批次选择 Craft 且本机资格满足时才使用。正式 core v0.7.0、native Craft-Pi v0.1.1、reverse v1.9.0 分开发布，下载 helper 独立为 0.1.1：先按 [精确 pin 获取指南](craft-acquisition.md) 获取真实 bundle/reverse，再按 [本地 bundle 指南](craft-install.md) 提供独立 Pi Node/CLI/分发根和精确版本。核心 installer 只消费本地已核 bundle，没有直接 fetch flag。资产和 pin 存在不证明本机 provider、宿主加载或业务接受；新电脑全自动 fresh 网络最后记录为匿名 API 403、无 complete，已核 GET/hash 不等于完整换机实测。它不新增控制 profile，不接管原路由或独立验收。

### Pi shell-guard 可选插件

默认 `all` 不会启用它。安装或更新时增加 `--with-shell-guard`；本地独立 0.3.0 包可加 `--shell-guard-root ../agent-plugins/plugins/pi/shell-guard`。目标 tag `shell-guard-v0.3.0` 已发布，安装器按 commit/tree 冻结。Everything CLI 使用 `--everything-es <现存CLI绝对路径>`，GUI 使用 `--everything-gui <现存Everything.exe绝对路径>`，需要自动启动时增加 `--everything-autostart`。只有 CLI 明确报告 IPC/服务不可用时，插件才会启动该 GUI 并重试一次；不会自动查 PATH、安装 Everything 或启动任意程序。已有禁用开关、自定义规则和其他设置保留。已有开发注册需准确的 `--replace-shell-guard-root`，不能注册整个 hub。详见 [shell-guard 安装与迁移](shell-guard-install.md)。

已选中的插件在后续 update 保留；旧 receipt 仍默认关闭。`verify` 只核身份和注册，`accept` 不运行拦截事件。更新插件后完整重启 Pi/Pi Web，再单独检查加载、命令拦截和 Everything 查询。`PI_SHELL_GUARD_ES` 可在宿主进程覆盖设置中的路径；安装器不更改或认证该进程环境。历史回放结果不能保证未来命令没有误判或绕过。

### Pi grilling 伴随技能

逐个安装官方核心技能；installer wrapper 放到独立的 Pi 用户技能子目录，不写入官方目录。将 `<Pi用户目录>` 换成当前宿主实际使用的 agent 目录（通常为 `~/.pi/agent`）：

```text
npx skills add mattpocock/skills -s grilling --agent pi --global
npx skills add mattpocock/skills -s domain-modeling --agent pi --global
node scripts/pi-adapt-grill-skills.mjs --output-root <Pi用户目录>/skills/pi-grilling
node scripts/verify-pi-grill-skills.mjs --output-root <Pi用户目录>/skills/pi-grilling
```

官方来源默认 `~/.agents/skills`；自定义来源用 `--skills-root`。生成的 `pi-grill-me` 与 `pi-grill-with-docs` 使用独立名称。Pi 递归发现用户 skills 目录下的技能，重载后核对实际加载路径；若输出放到其他位置，按 [wrapper 指南](pi-grilling-wrappers.md) 将生成包登记到对应 profile，避免重复注册。

升级官方技能后，用相同参数重新生成并验证 wrapper。所有权清单检测手改冲突；不能因为有 adapter 标记就覆盖现有文件。旧 `grill-me`/`grill-with-docs` 中的历史适配会单独报告且保持原字节，新 wrapper 直接读取官方核心。

Grilling 是可选伴随技能，不属于 Python 核心组件事务；安装器的 verify/restore 不替代这里的独立验证和维护。清单证明本地摘要一致，不认证上游来源或真实对话行为。

安装后不要凭感觉推进任务。针对 EXE、DLL、APK、JS、协议和已有 case 的分阶段操作、加壳/未加壳分流、REA work item、动态验证和可复制提示词，见 [Reverse 工作流使用手册](reverse-workflow-playbook.md)。

如果你是零基础，直接这样开始即可：

```text
/skill:reverse-workflow

帮我分析这个目标。我是零基础，请用大白话解释。先只读分析，不要修改原文件。
当前对话所在的文件夹就是项目根目录，目标文件在：./[文件名]
请连续推进已授权范围和预算内的检查，并定期用大白话汇报。技术方法和事实你自己判断，不要让我选工具或每步回复继续。
只有目标取舍、需要新的授权、缺少我独有的材料或无法自行解决的阻碍才暂停问我。明确需要访谈时再用 grilling，不为每个结论重复访谈。
```

你不需要自己选择 REA、Ghidra、radare2 或 Static/Dynamic；这些由工作流根据 Evidence 处理。

## 安装完成后的四步

在安装器仓库根目录执行。把 `../workflow` 换成实际安装根：

```text
python scripts/install.py verify --root ../workflow
python scripts/install.py accept --root ../workflow
```

`verify` 只检查包、版本、hash、回执和配置身份；`accept` 才会检查 REA MCP 的启动和工具目录、原生 reverse router，以及 Spec Kit 的临时初始化。两个命令都不会修改用户成果项目。

然后重启 Pi/Codex/Claude Desktop，或者使用宿主提供的 reload 功能。启动时必须使用安装计划中的同一个配置根：Pi 使用对应的 `PI_CODING_AGENT_DIR`，Codex 使用对应的 `CODEX_HOME`，Claude Desktop 使用安装计划中的 `claude_desktop_config.json`，并从成果项目工作。Pi Web/SDK 和 Claude Desktop 需要核对它实际读取的配置，不能把 CLI 示例当作宿主已加载的证据。

最后开一个新对话，使用下面的工作流冒烟测试。只有“宿主加载”和“对话确实进入原生 router”都确认后，才可以把安装视为真正可用。

## 新对话的推荐开场白

Pi 可以先输入 `/skill:reverse-workflow`；如果宿主没有自动显示这个入口，也可以直接复制下面的内容：

```text
/skill:reverse-workflow

这是一个逆向工程任务，请先进入 reverse-workflow 工作流，不要直接开始执行普通命令。

任务：
[写清楚要分析、实现、验证或追踪的目标]

目标对象：
[文件、项目目录、离线样本或已授权目标]

范围：
[只读分析 / 独立实现 / 原版对比 / 版本追踪 / 知识维护]

授权与网络范围：
[本地离线样本，或填写已经授权的目标范围]

请先：
1. 读取本机安装回执；
2. 读取 reverse-skill 的 RULES.md 和 skills/MASTER-ROUTING.md；
3. 使用原生 router 选择 PRIMARY；
4. 报告已知内容、未知内容、范围和下一步；
5. 通过原生工作流执行，不要绕过路由直接使用普通 Bash。
```

只做本地只读检查时，使用：

```text
/skill:reverse-workflow

这是一个只读检查任务。不要修改文件、不要安装、不要下载、不要提交。

请按 receipt 的实际选择范围检查当前环境；未选组件不要求存在：
- 安装回执和已选择的核心组件身份（完整 core 为 REA、reverse、Spec Kit 三项）；
- 若 receipt 选择 Craft，再核其 bundle、独立 Pi 分发和受管 resources 身份，不默认启用 Craft；
- 宿主 skill 是否加载；
- REA MCP 是否完成握手并暴露完整工具；
- reverse 原生 router 是否可运行；
- Spec Kit 成果项目资源是否存在。

最后分别报告：已安装、已加载、已验证、未验证，以及当前对话是否真正进入了 reverse 原生路由。
```

### 全局安装后创建成果项目

当 Codex 计划没有 `--project` 时，receipt 的 `checks.project_init` 为 `not-selected`：全局 reverse 入口、REA 和 `specify` CLI 已准备，但不会在安装仓库或任意默认目录创建 `spec/plan/tasks`。之后真正开始一个独立业务项目时，先选择工具仓库之外的项目目录，读取 receipt 的 `runtime.specify`，再按官方 CLI 在该项目中初始化 Codex 原生资源：

```text
<SPECIFY_FROM_RECEIPT> init <独立成果项目> --integration codex --script py --non-interactive --ignore-agent-tools
```

该步骤只创建项目自己的 `.specify`、constitution、spec/plan/tasks 和 Codex 原生资源；它不重新安装全局 reverse，也不把项目资源写入 `CODEX_HOME/skills/reverse-workflow`。随后从全局 reverse 入口进入原生 router，在当前业务项目的 scope/case 下使用这些项目规格。若项目已有文件，先按官方 CLI 的实际兼容规则和用户授权处理，不让全局安装器静默覆盖。

## 需要独立复刻项目时

填写意图和实际输入即可；技术工具与后端由智能体按原生合同选择。模型实际 provider/model/effort 按会话与运行证据核实，不从 requested 推断，未知保持 unknown；具体资格见安装版执行合同。

```text
/skill:reverse-workflow

请把选定功能做成独立项目，并与原版进行行为对比。
目标与功能：[目标文件/版本、选定行为和预期交付]
成果目录：[工具源码外的独立项目；已有项目填实际目录]
授权与输入：[原 case/证据或首次目标、允许读写/运行/网络范围、预算与已有材料]

先读取原 case、目标身份、scope、行为 Evidence 和 unknown；原 case/PRIMARY 保持权威。证据足够后再进入 reverse 包的 skills/reconstruction/SKILL.md 和 skills/reconstruction/references/spec-kit-workflow.md，恢复已有 feature、constitution、spec、plan、tasks；缺原版事实不猜成规格。纯分析/报告目标可在报告处结束，不强制进入 Spec 或实现。

在成果项目实际生成的官方 Spec Kit 资源中，完整执行适用的 constitution → specify → clarify → plan → tasks → 显式 analyze → implement → 显式 converge；具体 speckit.* 名称、宿主入口和指令全文以实际安装资源为准，只打印命令不算执行。显式检查 analyze/converge，不假定默认 workflow 自动包含。implement 保留 prerequisites、checklists、hooks、任务依赖、测试、同文件串行、阶段检查与最终完成职责。

实现默认交普通 implementation-worker，按原 tasks、实际 tests/diff 与独立验收接收结果。仅原 R46/Spec runner 为依赖已满足的明确批次选择 Craft 且实际安装/owner 协议/本机资格满足时，读取安装版 reconstruction-execution 及其 execution reference；只替换该批编码后端，一个活 owner、一个编码写者，不同时派普通 Worker、不递归派生或另开研究路线。

缺证回原 PRIMARY，在原 scope 内补证，只阻依赖任务；其余独立任务由原 runner 接收返回并确认旧写者清理后再调度。代码缺陷只在冻结计划与预算内 refine，规格/范围问题分别回原 runner/lead，不改预期凑绿。cleanup unknown 时先停新写者、保留 lease，确认自有写者/preview 全部退出再继续。Craft 批次按其有效 typed check report、return_summary、required checks、实际 diff 和 cleanup 接收，不凭标签猜路由；unsupported 交原 lead，输入/规格原因按有效 typed return_to 回原 Spec runner。

对 Craft 批次，补证被原 owner 接收或 plan/scope/交接合同改变后，使用新的引用、decision、selection 冻结新批次与 fresh run root；不复用旧 approved hash，不覆盖历史或跨 run 续旧 session。

所选批次返回后由原 runner 接收并更新原 tasks，失败/未验证不勾完成，继续其余任务、完整 implement/converge；收敛新增有来源的缺项仍回原 tasks 再实现。最后独立验收规格符合、声明范围原版行为及隔离构建/运行，覆盖边界、错误、状态、副作用和 required checks；candidate、Ready、Converged、exit 0、installer accept 均不等于业务 accepted。

在已有授权内连续推进，技术工具由你选择，不让我手工选工具。分别报告复用/新增、证据与真实命令结果、失败/unknown、清理状态和下一恢复入口；未验证边界如实保留，不把安装成功当成行为等价。
```

## 继续旧项目或追踪上游更新时

```text
/skill:reverse-workflow

继续当前成果项目。请先读取旧 case、timeline、证据、Spec Kit feature/plan/tasks 和上次报告，说明已验证内容、未验证内容、失败内容和当前恢复入口，然后再继续。
```

追踪上游版本时补充：

```text
上游从 [旧版本] 更新到 [新版本]。沿用我们的实现和界面，只适配已确认的变化并重新验证。优先恢复旧 case，不要另起无关项目。旧版通过记录不能替代新版证据。
```

## 什么时候应该使用哪个组件

普通问题、普通代码编辑和与逆向无关的任务，不需要强行调用这套工作流。

涉及二进制、APK、前端签名、协议、API 逆向、漏洞分析、恶意样本、复刻、行为对比或版本追踪时，先进入 `reverse-workflow`，由原生 router 选择 PRIMARY。REA 应该由 PRIMARY 在需要时调用；不要把 REA MCP 当成独立路由器。

需要把分析结果做成独立项目、维护规格和任务、长期进行对比验证时，再使用 Spec Kit。Spec Kit 不会替代 reverse-skill 的专业路由。

## 安装、验证与加载状态

- `installed: true`：安装事务已经写入选定包和配置。
- `verify` 通过：静态身份、hash、回执和配置仍然一致。
- `accept` 通过：本机 REA MCP、原生 router 和 Spec Kit 基础流程完成运行验收。
- 对话冒烟测试通过：当前宿主确实加载了入口，并且模型在专业任务中使用了原生 router。

前两层通过，不代表最后一层一定通过。自然语言自动选择 skill 不是安装器可以完全保证的，因此专业新对话优先使用显式 `/skill:reverse-workflow`。

## 入口没有生效时

先确认启动宿主使用的 agent/config 根与安装计划一致，然后重启或 reload。再检查 [故障排查](troubleshooting.md) 中的宿主加载、REA 验收和旧 REA skill 竞争项。

如果模型仍然直接调用普通工具，把任务开头改成：

```text
先调用 /skill:reverse-workflow。没有完成 RULES.md → skills/MASTER-ROUTING.md → PRIMARY 之前，不要开始任务执行。
```

如果 `accept` 失败，读取安装根下 `.installer/transactions/<transaction>/` 的结果和失败记录；不要把 `installed: true` 当成完整任务通过。
