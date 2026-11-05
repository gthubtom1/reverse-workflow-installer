# 安装后快速开始

这套环境由三个核心组件和一个 Pi 伴随技能组成。前三个由本安装器管理；`grilling` 保持官方原文，由官方 `npx skills` 安装器单独安装，再由本仓库提供的 Pi 适配脚本处理门面技能：

| 组件 | 负责内容 | 什么时候使用 |
|---|---|---|
| REA | MCP 分析工具、工具目录和证据相关能力 | PRIMARY 专业技能需要调用分析工具时 |
| reverse-skill | 原生路由、范围门禁、专业技能和证据流程 | 逆向、二进制、协议、前端签名、复刻、追版等任务开始时 |
| Spec Kit | 成果项目中的规格、计划、任务和模板 | 需要独立实现、复刻、验证或长期维护项目时 |
| grilling | 方案决策树、隐含前提和结论审查 | 形成方案、确认分析结论或准备修改/重实现之前 |

`grilling` 不替代 reverse 路由，也不替代 REA 取证。需要读文件、跑命令或比对字节的问题由 agent/subagent 查证；`grilling` 只把查证后的事实带入决策访谈。

### 日常沟通顺序

你可以把一次逆向任务按下面四段来推进：

1. **开始分诊**：使用 `/skill:reverse-workflow`，写清目标、范围、授权和“先只读”。这一阶段让 reverse 读取 receipt、运行 router、创建 case，并报告 Observed、Inferred、Unknown、Evidence 和下一步。
2. **推进证据**：只给一个具体 Evidence 问题，例如“确认这个字符串的引用函数”或“确认这个函数的返回值和调用者”。需要读文件、跑工具、看字节的问题，要求 agent 自己查，不要把事实题回答给你。
3. **审查方案**：当它准备下结论、设计补丁、开始复刻或准备修改之前，发送：

   ```text
   现在先不要实施。读取并使用 grilling 规则，列出当前 design tree 的完整 frontier。
   事实问题请先由 agent/subagent 查证；只把需要我决定的方案分叉列出来。
   对每个问题给出你的推荐答案，等我确认共识。
   ```

   这时它会使用 `Q1`、`Q2` 和推荐答案的访谈格式。你按编号回答，或者直接说“接受 Q1、拒绝 Q2，并选择……”。
4. **确认后实施**：只有在你确认方案后，发送：

   ```text
   我们已经达成共识。按刚才确认的范围和停止条件继续实施。
   实施后重新验证原始字节、产物身份、行为结果和所有未解决项。
   ```

   如果你还没有确认共识，就不要用“继续实施”这句话。

在 `grilling` 访谈中，reverse 的阶段报告放在访谈前或一轮访谈完成之后；你会看到两种格式各自负责不同事情：reverse 用于阶段状态和下一步菜单，grilling 用于方案问题和推荐答案。

例如，补丁分析不能直接把“改掉 `jne` 后就是已授权”当成结论。应该先查证实际控制流、落点指令、寄存器是否被覆盖，再让 grilling 质询：补丁目标是什么、哪些功能路径覆盖到了、哪些仍是 unknown、是否允许修改副本。

### Pi grilling 伴随技能

在新电脑或新用户配置上，先在安装器仓库根目录逐个安装官方技能。不要把多个名字写进一次 `-s` 参数；上游安装器的逗号语法存在问题：

```text
npx skills add mattpocock/skills -s grilling
npx skills add mattpocock/skills -s grill-me
npx skills add mattpocock/skills -s grill-with-docs
npx skills add mattpocock/skills -s domain-modeling
node scripts/pi-adapt-grill-skills.mjs
```

安装结果应出现在 `~/.agents/skills/`（Windows 为 `%USERPROFILE%\\.agents\\skills\\`）下。最后一次脚本执行应把 `grill-me` 和 `grill-with-docs` 改成 Pi 可组合的门面；它是幂等的，第二次执行不会重复修改。官方 `grilling/SKILL.md` 不会被修改。

如果以后运行 `npx skills update`，上游可能重新写回两个门面；更新后再次执行：

```text
node scripts/pi-adapt-grill-skills.mjs
```

这四个技能属于 Pi 用户级配置，和 `--root` 指定的 REA/reverse/Spec Kit 安装根分开保存。迁移电脑时要同时迁移安装器仓库、reverse 工作副本/远程来源、成果项目，以及按本节重装的用户级技能。安装器的 `verify` 不会把 grilling 算作核心事务的一部分，因此要单独检查四个目录和适配脚本输出。

安装后不要凭感觉推进任务。针对 EXE、DLL、APK、JS、协议和已有 case 的分阶段操作、加壳/未加壳分流、REA work item、动态验证和可复制提示词，见 [Reverse 工作流使用手册](reverse-workflow-playbook.md)。

如果你是零基础，直接这样开始即可：

```text
/skill:reverse-workflow

帮我分析这个目标。我是零基础，请用大白话解释。先只读分析，不要修改原文件。
每个阶段完成后请告诉我：本轮做了什么、确认了什么、还不知道什么，并根据当前情况生成带编号的下一步建议。选项要写白话，括号里保留专业术语。我只通过输入编号推进。
当分析足够判断长期结果时，请给我多个可复制的 GOAL 目标文本。
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
2. 读取 reverse-skill 的 RULES.md 和 MASTER-ROUTING.md；
3. 使用原生 router 选择 PRIMARY；
4. 报告已知内容、未知内容、范围和下一步；
5. 通过原生工作流执行，不要绕过路由直接使用普通 Bash。
```

只做本地只读检查时，使用：

```text
/skill:reverse-workflow

这是一个只读检查任务。不要修改文件、不要安装、不要下载、不要提交。

请检查当前环境中的：
- 安装回执和三组件身份；
- 宿主 skill 是否加载；
- REA MCP 是否完成握手并暴露完整工具；
- reverse 原生 router 是否可运行；
- Spec Kit 成果项目资源是否存在。

最后分别报告：已安装、已加载、已验证、未验证，以及当前对话是否真正进入了 reverse 原生路由。
```

## 需要独立复刻项目时

```text
/skill:reverse-workflow

请把选定功能做成独立项目，并与原版进行行为对比。

先恢复或创建当前成果项目的 Spec Kit 工作流，再读取旧 case、证据、feature、plan 和 tasks。保留 unknown，不把文件存在、退出码为 0 或安装成功当成行为等价。

完成后分别报告：复用内容、新增内容、已验证行为、失败行为、未知项和下一步验证入口。
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

## 三种状态不要混淆

- `installed: true`：安装事务已经写入选定包和配置。
- `verify` 通过：静态身份、hash、回执和配置仍然一致。
- `accept` 通过：本机 REA MCP、原生 router 和 Spec Kit 基础流程完成运行验收。
- 对话冒烟测试通过：当前宿主确实加载了入口，并且模型在专业任务中使用了原生 router。

前两层通过，不代表最后一层一定通过。自然语言自动选择 skill 不是安装器可以完全保证的，因此专业新对话优先使用显式 `/skill:reverse-workflow`。

## 入口没有生效时

先确认启动宿主使用的 agent/config 根与安装计划一致，然后重启或 reload。再检查 [故障排查](troubleshooting.md) 中的宿主加载、REA 验收和旧 REA skill 竞争项。

如果模型仍然直接调用普通工具，把任务开头改成：

```text
先调用 /skill:reverse-workflow。没有完成 RULES → MASTER-ROUTING → PRIMARY 之前，不要开始任务执行。
```

如果 `accept` 失败，读取安装根下 `.installer/transactions/<transaction>/` 的结果和失败记录；不要把 `installed: true` 当成完整任务通过。
