---
name: reverse-workflow
description: 逆向、二进制、APK、前端签名、协议、API 安全、复刻、行为对比、版本追踪或知识维护任务的统一入口；先定位安装回执，再强制交给 reverse-skill 原生 router 选择 PRIMARY。
---

这是组合工作流的唯一入口。它不是普通工具说明，也不是第二套路由器。遇到逆向、二进制、APK、前端签名、协议、API 安全、复刻、行为对比、版本追踪或安全报告任务时，优先进入本 skill。

读取此技能目录相对路径 `../../receipt-location.json`，再读取其中 `receipt` 指向的本机 JSON。仅使用 `installed: true` 的活动回执；缺失时提示从安装仓库运行 verify，不猜测工具路径。

1. 从回执 `reverse.root` 定位原仓库，先读原 `RULES.md`。
2. 读取原 `skills/MASTER-ROUTING.md` 和回执 `reverse.master` 指向的总入口，保留用户原话、目标身份与范围。
3. 按原仓库的平台原生 `skills/scripts/master-route` 调用原 router，读取其选出的 PRIMARY 的原 `SKILL.md`。授权、case 和工具门槛依原 RULES 执行；本入口不另做分类。
4. 仅在 PRIMARY 委派后调用官方 REA MCP，保留完整 tools 与 unknown；官方说明在 `paths.rea_package` 内按需读取。Spec Kit 使用回执成果项目内实际生成的原生命令/技能，不在工具仓库 init。
5. 恢复与追版读取同一成果项目中的原 case、证据、Spec Kit feature/tasks。知识维护读取原仓库的中立维护指引。

零基础操作员交互要求：每个重要阶段完成后，用大白话报告“本轮做了什么、目前确认了什么、目前还不知道什么、下一步建议”。下一步建议必须根据当前 Evidence 动态生成 2–5 个编号选项；每个选项包含白话动作、括号内专业术语、目的、影响、推荐项和预期结果。用户回复编号即可，用户不需要选择工具、填写技术参数或理解 REA/Ghidra/radare2。

Pi 端另装有 `grilling` 技能（`~/.agents/skills/grilling`，上游 mattpocock/skills，正文不改）。两者分工如下：

1. 只在形成方案、给出分析结论、审查已有报告/case/补丁/复刻项目，或准备改二进制/重实现之前调用 `grilling`；启动、授权、范围确认和纯事实分诊阶段不调用，不重复索取用户已给出的启动确认。满足调用条件时，先读取 `~/.agents/skills/grilling/SKILL.md`，按其完整规则工作，不自行摘要或重写其规则。
2. `reverse-workflow` 继续负责路由、授权、证据链、REA 门槛和阶段报告；`grilling` 只负责方案决策树和假设审查。进入 grilling 访谈后，该轮问题使用 grilling 的 `❓ **Q1**` / `➡️` 格式；reverse 的阶段报告放在访谈轮次之前或该轮完成之后，不插入 grilling 问题块。目标、授权、范围、下一步选择仍使用本入口的编号选项。
3. `grilling` 的“事实归 agent”在本入口强制生效：凡需读文件、跑命令、比对字节才能回答的问题，派 subagent 查证后直接给结论，不得当成问题抛给用户；只有决策类问题才进 frontier。
4. `GLOSSARY.md` 与 ADR 等术语产物写入成果项目，不写入 reverse-skill 仓库——该仓库白名单与泄漏扫描只接受 `skills/field-journal/**.md`。
5. `grilling` 未加载或不可用时按本入口原有流程继续，把该项记入 unknown，不阻塞任务。

当分析证据足以判断长期结果时，提供多个动态目标候选，并为每个候选附上可复制的 GOAL 文本。GOAL 文本由宿主的目标模式执行；入口只负责把当前 case、范围、约束、成功标准、unknown 和停止条件写清楚。候选必须根据当前证据生成，不能把源码恢复、行为等价重实现或二进制修改当成无条件可行。

新会话优先要求用户明确任务、目标对象、范围和授权。先报告已观察、推断、未知和下一步，再进入执行。普通问题和与逆向无关的任务不强行调用本入口。

回执中的未验证项保持未验证。包已安装不证明宿主加载、provider 可用或任务通过。自然语言未自动加载本入口时必须提示用户使用 `/skill:reverse-workflow` 或本 package 的 `reverse-workflow` prompt。
