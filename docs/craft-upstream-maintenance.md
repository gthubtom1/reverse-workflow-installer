# Craft 上游更新维护指南

维护目标是固定上游差异、最小适配并重新取证，保留现有质量门。新对话可直接使用[升级提示词](craft-upgrade-prompt.md)。所有命令从 installer 仓库根执行；本指南不依赖原开发机、桌面 clone、私人 notes、auth 或 MCP 配置。

## 1. 先核身份与边界

读取 [AGENTS](../AGENTS.md)、[安装合同](craft-install.md)、[打包接口](craft-packaging.md)及其当前源码。用 Git status/HEAD、实际文件 hash、当前安装根的 `.installer/receipt.json` 和事务记录分别确认开发源、工件、安装与部署状态；旧文档不能覆盖实物。当前正式发布身份见 [Windows x64 pin](../releases/windows-x64.json)，公开 release 仍须按 GitHub 的 tag→commit、release、唯一 asset/hash 核实；发布存在不证明本机运行资格。runtime 的历史 README 按其原观察时点理解，遇矛盾应核 manifest/origin 和审查记录，禁止自动拼接不同快照。

**以下仅为本次基线，验收前重核，不是永久最新：** 每轮资格基线以实际 source manifest 为准；联合 `runtime/source-manifest.json` 尚未生成或与实物不符时，应报告未冻结，不能手填身份。下表只帮助定位已读证据。

| 层 | 固定身份与已有证据 |
|---|---|
| Craft | 完整上游 `0326b4de8051f85a0f3139cd82f88f76911e6a35`，保留完整依赖；[series](../adapters/craft-pi/runtime/patches/series.json) 为 4 个有序 patch、23 个源码摘要，含只读 admission 与 typed check report v2 门。原 series SHA `0807fb2219751caec408aa1c89d2a5bc8a5cbee17062e7c0814fe125b929ab16`；portable SHA `61cf9b94c6cc3b28de8f5ea16e44ee9be7f92937bac91da880bda3bda4919a6c`。该源码门已独立接受，定向 31 tests 通过，不等于全上游 suite。 |
| bridge/P1 | 原 source SHA `50a2494ae8b86dd59b1988566e2b347fc939f16c0dde6a9b6ba158875e4e33e4`；[原 manifest](../adapters/craft-pi/runtime/bridge/FROZEN-SOURCE-MANIFEST.json) 19 文件，历史 71 integration + 5 unit = 76 pass，另 1 private test ignored。 |
| executor | 原 source SHA `daa40ce151b45d483ca189dcd9e00bffd50a3499e16d06d56f7dd9e05dc2fa50`；[原 manifest](../adapters/craft-pi/runtime/executor/FROZEN-SOURCE-MANIFEST.json) 46 文件、原字节 SHA `f4ac2bbe706b281a5741e0b47e0d5aefd38c48ac13af3560f50dee6984c6706c`，由 [origin](../adapters/craft-pi/runtime/executor/snapshot-origin.json) 绑定。含 prepare 三项 context binding/privacy 修复，已独立接受；最终 27 tests 通过（11 observer + 16 integration）。 |
| installer/reverse | installer/Pi entry 正式 v0.7.0（`70cf9c779ec0198eb725b864af868ee88bcfbce9`），native Craft-Pi v0.1.0（`010e2e323f912806f3fc3f2b17b1f9f06c29c944`），reverse v1.9.0（`7cc3109bf14a570c9c852dc76cce05fff424e88c`）分开发布；获取 helper 独立为 `craft-acquisition-v0.1.1`（本次源码基线 `d29b1fe5b207cb36faf3df9533dad4faf23e1e72`）。reverse 要求 `reverse.r46.execution-backend` descriptor schema/contract 1 和四项 exact capabilities/四文件摘要，详见安装合同。Craft plan schema 2，core plan/receipt schema 1，事务协议 0.2.0，Craft contract/min_reader 1。旧 0.6.1 verify/restore 不认证 Craft。 |

历史 policy `0bdca190…`（22 文件）及 executor `e10b74d…`（28 文件）只用于追溯失败经验，不是本次身份；对应旧测试不认证新源码。本轮最终原生包已生成，P1/P2 source-layout 回归通过；安装后功能资格仍须按实际 receipt/protocol 和本批运行另验，不能写成全部通过。

我方完整源码、测试、fixtures、examples/helper 在 [runtime/bridge](../adapters/craft-pi/runtime/bridge) 与 [runtime/executor](../adapters/craft-pi/runtime/executor)，不是只留 binary 或外部工作区指针。各自 `FROZEN-SOURCE-MANIFEST.json`、`snapshot-origin.json`、`packaged-source-manifest.json` 区分原始与 portable 身份；生产 Rust/Cargo 字节保真，非生产路径转换单列。上游真实源码从官方固定 tree 获取，不能把反编译伪码冒称原 source。

runtime/外部文档关于 reverse 的“尚未安装”属于其观察时点，应按本机 receipt 和能力门判断；不要把旧断言写成永久状态。reverse 执行合同仍由 reverse owner 独占维护，本文不据并行文档中的旧 adapter 路径推断已部署位置。

## 2. 只读比较，再决定是否改补丁

先填目标、允许写根、预算、下游安装/项目状态与本轮模型选择，冻结 old/candidate 身份。获准联网时，从 [Craft 公共仓库](https://github.com/storytold/craft-anything) 获取明确 tag/commit，解析成完整 commit/tree，保留旧 fixed ref。以下 Bash、PowerShell 通用只读命令，`NEW_FULL_COMMIT` 和 `../craft-upstream` 须替换为本轮实际值/本地完整 clone；对象缺失先按获准范围获取，不自动追浮动 latest。

```text
git status --short --branch
git rev-parse HEAD
git -C ../craft-upstream rev-parse --verify NEW_FULL_COMMIT
git -C ../craft-upstream diff --stat 0326b4de8051f85a0f3139cd82f88f76911e6a35 NEW_FULL_COMMIT
git -C ../craft-upstream diff --name-status 0326b4de8051f85a0f3139cd82f88f76911e6a35 NEW_FULL_COMMIT
```

保存固定 compare、files/stat 和逐项 delta：功能/API/trait、lock/完整依赖、toolchain、build scripts、license/品牌、数据格式/migration、session/check/process 行为。分为无需变更、上游已吸收可删 patch、文本冲突、无冲突但语义变更、合同不兼容。**0 patch conflict、git apply 成功都不证明兼容。** 优先现有公开 seam；只有必要时改薄 patch，不抽取/裁剪 Craft 后端，不扩大 route 或复制 Study 引擎。

受管模式仍禁 Study/Extractor/新研究；缺证或 contract change 返回原 case/R46，由原 PRIMARY 补证/owner 接收新合同。单 owner、单编码 Builder、Spec 完整 implement/converge、lead 对原 Evidence 的晋级权不变；Builder 不递归派生、不写权威账本。

## 3. 按门重放与验证

1. 在 fresh、detached、固定上游副本依次核 patch hash、`git apply --check --index`、apply，核全部 source hash、Cargo/锁文件与依赖。本次应重放 4 个 patch；仅上游吸收并经审查后可删对应 patch。当前脚本内置 BASE=0326，没有 `--new-ref`；更换基线须在另行获准范围审改支持清单/recipe，不能只改 manifest 摘要。
2. 运行当前 API/protocol、准入/权限/身份/漂移/取消负例，编译并回放完整 own tests；policy 同时验证普通模式与受管模式无退化。本次 31/76/27 测试记录仅定位相应已验源码，新结果必须绑定本轮 source、工具、命令、输出、cleanup。
3. 独立 native UI + 业务 oracle 使用 fresh seed；headless 另验保存/关闭重开、错误输入/IO 与副作用。故意不持久化、错 stdout/退出码、假 receipt/错 source/重放 generation 必须在预期门失败；timeout/unknown 不算有效业务负例。实际 provider、精确 owned resume、取消/owner join/后代退出分别验证，缺 optional provider 如实 blocked，禁止换 model fallback。
4. 独立 review 后冻结 recipe/resources/reader，再构建 native 工件，记录实际 hash、PE imports/非系统 DLL 闭包、编译依赖原始 license/attribution。当前仅 Windows x86_64 GNU、Rust/Cargo 1.99 路径准入。recipe freeze 后 imported module 改变必须拒绝；旧 Cargo cache 只可经前 manifest/hash 校验复用并诚实记录 leaf relink 来源，不能关漂移门或假称旧 binary 等于新构建。
5. clean staging 验 install/update、pending/失败恢复、用户后改 conflict、receipt 最后恢复。迁移使用完整项目数据副本，逐格式验证新读旧、旧读新及拒写；旧 v3/候选 v4 边界不能靠改 version 强写。完整旧包/source/history/rollback receipt 均保留。
6. 前述 required checks 与 owner cleanup 都成立才讨论晋级。GitHub 发布须获授权并固定 immutable tag→commit、唯一 asset SHA 与 manifest，记录兼容 tuple：Craft tree/patch/lock/toolchain/OS/arch、bridge/executor、reader/contract/schema/min_reader、Pi/Node/RPC、模型假设、check plan/转换器/数据格式。当前 installer CLI 只接本地 bundle；独立 `acquire_craft.py` helper 已提供按正式 pin 下载、校验与解包的获取能力，见 [获取指南](craft-acquisition.md)，不等于核心 installer 新增直接 fetch flag。
7. 活动 profile/installer 部署单列；静态 verify、工具 accept、实际宿主重载/新会话加载、真实任务分别留证，不以打包或配置存在冒充加载。回退先停接单、取消并证实全部写者/preview 退出，再协调代码/包、部署注册、项目数据三层；Git 回退不能撤销业务或远端副作用，条件 restore 不覆盖用户后改。

## 4. 命令入口与新机器

先核实际帮助；下列命令仅显示参数，不构建、不安装：

```text
python -B scripts/build_craft_bundle.py freeze --help
python -B scripts/build_craft_bundle.py build --help
python -B scripts/test_craft_owned.py --help
python -B scripts/install.py --help
```

[打包指南](craft-packaging.md) 有 freeze/build 的完整参数形状；四次 `--patch` 必须与 series 同序。测试输入使用 recipe 生成的 sibling layout：`craft-anything-adapted`、`craft-pi-bridge`、`craft-pi-executor`，不能直接在 runtime 两个 crate 上猜路径运行。以下仅供未来获准验证时填写，`REQUIRED_*` 全是占位符：

```text
python -B scripts/test_craft_owned.py --source-layout .local/upgrade-build/source --output .local/tests/upgrade-owned --cargo "REQUIRED_CARGO_EXE" --rustc "REQUIRED_RUSTC_EXE" --gcc "REQUIRED_GCC_EXE" --node "REQUIRED_NODE_EXE" --target-dir .local/upgrade-build/owned-test-target --cargo-home .local/upgrade-build/cargo-home --release
python -B -m unittest discover -s tests -p test_craft.py -v
python -B -m unittest discover -s tests -p test_craft_packaging.py -v
```

依赖已在该隔离 cache 中才加 `--offline`，否则报缺项；不静默联网。policy tests 命令见 patch 0004 内 `policy-build-job.py` 源合同；native helpers 的 syntax check 不代表执行。新项目应读[生产 handoff 与返回合同](../adapters/craft-pi/references/execution.md)，按实际 receipt/bundle manifest 定位正式 entry protocol、production prepare-contract.md 和 schema；本次 `daa40ce…` 生产源码的 prepare 三项 context binding/privacy 修复已独立接受，27 tests 通过；`--validate ABS_HANDOFF` → `--prepare ABS_HANDOFF` → `--run ABS_OUT/execution.json` 的具体所装能力与本批运行资格仍按 receipt、协议和实际结果另核，不据源文件存在认证 bundle。executor 无通用 `--help`，核其 `--inspect`；不能用 NativeNotes/BaselineA 实验入口替代生产路径。

受管握手命令模板（Bash/PowerShell 通用；执行前将所有 `ABS_*` 换成真实本机绝对路径，逐步检查输出）：

```text
python -B "ABS_MANAGED_ENTRY_PY" --check
python -B "ABS_MANAGED_ENTRY_PY" --execute -- --inspect
python -B "ABS_MANAGED_ENTRY_PY" --execute -- --validate "ABS_HANDOFF_JSON"
python -B "ABS_MANAGED_ENTRY_PY" --execute -- --prepare "ABS_HANDOFF_JSON"
python -B "ABS_MANAGED_ENTRY_PY" --execute -- --run "ABS_PREPARED_EXECUTION_JSON"
```

owner 必须实际声明这些命令，且满足本批资格才执行。handoff 绑定原 case/scope/workitem/feature/spec/plan/tasks/acceptance、lead decision/selection 的真实 HashedRefs、标准 T### 任务与已完成依赖、目标/合格外部 bundle-baseline-index/check plan、批准源码/写根/模型预算。validate 只读，prepare 创建新 owner 工件及按需正式 Workspace，成功输出 prepared execution 路径/hash；run 使用这个真实回执路径，不猜 JSON。两者模型调用为零，wrapper 仍有 Pi `--version` 进程探测。场景/状态接口由原 verifier 提供，缺失回 needs-evidence，prepare 不自动研究或生成 UI oracle。

新 Workspace v1 `read_references` 必须为空；若 Builder 需文件读取规格/基线，原 owner 先准备正式 existing Workspace 和 staged readonly references，再交接，app 根不变且 spec/任务不入写根。不得清空必需引用凑通过；审过的 prompt/可读路径和真实 gate 应一致。加壳目标保留原 identity/hash，dump/伪码/动态观察保留派生来源和 limitations；原 PRIMARY/REA 在原 scope 取证后由 Spec 冻结实现，Craft 不必亲自脱壳，不能承诺全软件 1:1。

新机器先按 [公开获取指南](craft-acquisition.md) 使用 helper 0.1.1 获取正式 native bundle/reverse；下载 stage 的64 UTF-16 units根预算与安装根预算分别核。全自动 fresh 网络最后一次匿名 API 403、无 complete，已核 GET/hash 不能当作完整换机实测。再获准联网运行现有 `python -B scripts/build_craft_bundle.py acquire-pi --stage .local/pi-upstream`：官方 Node 24.20.0/Pi 1.5.0，全 npm lock/checksum、完整依赖，本次 Windows 实测 123 包；读取新生成的 `acquisition-result.json` 的四项 `installer_pi_options`，不复制旧机器路径。一个 Pi 依赖的授权正文仍 unknown，`release-pi` 阻断，不重分发 Pi ZIP、不裁剪包。native 编译依赖许可缺口也须独立关闭；candidate 缺许可模式不获发布资格。REA 6.8.0、Spec Kit 1.3.1 保留官方固定来源，不改官方源；凭据只用本机 env reference，经官方 resolver 解析，不 clone 个人配置。

输入至少包括接收后的任务/研究引用、原目标身份、允许成果根、源码起点、冻结检查计划、种子/基线和显式模型许可；缺项在创建 Workspace、租约或启动模型前拒绝。执行配置还需 driver/instructions/provider manifest 的实际路径与摘要，凭据字段只列环境变量名称。输出应能追到本轮输入、源码前后差异、真实产物、逐项检查与进程清理；公开摘要不含原始消息体、凭据值或私人端点。

运行后核实际 `return_summary`、typed check report v2/`typed_check_report_valid`、required checks、diff/cleanup，再交原责任人；不从文案或单字段猜 route，optional 不混成 required。required needs-evidence 停 refine 回原 PRIMARY/原 scope 补证，unsupported 交 lead（输入/Spec 原因遵有效 typed return_to 回 Spec runner），needs-spec/scope 分别回 runner/lead，实现失败只在预算内 refine。`0807fb22…` 源码门的 typed 组合校验/optional 隔离已独立接受，31 tests 通过；具体所装版本与本批运行资格另核 receipt/protocol，摘要不代表接受或授权自动调用 REA。cleanup unknown 优先 blocked、保锁；补证后原 owner 接收新引用/决定/selection，冻结新批次/fresh run root，不覆盖原记录或跨 run 续旧 session。v1 strict aggregate 返回 unsupported-budget；只有 lead 明确选择 audit-only 才用 wall/refine/per-response 硬界加 actual usage，协调消费未知保留理由，不声称总 token/费用硬 cap。更新/恢复仍留完整数据与用户修改，每项分别报告实测、历史或未知。

## 5. 窄检查表：避免重复失败

| 已踩边界 | 必须保留的判据 |
|---|---|
| Windows JS argv | canonical/verbatim 用于身份，Node 启动 argv 使用经再次 canonical 等价核验的普通 drive/UNC 拼写；禁止盲删前缀。 |
| RPC/session | settled + 权威 final stop + 无 errors + owned cleanup 才成功；agent_end/TurnDone 不够，resume 只接精确 header-verified owned 文件。 |
| effort/redaction | requested state 严格核三元组；final 的 optional thinking/provider effort 缺失保持 unknown，存在才 exact 校验。public_selection 只给 typed exact provenance 例外，未知 metadata/正文/error/tool 继续脱敏，不全局 skip mask；env 值不公开。 |
| source lease/process | PID + creation identity、父子存活区间与 retained handle；Wait signaled 才读 exit time，不能靠 PPID/PID 或非零 exit buffer 推断退出；unknown 保锁。 |
| baseline/source | Windows stdout CRLF 从观察冻结 exact bytes，不 normalize checker 凑绿。正确 candidate 可与 reference 字节相同；physical hardlink/原件路径不得冒名，身份查询失败拒绝。 |
| 最终状态 | Rebuild Ready 不等于 accepted；Checks.good 不等于 passed 字段。required coverage、真实业务、独立验收与 owner cleanup 全部单列；源码分发保留完整测试 fixtures。 |

本次 A/B 单切片双方均一次修复并通过独立业务/UI 检查，无 Craft 修复收益证据；普通 Worker 默认沿用，Craft 模块显式 opt-in。旧 B cleanup blocker 不追改成通过，e10b 单元/集成结果也不追认旧运行。可描述有条件的 opt-in capability available，不得声称 P3 收益通过或 scalability；Electron/CLI/Web/多窗口扩类各自验证。每轮交付实际 diff、输入/输出/错误、证据 hash、独立审查、unknown/阻塞和恢复入口，禁止借历史 pass 认证新版本。
