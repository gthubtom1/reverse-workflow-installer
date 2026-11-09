---
name: reconstruction-execution
description: Use only when the original R46/Spec implement runner explicitly selects the optional Craft backend for accepted implementation tasks.
---

普通 implementation-worker 仍是默认；仅原 R46/Spec runner 明确为本批选择 Craft 才使用本入口，不宣称单个 A/B 切片证明收益。先完整读取官方 implement 全部指令，保留 prerequisites、checklists、hooks、依赖、同文件串行、测试任务、阶段检查和最终完成职责；本 skill 只替换所选批次的编码后端。

按本目录相对路径 `../../receipt-location.json` 读取实际 receipt，再核 Craft 选择、reverse 合同、contract/min_reader/capabilities、工件摘要与唯一注册。以 `../../entry.py --check` 核受管入口；它有 Pi 版本进程探测，静态合格不证明 provider、任务或宿主已接受。读取[执行交接与返回合同](../../references/execution.md)，按 receipt/bundle manifest 定位正式 entry protocol 和 production prepare-contract.md；不要使用开发机路径或实验脚本。

核所装 owner 的 `--inspect` 与 bundled protocol，确有 `--validate`、`--prepare`、`--run` 才走生产准备链。源码具备接口不等于该 bundle 已收录或独立验收完成；缺能力返回原 runner，保留普通 Worker 路径，不猜参数或造假 JSON。通过受管 `entry.py --execute -- <实际 owner 参数>` 转发：先校验真实 handoff，再 prepare，核 prepared 回执的 execution 路径/hash，最后 run；具体命令模板见 reference。validate/prepare 不调用模型，prepare 会创建新 owner 工件及按需正式 Workspace，不能按只读动作执行。

原 lead/runner 准备真实 case/scope/workitem/feature/spec/plan/tasks/acceptance、lead decision/selection 的 HashedRefs、标准 Spec T### 任务和已完成依赖、原目标/研究 bundle 与合格外部基线、检查计划、批准源码、读写根、模型和预算。只交依赖已满足的一批；缺真实场景/状态观察接口回 needs-evidence，prepare 不自动研究或生成 UI oracle。一个活 owner、一个有界 Builder 持写权，不同时派普通 Worker，不递归派 Agent/crew。

运行后先核 typed check report v2、`typed_check_report_valid`、实际 `return_summary`、required checks、diff 和 cleanup。缺证回原 PRIMARY，能力不支持交 lead，规格/范围冲突分别交 Spec runner/lead；不据返回标签自动调用 REA、扩权或接受任务。cleanup unknown 优先 blocked、保锁，不启动替代写者。补证/改合同由原 owner 接收新引用，再冻结新批次和新 run root，禁止跨 run 续旧 session；实现失败仅在原预算内 refine。

runner 按真实结果接收并更新原 tasks，失败/未验证不勾选；单批完成不等于完整 implement。随后执行官方完整 converge，只追加有来源的缺项任务，下一轮 implement 再选后端。独立规格、原版行为和隔离运行验收仍由原链负责；Ready/candidate/exit 0 均不是 accepted。加壳/派生来源、预算和取消边界见 reference，不承诺所有软件 1:1 复刻。
