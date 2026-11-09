# 生产执行交接与返回边界

本资源服务原 R46/Spec implement runner 明确选定的一批任务。普通 Worker 默认沿用；Craft 是单 owner、单 Builder 的可选编码后端，不新增控制 profile、第二任务账本或独立研究路线。官方 implement 必须全文执行，保留前置、checklists/hooks、依赖、同文件串行、测试、阶段与最终检查；批次之后继续原 tasks，再执行官方完整 converge 和独立验收。

## 按实际安装发现能力

从本 package 的 `receipt-location.json` 定位 receipt，核 `craft.resources` 和 `craft.root`；用 `craft-bundle.json` 的 `runtime.entry_protocol` 定位正式协议、`runtime.entry`/driver 定位真实可执行文件，并核完整 inventory/hash。按 bundle manifest 定位 production `prepare-contract.md`、schema 和所需示例源码；当前打包配方把 executor 源库存放在 `source/executor/`，只有 manifest 实际列入 `source/executor/docs/prepare-contract.md` 才可读该路径，不能假定所有旧 bundle 都有。缺文件/协议不兼容返回具体缺口，不从工作区补读未冻结源码冒充已安装能力。

受管入口只用 `entry.py --check` 或 `entry.py --execute -- <正式 owner 参数>`。先经受管入口执行 `--inspect`，核 commands 与 bundled protocol/receipt 能力匹配；本次生产源码已实现 validate/prepare/run，最终测试与独立接受仍须按所装版本取证。未收录/未满足本批资格则 unsupported，回原 runner 选择现有 Worker；文档或源文件存在不宣称全链已通过。executor 当前没有通用 `--help` 命令，参数以正式协议和 `--inspect` 为准，不能把它当 argparse 工具猜 flags。

entry 会复核 bundle/资源/reverse 合同/唯一注册和独立 Pi 分发，并执行所选 Node + Pi CLI 的 `--version`。它输出的 command 是真实 owner，`runtime_qualification:unverified` 不能解释为 provider 资格。入口提供 `CRAFT_BUNDLE_ROOT`、`CRAFT_PI_NODE`、`CRAFT_PI_ENTRY`、`CRAFT_PI_VERSION`、`CRAFT_PI_DISTRIBUTION`、`CRAFT_BUILDER_INSTRUCTIONS`；移除 Node 注入变量，无 PATH pi fallback。完整内容身份不等于来源认证、动态 import sandbox 或实际模型可用性。

## 原 owner 准备真实 handoff

按实际 prepare-contract/schema 组装 deny-unknown v1 输入，不自创字段，不把下列文字当可直接提交的 JSON：

- `authority` 绑定原 case、scope、workitem、feature、spec、plan、tasks、acceptance 的真实 HashedRefs；`lead_decision` 和 `selection` 也须是有实际内容/hash 的文件。decision 绑定同一 authority、selection、所选 IDs、原 lead 决策引用与批准的 target/source/workspace、stack、check plan、model、commands/build、budget。hash/结构匹配不证明 lead 决定真实或证据充分，仍需原责任人接收。
- selection 引用同一 spec/tasks；任务使用标准 `- [ ] T001 ...` / `- [X] T002 ...` 格式，选中项须实际未完成，依赖须在原 tasks 中完成且与声明一致。补充记录不更新原 tasks，不造 case ID、假已完成依赖或未替换占位符。
- original 保留原 target/identity、研究 bundle/行为引用；external baseline/index、artifact/scenario/check plan 绑定真实 hash、来源资格、环境、映射损失与限制。至少有 required build 和 required external business scenario，命令、产物与种子来自原 verifier 的真实接口。prepare 仅装配，不自动研究、不发明状态接口或万能 UI oracle；缺材料只阻依赖任务，由 runner 安排其余任务。
- application 选 `existing-workspace`、`empty` 或 `copy`。existing 指向与目标/stack 匹配的正式 Workspace/app 及批准源码摘要；empty 要明确批准空源码，copy 从批准源根/摘要复制到全新正式 Workspace/app，拒绝 links/reparse 与根重叠。新 Workspace 必须不存在、父目录存在；owner_output 也须全新，位于 Workspace 外，原输入/运行控制和 provider 资源不能落入 Builder 写根。
- v1 新 Workspace 的 `read_references` 必须为空。若 Builder 需要按文件读取规格/基线，原 owner 先按现有正式接口准备 Workspace、将 exact 只读引用暂存到该 Workspace/reference，再以 existing-workspace 交接；app 源码根不变，spec/plan/tasks 和控制文件保持受保护，不移入写根。若材料已在审过的 prompt 内，也须足以完成任务；需要工具读的路径必须在实际 gate 下可读。不能清空必需引用或扩大权限凑通过。
- 模型选择和 instructions、driver、最小 provider manifest 均显式引用/hash。provider 定义只含选中 provider/model，凭据仅 `${ENV_NAME}` reference，`credential_env_keys` 只有名称，本机官方 resolver 提供值；不复制个人 auth/settings/MCP/session。validate/prepare 要求 provider manifest 和资源合格，但不读凭据值或启动模型；真正 run 另核显式 Pi 环境/凭据和实际选择，失败不换模型 fallback。

预算由 lead 明确选择。本 v1 wire `budget.aggregate:"strict"` 返回 `unsupported-budget`，不支持总 token/费用硬上限；不得暗改成 audit 模式。本批若获 lead 明确选择 `aggregate:"audit-only"`，则冻结 hard wall、max_refinements 和配置的 per-response maxTokens，记录实际主/嵌套 usage；coordination_usage 用 hashed record 或 unknown-with-reason，未知不填零，估算不等于账单，也不声称全链总 cap。具体范围以实际 schema/gate 为准。

## 受管握手：校验 → 准备 → 执行

以下是 Bash/PowerShell 通用命令形状。`ABS_MANAGED_ENTRY_PY`、`ABS_HANDOFF_JSON`、`ABS_PREPARED_EXECUTION_JSON` 都须先换成本机真实绝对路径，执行前检查无占位符；不需要原开发机 shell/目录。entry 路径按 receipt 定位，不能运行源码树里的 gate 冒充安装资源。

```text
python -B "ABS_MANAGED_ENTRY_PY" --check
python -B "ABS_MANAGED_ENTRY_PY" --execute -- --inspect
python -B "ABS_MANAGED_ENTRY_PY" --execute -- --validate "ABS_HANDOFF_JSON"
python -B "ABS_MANAGED_ENTRY_PY" --execute -- --prepare "ABS_HANDOFF_JSON"
python -B "ABS_MANAGED_ENTRY_PY" --execute -- --run "ABS_PREPARED_EXECUTION_JSON"
```

每步检查实际输出和退出码后再执行下一步；不是无条件批处理。validate 应返回 `state:validated, model_calls:0`，只读准入；prepare 会创建 owner 工件及按需 Workspace，成功返回 `state:prepared, accepted:false, model_calls:0`、execution/policy/input_manifest 路径与 SHA。读取真实 prepared 回执并核摘要，用其 execution 路径（当前为 owner_output/execution.json）启动 run，不手填一份 execution.json 绕过 assembler。prepare 不运行 build/check/model；**通过受管 gate 仍会启动 Pi 版本探测进程**，零模型调用不等于零进程。run 才进入有界 Builder/检查循环。

executor exit 0 可指 inspection/validated/prepared/candidate，exit 1 是已执行的 failed/stopped/blocked-cleanup，exit 2 是准入/配置/runtime 错误；wrapper 自身失败另读 stderr，不仅看数字。保留真实错误输出，缺/坏回执不得当成功。不得借 NativeNotes、BaselineA 或 console 测试造的设计资料作为新项目真实 Evidence；示例只帮助理解 schema。

## 读 typed 返回，再交原责任人

运行后核 `typed_check_report_valid`、与本轮 owner/round/冻结 check plan/source refs 匹配的 **check report v2**，逐项 required/optional、reason code、真实执行结果和 `return_summary` 的 disposition/affected_tasks/checks/return_to/refs。v1 diagnostic、自由文本 note、Ready 或只含 passed 的记录不足以路由/接收。optional 不得冒充 required 的阻断或通过；合法 typed 组合才可使用，不从单个字段或错误文案推导目的地；该组合校验和 optional 隔离仍应以最终独立审查/实物为准。

| 返回原因 | 原 runner 的动作 |
|---|---|
| required needs-evidence | 停自动 refine，回原 PRIMARY；其按原 scope 决定有界 REA 补证，不由返回标签自动调用/授权。 |
| unsupported | 停该后端，交 lead 判断能力/换后端；输入/Spec 类原因遵循有效 typed return_to 交 Spec runner，不把所有 unsupported 强改路由。 |
| needs-spec / needs-scope | 分别交原 Spec runner / lead，Builder 不改意图或扩大 scope。 |
| implementation-failed | 只在原 frozen plan/max_refinements/预算内修复，耗尽交 Spec runner，不研究补事实。 |
| cancelled / cleanup unknown | 停新动作；unknown 的外层状态优先 blocked-cleanup，保留底层 return cause 和 lease，确认 owned writers/preview 退出前不启动替代者。 |

返回摘要只是引用原责任人的运行工件，不是 accepted、任务授权或自动 dispatcher。没有 return_summary 也不代表成功：还须实际 required coverage/Checks.good、输入身份、diff、退出与 cleanup 都成立，再由原 runner/lead 接收及独立验收；`accepted:false` 保持。补证/合同修订由原 owner 接收新引用和 lead decision/selection，冻结新批次、fresh owner_output/run root；原记录/历史不覆盖，不跨 run 续旧 session。需要取消/换模型/回退先停接单并确认退出；installer restore 仅条件恢复 journal 管理的部署字节，用户后改 conflict 保留，不恢复成果源码、业务数据或远端副作用。

## 加壳与行为复刻

保留原加壳目标 identity/hash，脱壳 dump、伪码和动态观察作为带 operation/environment/hash/limitations 的派生引用。前段由原 PRIMARY/REA 在原 scope 内取证，再由 lead/Spec 冻结行为与实现任务；Craft 不必亲自脱壳二进制才可实现。壳内不可见事实不猜成 observed，缺证回原路线；bounded 工具门也不把派生来源提升为 Clean Room。只能声明选定场景/环境的行为证据，不能保证全软件 1:1 复刻。
