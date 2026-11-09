# 可选 Craft 本地 bundle

此增量支持 installer 的本地分发、更新、静态验证和条件恢复机制。可复现构建、canonical owned source、独立官方 Pi 分发及待冻结阻塞见 [portable packaging](craft-packaging.md)。Craft 默认关闭，`all` 仍只有 REA、Spec Kit、reverse。显式 `--with-craft` 或 `--components reverse,spec-kit,craft` 才选择 Craft；只支持 Pi，必须显式选择 reverse 与 Spec Kit，不自动补选依赖。未提供真实、完整 bundle 时返回 unsupported，不追官方 latest，不拿原版 release 替代兼容补丁构建。

**支持状态：本地文件机制通过离线夹具；真实产品 bundle、RPC driver/policy 联调、provider 资格、宿主加载、取消和完整任务尚未验证；公共换机分发尚未支持。** 测试使用明确标注的 toy Python 工件，不是可安装的产品包。本仓不预填任何产品 release URL、资产摘要或发布版本号。

## R46 跨组件合同门（0.7.0 候选）

Craft 被选中时，组件名称或 VERSION 数字本身不能证明合格。plan 要求显式 `--reverse-root` 指向已具备执行合同的本地 reverse 源；当前公开 release 仍为 1.8.2，不合格。本地 1.9.0 候选尚未发布，不能替换已有 tag 或假造公共资产。未提供显式合格来源时返回 `Craft needs-contract`；正式发布后须另核确切 pin/tag/工件，不自动安装未发布版本。普通 core/all 未选 Craft 时不要求此 descriptor。

同一 `scripts/craft.py:reverse_contract(root, expected=None)` validator 在 plan、apply 首次写入前及激活前、receipt verify、受管 entry 任务启动前执行。固定包根相对文件 `skills/reconstruction/references/execution-backend-contract.json` 必须为 schema_version 1、contract_id `reverse.r46.execution-backend`、contract_version 1，恰含这三项及 `min_reverse_version`/`capabilities`/`required_files` 六个字段。VERSION 必须是严格三段稳定 SemVer 且满足声明的 minimum >=1.9.0。

capabilities 必须恰为四项且无重复：`r46.accepted-research-v1`、`r46.single-implementation-owner-v1`、`r46.bounded-pi-builder-v1`、`r46.candidate-independent-acceptance-v1`。required_files 必须恰含以下四项 `{path, sha256}`，摘要取实际原始字节；数组次序不承担语义：

- `skills/reconstruction/references/execution-backend.md`
- `skills/reconstruction/SKILL.md`
- `skills/ops/role-map.md`
- `skills/reconstruction/references/spec-kit-workflow.md`

未知字段/schema/capability、重复 JSON 键或文件、缺项、畸形 hash、绝对/逃逸/其他路径、symlink/junction、VERSION 过低与字节漂移都拒绝。plan/receipt 的 `craft_reverse_contract` 保存包根、descriptor 原始 SHA256、VERSION/其原始 SHA256、四文件摘要；apply/verify/entry 与该冻结值比较，不能通过重新填写 descriptor hash 认领后改。无需硬编码开发机路径或某一轮四文件 hash。此声明不授予任务范围、不取代 full reverse source identity、原 Evidence 或独立验收，也不创建第二权威账本。

## Windows 目标路径预检

首版 Craft 安装支持传统 Win32 路径预算：最终文件最多259个 UTF-16 code units、父目录最多247，并为原 atomic 写入预留24-unit临时basename及版本目录重试后缀。plan 在任何外部命令前、apply 在创建锁/Journals/`.installer` 前，检查 bundle 与按需/原Pi adapter的实际文件映射、完成标记及事务/配置路径。超限返回 `craft-path-too-long` 和“选择更短安装根”，附相对文件、计数与上限。建议使用短独立根，例如 `D:/wf`；结果还取决于实际包内最长路径与agent目录。

这是本产品首版portable Win32支持范围，不判断系统 LongPathsEnabled 状态，也不承诺某些Python进程能写长路径就表示所有外部工具可用。不会开注册表、要求admin、添加扩展路径前缀或缩改许可证文件名/摘要。非Craft核心安装与非Windows路径逻辑不变；本预检只属于宿主installer bootstrap，不改变native bundle/reader工件或其manifest。下载stage的解压路径支持另属acquisition，不由本门扩大。

## 调用

在 installer 根目录运行。新电脑先联网获取完整官方 Pi/Node 依赖，不需要复用开发机路径：

```text
python -B scripts/build_craft_bundle.py acquire-pi --stage .local/pi-upstream
```

该命令使用固定 npm lock、官方 Node archive/hash、新隔离 prefix 和无模型 RPC 探测，生成 `acquisition-result.json` 中的 `installer_pi_options`，可直接用于下方 plan；详见 [联网获取与参数衔接](craft-packaging.md)。这是目标机从上游获取依赖，不是我方重分发 Pi/Node ZIP。官方依赖不裁剪；当前缺少一个包的许可正文只阻断 `release-pi`。真实 Craft native bundle 仍须由后续构建阶段提供，下面不会从 Rust 源码假造 binary。

```text
python scripts/install.py plan --components reverse,spec-kit,craft --client pi --root ../staging-workflow --agent-dir ../staging-agent --project ../staging-project --reverse-root ../reverse-skill --craft-bundle ../verified-craft-bundle --craft-pi-node ../standalone-node/node.exe --craft-pi-entry ../standalone-pi/node_modules/@earendil-works/pi-coding-agent/dist/bundle/cli.js --craft-pi-distribution ../standalone-pi --craft-pi-version 1.5.0 --output .local/craft-plan.json
python scripts/install.py install --root ../staging-workflow --plan-file .local/craft-plan.json --apply
python scripts/install.py verify --root ../staging-workflow
```

选择 `all --with-craft` 会保留原三个核心组件并增加 Craft，也会按既有机制安装 REA；若只做本地 Craft 集成，使用上面的明确子集。Spec Kit 的已有复用参数和 `--spec-kit-version` 继续适用。

`--craft-pi-node`、`--craft-pi-entry`、`--craft-pi-version` 和 `--craft-pi-distribution` 是独立 Builder Pi 的显式身份，不能用 PATH 上的 `pi` 替代。Node、入口、独立分发根的全部文件及依赖树摘要冻结在计划和 receipt；plan/apply、verify 和受管入口都复核。plan/apply 用所选 Node 执行所选 CLI 的 `--version`，输出必须等于 bundle 中的精确 Pi 版本。版本探测及 entry 子进程环境移除 `NODE_OPTIONS`/`NODE_PATH`，不接受隐式外部 Node 注入。此检查不认证包来源、实际动态 import 行为、provider 凭据或 RPC 运行资格；新电脑须使用集成打包阶段已审过的完整独立官方分发。任意 node/entry 加未记录的 hoisted dependencies 不获支持，不硬编码开发机路径，不复制个人 agent/profile、settings、MCP 凭据或 sessions。

`--craft-pi-distribution` 根必须先有 `pi-runtime.json`，否则在目录遍历前即返回 unsupported。manifest 要有 `schema_version: 1`、`name: official-pi-standalone`、精确 `version`、`dependency_closure: self-contained-node-modules-v1`、`package_root`、`dependency_root: node_modules`、`entry` 和全量 `files` → SHA256（不含 manifest 自身；manifest 原始摘要也被 installer 冻结）。package_root 必须在该 node_modules 内，入口必须为该 package 的 `dist/bundle/cli.js`，package.json 名称为 `@earendil-works/pi-coding-agent` 且版本匹配。所有声明 dependencies 必须能在分发根内解析；不支持外部 hoist/symlink/junction。该 manifest 的闭包声明须由集成打包阶段审查，本检查不从任意 JavaScript 推导所有动态导入，不是 OS import sandbox。

只遍历这个显式分发根，禁止其中出现 auth.json/mcp.json/settings.json/credentials.json/.env/backups 路径，拒绝后不读该项。不会扫描机器整个 Node/Pi Web runtime。当前开发机嵌套 Pi Web 安装没有这样的独立分发资格时，应报告 unsupported；不得仅因 node/entry 的两个 hash 相等就声称精确运行时。真实分发打包与加载验证仍是后续集成阻塞。

更新保留 receipt 已记录的 Craft opt-in、bundle 源路径、Pi Node/入口/完整分发根和版本。更新前保留原源目录；要移动或替换源，显式重新指定 `--craft-bundle` 并重新 plan。更新仍按当前命令明确选择核心组件，不静默收缩原范围。旧 receipt 没有 Craft 时不会自动启用。`craft_update` 记录 old/candidate 的 manifest/摘要、源引用、隔离版本目录和未验证资格；它不是已通过运行验收或人工晋级的记录。

## Bundle 格式

包是已解压、可分发的独立目录，根文件为 `craft-bundle.json`。禁止 root/祖先/子项 symlink 或 junction，禁止 `.git`/`.installer`、路径逃逸、大小写冲突。包内所有文件必须列入 `files`，唯一例外是 manifest 自身；manifest 自身的原始字节摘要也进入 installer 冻结的全量 inventory。新增文件、漏文件、hash 变化或计划源根变化都会拒绝应用。仅声明身份及匹配本地字节不认证远端来源或构建可复现性。

| 字段 | 必需内容 |
|---|---|
| `name`, `version` | `craft-pi-bundle`、精确三段包版本；由真实打包阶段确定，不是 installer 新发行号 |
| `contract` | 下述 adapter/installer entry 合同；未知 contract/min_reader/capability 拒绝 |
| `base_commit` | `0326b4de8051f85a0f3139cd82f88f76911e6a35`；更换 base 须先审补丁兼容并修改支持清单 |
| `artifact` | `os` 为 `windows`/`linux`/`darwin`，`arch` 为 `x86_64`/`aarch64`，与运行主机匹配；`source_commit` 是实际构建源的完整 commit，`build_source` 记录真实构建来源、工具链/target 与依赖前提 |
| `pi` | 实际要求的精确 `version` 与 `protocol: rpc` |
| `files` | 所有工件/依赖/文档/许可的规范相对 POSIX 路径 → 实际 SHA256；不可填占位摘要 |
| `patches` | 非空且顺序固定的 `{path, sha256}` 数组；每个 patch 原件也必须在 `files` 中且 hash 相符 |
| `runtime.entry`, `entry_kind` | 真正执行 owner 的相对路径，以及 `native` 或 `python`；不接受 Rust 源码或 build 工作目录代替可执行工件 |
| `runtime.driver`, `driver_kind` | 真正逐消息 RPC driver 的相对路径及 `native` 或 `python` |
| `runtime.entry_protocol` | 包内正式入口参数/协议说明的相对文件路径，必须有 hash；installer 不猜 owner 参数 |
| `runtime.required_files` | 非空、无重复的必需运行依赖相对路径；所有文件都须存在并有 hash |

固定合同为：

```json
{
  "name": "craft-pi-execution",
  "version": 1,
  "min_reader": 1,
  "required_capabilities": [
    "craft-bundle-integrity-v1",
    "craft-resource-ownership-v1",
    "craft-entry-gate-v1"
  ]
}
```

这些 capabilities 只描述这里实际实现的文件/资源/入口 gate，不宣称已实现 owner 单写、取消或权限 sandbox。实际运行合同由后续桥接/policy 集成验证。另必须保留 `Cargo.lock`、`LICENSE-MIT`、`LICENSE-APACHE`、`ATTRIBUTION.md`、`THIRD_PARTY_NOTICES.md`。完整上游依赖与所需 runtime 由打包者精确列入，不是拷一份 checkout 就就绪；品牌许可另审。

native 工件必须非空且在 Unix 可执行，Windows 使用 `.exe`。portable Python 工件必须非空 `.py`，由当前 Python 3.11+ 执行。所有引用相对 bundle root，移动解压包后重新 plan 可用；冻结计划不能随源目录移动而悄悄改根。Windows GNU 构建可在真正构建并检查依赖后记录其 target 与摘要；本增量没有构建 Rust，也不声称 MSVC/GNU runtime 已通过。

## Pi 按需资源与入口

真实安装使用 `root/versions/<frozen-id>/craft-bundle` 的逐字节副本，源包不修改、不直接注册。专用 skill-only package 在同版本的 `craft-pi` 中，含 reconstruction-execution skill、相对 references、builder instructions、portable entry gate、reader 代码和 receipt pointer。Pi settings 只增加/替换这一个精确包注册，保留用户其他字段；重复、filtered、其他副本、父目录/hub 或直接 skill/extension 注册会拒绝。

plan 的 `craft_resources` 冻结全部 entry/skill/reference/builder instructions、三个随包 reader 脚本与 receipt pointer 的文件 inventory/hash。apply 首次受管写入前、资源文件写入前及 receipt 激活前复核；plan 后改源码、新增/删除资源均拒绝，不能把新字节认领为该冻结计划的成功结果。

不新增控制 profile，不覆盖用户 AGENTS，不管理旧人工 profiles。主流程显式选择本执行 backend 时读取 `/skill:reconstruction-execution`；只有一份按需 builder instructions。原 R46、Spec implement/converge、task owner、独立验收职责仍在原系统。

在 receipt 的 `craft.resources` 定位到安装包后：

```text
python -B <craft.resources>/entry.py --check
python -B <craft.resources>/entry.py --execute -- <runtime.entry_protocol 中已核实的正式参数>
```

check 校验所有 bundle/资源 hash、contract、唯一注册、Pi Node/入口/完整分发与依赖树身份并重新核 `--version`，输出实际命令；execute 在同样 gate 后只调用已冻结 owner。入口以 bundle 为 cwd，输出 `CRAFT_BUNDLE_ROOT`、`CRAFT_PI_NODE`、`CRAFT_PI_ENTRY`、`CRAFT_PI_VERSION`、`CRAFT_PI_DISTRIBUTION`、`CRAFT_BUILDER_INSTRUCTIONS` 环境变量给 owner；集成打包阶段须让真实 owner 使用并验证这些输入。未提供真实 owner 时没有完整执行能力。此通用入口不替 owner 初始化隔离 agent、加载 provider、持租约或确认进程清理。

## 更新与恢复

installer 与 Pi 入口包为 0.7.0 未发布候选；原生 bridge/executor/bundle 仍各自使用 0.1.0，不在这里修改其生成 manifest。含 Craft 的冻结 plan 使用 schema_version 2，普通 core plan 继续 schema 1；adapter transaction protocol 仍是 0.2.0。新 reader 只接受对应组件范围的 schema，Craft 不能用 schema 1 重放。原 0.6.1 validate_plan 实际先检查 schema==1/adapter==0.2.0，因此会在配置写入前拒绝新 Craft plan；该行为由加载 Git 中原 reader 的离线反例核实。

receipt schema 仍为 1，Journal 字节格式保持原样。旧 0.6.1 receipt verify/restore **没有**新增字段/min_reader 的 enforcement：旧 verifier 至多检查其识别的 core，旧 restore 也不因 Craft 新字段自动拒绝，不能声称 schema 2 plan 保护延伸到了 receipt。部署与恢复推荐新 reader；Craft 任务前必须由新受管 entry 自身执行完整合同门。Craft 自有 contract version/min_reader 仍为整数 1（能力协议序号，不是 installer SemVer），没有无理由升级到 2，也没有伪造 installed:false 来阻止旧程序。

Craft 副本、新资源和完成标记全部使用原字节 journal。失败不写成功 receipt，已有安装保留；pending 在新安装前从新到旧条件恢复，receipt 最后；未知 Craft 合同拒绝恢复。恢复遇用户编辑的工件、instructions 或注册时保留字节、报告 conflict，receipt 不假回旧版。异字节已有资源不会无条件覆盖，源包和用户成果/业务数据不归 installer 所有。

回退前由实际执行 owner 停接单、取消并确认所有写者/preview 退出，保留 run 和用户数据；installer 本身不启动执行 owner，也不宣称自动完成该生命周期前置。完成此项后：

```text
python scripts/install.py restore --root ../staging-workflow
python scripts/install.py restore --root ../staging-workflow --apply
```

只回退活动事务，再逐个向旧事务回退。restore 是部署字节和注册回退，不是业务数据库/源码成果回退；旧 reader 与 Craft v3/v4 数据恢复须在相容副本另验。冲突可能造成部分资源已恢复，活动 receipt 仍保留，需先审差异后重试，不能把这时的 receipt 当成可运行保证。

## 后续集成与公开分发阻塞

后续阶段须将独立 RPC crate、固定 base 的 Craft policy patch、reverse 执行合同组装为真实 bundle，真正 build 后才计算文件 hash，核 Pi 1.5.0 的绝对入口与真实 provider/model/effort、单写、权限负例、取消及完整业务切片。本增量无需等待这些组件即可审查其离线机制，但不替代它们的验收。

远程仅准备了 `scripts/craft.py:pinned_release` 的显式官方 GitHub pin 元数据解析：核 tag→commit、正式 release、唯一 asset、GitHub SHA256 与官方 URL；离线反例含移动 tag/缺 hash。它不下载、不解包、不被 CLI 自动选择、不代表任何兼容资产已经发布。当前 CLI 无 bundle 即 unsupported。真实包通过集成、兼容、升级/回退、许可/品牌与运行验收后，才可另行实现已核资产下载并正式发布；**只有 local bundle 的当前结果不满足公共换机分发**。
