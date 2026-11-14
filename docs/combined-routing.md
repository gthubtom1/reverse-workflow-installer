# 组合安装的路由归属

组合环境只有一个任务入口：`reverse-workflow` → 增强 reverse 的原生 router → PRIMARY。REA、Craft 的工具可被该 PRIMARY 选择；安装了 MCP 不会把工具变成第二个任务负责人。本规则适用于每次新安装、重装、更新及新增宿主。

## 谁负责什么

| 内容 | 唯一负责人 | 组件如何参与 |
|---|---|---|
| 选择专业路线、目标授权、case/scope | reverse 原 router / PRIMARY | 工具不能自行换目标、重开 scope 或扩大范围 |
| 分析事实与未知项 | 原 case 的 Evidence 与 lead 接受决定 | REA / Craft 工具结果保留原件、ID、来源和限制，由原链接收；不把另一工具的 finding 当作自动结案 |
| 规格、计划、任务及任务完成 | 成果项目的官方 Spec runner | 不能让 Craft 自建计划覆盖原 spec/plan/tasks |
| 所选实现批次 | 原 runner 选中的一个写者 | 默认 Worker；合格 Craft 后端仅替换这批实现，不同时另派写者或重新 Study |
| 候选验收、失败回流和 case 完成 | 原 runner / lead / 独立验证者 | Craft Ready、MCP健康、进程退出0均不是 accepted |

REA 官方 setup 使用 `--skill=false`。Craft 在组合环境准备上游 MCP 时使用其所选版本实际支持的 `setup --client codex --no-skill`；先 dry-run、再按已授权范围 apply。**不要把上游 `craft-anything` 广域调查 Skill 默认安装／启用为另一个自动入口。** `--all-tools` 只控制工具目录；`--allow-run` 只控制代码执行同意；两者都不确立路由或执行后端资格。

Craft 0.6.1 的默认setup即使带 `--no-skill`，仍会把已有 `["mcp", "--all-tools"]` 改回 `["mcp"]`。已有全工具注册不要因doctor提示shape不同而重复apply；按官方Skill说明保留该args，只检查其准确CLI身份与其他受管字段。新建注册后若所选Codex版本需要初始全目录，再显式加入该版本支持的 `--all-tools`，核其他MCP／工具审批语义未变。`--no-skill`不是保留工具目录的证明，必须在真实宿主重新检查目录。

## Codex 的机器检查与迁移

本安装器为 Codex 检查已知的上游广域 Skill，包括 `craft-anything`、`rea`、`rea-agents`。扫描范围包括真实用户共享 skills 根、实际选定 Codex 根、显式 Skills 根及选定项目；即使自定义 CODEX_HOME 的末级目录也叫 `.codex`，仍检查真实用户的 `.agents/skills`，不能从目录名猜另一个用户根并漏扫。不枚举历史插件缓存，不声称覆盖任意扩展或被重新命名的第三方入口。出现已启用的冲突时，plan 拒绝并指出准确路径；不能靠 AGENTS 一句“Reverse 优先”放行。

已有官方 Skill 时，保留原正文和附件，用 Codex 原生 `[[skills.config]]`、准确 `path`、`enabled = false` 解除其宿主入口。显式选择受控迁移，例如：

```text
python -B scripts/install.py plan --root <独立安装根> --client codex --agent-dir <实际CODEX_HOME> --exclude-workflow-skill <实际共享skills根>/craft-anything/SKILL.md --output .local/plan.json
python -B scripts/install.py update --root <同一安装根> --plan-file .local/plan.json --apply
python -B scripts/install.py verify --root <同一安装根>
```

参数只控制已识别的上游入口，不用于随意禁用用户技能。禁用的是整个宿主 Skill，不能宣称仍可通过 `$craft-anything` 显式调用它；MCP工具与独立 Craft app不卸载。组合任务从 `reverse-workflow` 进入，PRIMARY依据 live schema选择所需工具。官方Skill原件仍可作为按需参考，但其独立调查／记录职责不替代原case。

安装器将入口控制及所选文件身份记录在 plan/receipt，应用前重核，verify重新检查冲突。源文件漂移、plan后新增冲突、禁用条目重新启用必须拒绝或报失败；重新plan后才能重新接受。恢复只撤销本次拥有的设置，保留其他MCP、其他Skill和用户后改；受管设置被用户改动时报告conflict，不覆盖凑成功。旧receipt不自动证明路由合格，必须按当前检查补齐记录。

Codex仍需新进程／重载后的Skill清单核对：`reverse-workflow` 应启用，上游独立Skill不得仍以启用状态出现。MCP目录完整与入口无冲突分开验收，不做真实模型请求也能检查这些配置和发现条件。配置控制不是OS隔离，也不能证明模型在所有对话中都遵从。

## Pi、Claude与以后新增的宿主

Pi沿用自己的资源排除和显式调用资源机制，不复制Codex TOML。现有 `--exclude-rea-skill` 冻结准确路径；可选 Craft-Pi 的 `reconstruction-execution` 仅在原runner为具体批次选择时使用，不能换成上游广域自动调查Skill。包注册、CLI source和被过滤资源分别核对。

Claude或其他宿主必须先实现其实际技能发现／自动启用／禁用机制，不能因为能连接Craft MCP就宣称完成组合适配。`--exclude-workflow-skill` 的当前原生实现只支持Codex，其他client明确拒绝该参数。安装AI不得绕过这个拒绝，改成手写配置后报“完整适配”。可以保留组件为独立工具，记录尚未支持的组合关系。

为新宿主增加支持前，必须同时交付：

1. 实际宿主配置根、资源发现路径及原生入口控制；未知客户端／格式失败关闭，不借用其他宿主的通过记录。
2. 同一原router/PRIMARY与case/Evidence/Spec归属；任何自动入口或上游setup副作用列入plan。
3. plan、apply、receipt、verify、恢复的一致处理；重复安装、后加冲突、用户配置保留的定向检查。
4. 新宿主真实Skill发现和MCP目录结果；已安装、已加载、基础运行、组合执行后端资格、业务验收分别报告。

## Craft 安装和受控执行资格分开

Codex 官方 Craft MCP/app 可提供分析工具。接续原 R46 的实现批次时，须安装并选择 [Codex 受控执行 bundle](craft-codex.md)，由 `craft-codex-app-server-v1` 复用 accepted research、固定任务/基线、单 Builder、build/check/refine 与 typed return 接收。只存在上游 MCP、没有 receipt 中的受控 backend 时仍记录 `tool companion; execution backend not installed`；不能用独立 `rebuild_start` 偷换原 runner。

用户明确选择从Craft app单独发起其完整Study/Build流程时，它是另一项独立任务及其自身记录；不能与同一成果根的原Spec实现同时运行，也不能把结果自动记入原case为accepted。需要接回组合流程时由原lead核对身份和证据再接收。

安装报告分别列出上游工具、路由控制、所选执行 backend、其离线协议/取消/清理验证与实际业务验收。移除上游自动入口解决入口归属；完整后半执行由独立安装的受控驱动提供。新宿主必须同时实现入口控制和这条执行链，不能复制另一个宿主的通过记录。
