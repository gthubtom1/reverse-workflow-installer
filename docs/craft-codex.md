# Codex 的 Craft 受控执行

这个适配把原 Pi 流程中已经存在的后半段接到 Codex：

```text
原 reverse router → PRIMARY / REA 分析取证 → lead 接收 → Spec tasks
  → accepted handoff → validate/prepare
  → 一个 Codex Builder → build/check/refine
  → typed result → 原 Spec runner / lead 接收 → converge / 独立验证
```

复用固定 Craft `AcceptedResearch`、`RebuildRun`、单写租约、六个 bounded Build 操作、冻结 build/scenario/check plan 和 typed return。新增的是 Codex app-server 驱动、经真实 native effect probe 验证的固定运行 profile 和安装接入。Builder 使用目标机原有 Codex CLI 的确切版本与 binary SHA；`agents.enabled=false`、空环境及关闭 Code Mode/web/hooks/plugins 等官方控制固定施加，每次实际工程操作继续进入原 Gate。上游 Craft MCP/app 可保留为原 PRIMARY 的工具；它自己的独立 `rebuild_start` 不替换这条链。原 Pi 发行、source manifest、发布 pin 和已安装资源保持独立冻结。

## 新电脑与已有安装

从 installer 当前 `main` 开始。Python 3.11+、Git、uv、适用 Node/npm 和已能使用的 Codex 账号由目标机提供；不复制另一台电脑的认证文件。本次协议 profile 固定 `codex-cli 0.167.0-alpha.4.1` / app-server v2，不能静默换用其他版本或 PATH 上的另一 CLI。其他版本须先按同样的离线工具目录、协议和清理准入验证。

用户要求包含 Craft 的完整复刻流程时，安装 AI 必须加 `--with-craft`；旧的 `all` 默认只有 REA、Spec Kit、reverse。安装上游 MCP、禁用竞争 Skill 或检查工具可见，均不能代替安装本执行包。

1. 按 [Codex 发行 pin](../releases/craft-codex-windows-x64.json) 获取精确 native artifact 与配套 reverse source。使用新的短 stage，失败保留该 stage 与日志，不改 pin 或降级为别的 bundle：

   ```text
   python -B scripts/acquire_craft_codex.py --pin-file releases/craft-codex-windows-x64.json --stage D:/cw/codex-craft --codex-cli <实际绝对codex.exe路径> --deadline-seconds 600
   ```

   helper 只下载、核 ZIP/manifest、取得确切 Git commit 并对照 canonical blobs、校验原 reverse Codex descriptor 和 CLI。只有全部成功且 owned 进程/管道清理已证实，supervisor 才发布 `complete:true` 与 `installer-options.json`；worker 的 candidate 文件不表示完成。它不安装、不登录、不调用真实模型。获取目录是保留的版本化源缓存：receipt 仍引用其中的 reverse 或更新所需 bundle 时不要删除，不放进系统 TEMP。公共下载不可达时停止，不用猜测目录或自己填写成功记录。

2. 使用真实配置根和 helper 返回的三个路径生成计划。已有安装沿用原独立工具根；全局 Reverse 不要求成果项目，不要在安装仓库创建业务 Spec：

   ```text
   python -B scripts/install.py plan --components all --with-craft --client codex --root <独立工具根> --agent-dir <实际CODEX_HOME> --reverse-root D:/cw/codex-craft/reverse --craft-bundle D:/cw/codex-craft/craft-archive --craft-codex-cli <实际绝对codex.exe路径> --output .local/codex-craft-plan.json
   ```

   已有上游 Craft/REA 广域 Skill 时，按 plan 的准确路径使用 `--exclude-workflow-skill` 原生迁移；后续更新沿用已接受状态。保持官方 Skill 原文、MCP/schema 和用户其他配置。无需新建全局 Craft execution Skill；受控资源只安装到本事务的 `versions/<id>/craft-codex`。

3. 用户授权范围内应用已审计划；首次使用 `install`，已有 receipt 使用 `update`：

   ```text
   python -B scripts/install.py update --root <独立工具根> --plan-file .local/codex-craft-plan.json --apply
   python -B scripts/install.py verify --root <独立工具根>
   python -B scripts/install.py accept --root <独立工具根>
   ```

   plan/apply 及激活前重核 source、runtime、reverse 合同、entry/resources 与配置；receipt 记录真实宿主、完整 CLI 版本/摘要和独立 backend。update/reinstall 不会因包移动或模型切换自动认领新输入。restore 仍使用原 journal 条件恢复，用户后改产生 conflict 时保留字节；安装恢复不回滚成果代码和业务数据。

4. 正常重开 Codex，核 `reverse-workflow` 启用、上游独立广域 Skill 禁用及原 MCP 完整。通过 receipt 的 `craft.entry --check` 和 owner `--inspect` 检查安装入口，再从原 reverse 开始真实任务。MCP 目录、入口控制、受控执行能力、真实模型/业务验收分别记录。

## 原 runner 如何调用

从活动 receipt 定位 [execution resource](../adapters/craft-codex/skills/reconstruction-execution/SKILL.md) 和 [完整 reference](../adapters/craft-codex/references/execution.md)。原 Spec runner 为当前已接收任务选择 Craft 后：

```text
python -B <craft.entry> --check
python -B <craft.entry> --execute -- --validate <absolute accepted handoff JSON>
python -B <craft.entry> --execute -- --prepare <absolute accepted handoff JSON>
python -B <craft.entry> --execute -- --run <prepare 返回的 absolute execution JSON>
```

wire schema 以实际 bundle 的 entry protocol 为准。`validate/prepare` 不调用模型；`run` 重建并核验原 handoff/lead 决定与全部摘要后才启动 Builder。runner 不派第二个 Worker，不让 Builder 改任务勾选、检查预期或原 Evidence。源码基准、外部 baseline、任务、模型或范围变化后，先确认旧写者退出，再由原 owner 接受新版本并 prepare 新批次。

六个实际工程操作是 `build_files_list`、`build_file_read`、`build_file_write`、`build_file_edit`、`build_command_run` 和 `build_checklist`。Codex 原生环境、shell/文件写入、研究、hosted web、协作、任意 MCP/插件不得成为旁路。原生交互请求由 driver 拒绝并停止；动态工具的效果仍逐次进入原 Engine Gate。工具目录准入必须捕获真实 Codex 发给本地假 Responses 端点的完整目录，不能只看 feature flags 或顶层 `tools`。

每轮使用明确模型 profile。正常账号由原 Codex CLI 使用，执行桥不复制 auth；版本、binary digest、固定 profile digest、有效配置及模型身份分别绑定。原生返回的生效 provider/model/effort、模型切换、usage、thread/turn 和终态单独核对；未知不补造。现版本没有可据此声明的单响应或总 token/费用硬上限；仅在本批明确接受已验 wall/refine/deadline 边界与实际 usage 审计时使用 audit 模式，要求不支持的硬限则启动前返回 unsupported。

缺证以 typed return 回原 PRIMARY/REA，规格与范围问题回原 runner/lead；只有实现错误在冻结计划和预算内 refine。required 未执行、unknown、不支持或失败不能取得合格 candidate。原 runner 接收实际 diff、匹配 check report 和 cleanup 后继续完整 implement/converge，独立验证者仍在原链；backend 不自行置 `accepted:true`。

取消使用绑定 run/turn 的控制身份、Codex `turn/interrupt` 和实际终态；随后有界清理自有进程及管道。Windows Job/observer/worker/receipt 的必要证据缺任一项均保留 lease 并返回 blocked-cleanup，不按名称结束 Codex Desktop 或无关任务。

## 来源与维护

- 原 reverse Codex descriptor：`skills/reconstruction/references/execution-backend-codex-contract.json`。它绑定共同 R46/Spec 文档的实际字节，不创建另一套领域流程。
- 自有 host 源码：`adapters/craft-codex/runtime`；固定 Craft engine base、旧 policy series 与新增 Codex permission patch 各自记录，旧 Pi 文件不改。Codex CLI 由目标机提供；不重编或重分发 Codex/V8。
- `scripts/build_craft_codex_bundle.py` 复用既有 GNU build、owned process、DLL 与原始许可收集 helpers；显式 freeze 后从已提交源码构建 executor/driver，并纳入准确的 `codex-profile.json`。生产构建不启用 fixture feature。
- 首次构建使用明确 Rust/Cargo 1.99.0 Windows GNU 与 MinGW 工具路径、新 stage/target 和锁定依赖；不自动安装编译器。`freeze` 只在所有实现 owner 停止编辑并完成审阅后执行；任何源、lock、policy 或 recipe 变化都使该身份失效。
- 真实 Codex + 本地 canned Responses 的定向协议夹具可验证目录、动态 Gate、身份拒绝、终态、中断与 owned cleanup；不消耗真实模型，不证明任意原版目标的复刻质量或业务通过。安装报告须保留这项验证边界。
