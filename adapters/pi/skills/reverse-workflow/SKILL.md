---
name: reverse-workflow
description: 逆向、二进制、APK、前端签名、协议、API 安全、复刻、行为对比、版本追踪或知识维护任务的统一入口；先定位安装回执，再交给 reverse-skill 原生 router 选择 PRIMARY。
---

这是组合工作流入口，不创建第二个 router。普通代码编辑或一般问题不强制进入逆向流程。

读取此技能目录相对路径 `../../receipt-location.json`，再读取其中 `receipt` 指向的本机 JSON。仅使用 `installed: true` 的活动回执；缺失时提示从安装仓库运行 verify，不猜测工具路径。

1. 从回执 `reverse.root` 读取原 `RULES.md`、`skills/MASTER-ROUTING.md` 和 `reverse.master`。恢复现有 case、target identity、scope 和用户答案；维护工具仓库不创建虚假的样本 case。
2. 由平台原生 `skills/scripts/master-route` 选择 PRIMARY，再读取对应原 `SKILL.md`。严格只读请求使用 `-DryRun` / `--dry-run`，不创建 route-scope/case；执行模式才按原授权门建立或复用 case。支持的参数以当前安装版本为准；旧版没有只读路由时读取配置审查，不能偷偷写元数据。
3. PRIMARY 创建一个 bounded work item 后才调用官方 REA MCP。保留实际 schema、Evidence、unknown、预算、provider 和 cleanup。REA 是分析 backend，不选择总目标、scope、case 或完成结论。
4. 独立实现前先有原目标的行为模型、成功标准和 Evidence handoff，再进入原 `reconstruction/SKILL.md`。Spec Kit 只用成果项目中实际生成的官方资源；不在工具仓库 init，也不以猜测规格替代缺失证据。
5. 先核对原 `scope.md`、`timeline.md`、`workitems.md`、Evidence 和 Spec Kit feature/tasks；用户已有回答继续有效，只澄清缺失或被新证据推翻的决定。

按原仓库 `skills/ops/guided-operator-contract.md` 与 `skills/ops/beginner-operator-guidance.md` 交互：目标 `GOAL-*`、影响/授权范围 `SCOPE-*`、交付 `DELIVERY-*` 分开。用户可以复制整句选项、稳定 ID，或回复当前展示的 A/B/C、1/2/3。别名只对应同一 case/target 最近的明确选项；ID 本身不授予权限。清楚的自然语言决定直接沿用，不要求重选。

用户不选择工具、provider、REA、Static/Dynamic、脱壳、dump、IAT、Frida、Spec Kit 或 grilling。技术策略由 agent 在原 scope、预算和清理边界内决定；无范围内可行路径时诚实报告阻碍。只有真实结果、对象、授权/影响或交付取舍才给可复制卡，缺少用户独有材料只问必要输入。不能为阶段切换、换工具或事实核查制造菜单。

重要阶段用白话报告“本轮做了什么 / 目前确认了什么 / 目前还不知道什么 / 当前阻碍 / 下一步”。汇报不等于等待批准；常规工作持续推进。涉及授权、许可证或功能门时遵循原 `skills/ops/authorization-coverage.md`：逐组件、逐 gate 核对 Evidence、预期行为、补丁、回归和回滚。比如“已验证 1/7 个授权面”不能称整体完成；回归失败重开相关行。机械校验、文件生成和模型自述均不等于业务验证。

Grilling 只处理显式访谈或真实的目标、范围、产品行为和交付取舍。读取技能清单中官方 `grilling/SKILL.md`，保持其正文、格式和共识规则；既有用户回答沿用，既定方案的执行不因阶段切换重开访谈。事实归 agent：文件/字节/运行结果由 agent 或 subagent 查证，不能反问用户。文档访谈按官方 domain-modeling 的阈值处理 GLOSSARY/ADR。

Installer 的 `pi-grill-me` / `pi-grill-with-docs` 是独立 wrapper，只读取官方技能。官方 `grilling`、`domain-modeling`、`grill-me`、`grill-with-docs` 均不可改写。可选 Grilling 未装时，普通 reverse 流程继续；用户明确要求访谈且技能缺失时说明缺口。

本入口是指令适配层，不是执行沙箱或强制工具拦截器。receipt 的未验证项保留未验证。安装成功不证明宿主加载、provider 可用或业务通过。自然语言未加载入口时，可显式使用 `/skill:reverse-workflow` 或本 package 的 `reverse-workflow` prompt。
