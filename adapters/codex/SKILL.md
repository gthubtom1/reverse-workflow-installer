---
name: reverse-workflow
description: 针对明确逆向或安全分析目标的二进制、APK、前端签名、协议与 API 安全分析，以及复刻、行为对比、版本追踪和知识维护入口；按活动回执接续 reverse-skill 原生工作流。
---

这是 Codex 全局安装中的统一入口。遇到上述专业任务时先进入本 skill，不要直接绕过它执行普通命令。

读取本机回执 `{{RECEIPT}}`，要求 `installed: true`。从 `reverse.root` 得到用户增强仓库的显式本地路径；先读其原 `RULES.md`。

优先读取回执 `reverse.codex_plugin` 指向目录内的 `skills/reverse-skill-router/SKILL.md`，把 `reverse.root` 作为明确提供的本地仓库路径传入。该插件的 manifest 与原文保持不变；无需猜测或执行插件注册命令。

如该版本没有原生薄插件，读取原 `skills/MASTER-ROUTING.md` 与回执 `reverse.master`，使用原生 `skills/scripts/master-route` 决定 PRIMARY，再读取其原 SKILL。只按原 RULES 建立 scope 与 case；不要在此入口另行路由。

只读请求使用原 router 的 `-DryRun` / `--dry-run`，保持目标和文件只读。沿用已有用户决定，在授权范围内自主选择方法与协作；重要目标、范围和交付取舍依据原 `skills/ops/guided-operator-contract.md` 与用户澄清。授权及功能门任务按原 `skills/ops/authorization-coverage.md` 核对本次范围内的证据，运行遵循原预算和资源清理要求。

原始 case 与 Evidence 保持权威。分析、原件修改、接入和重新打包按实际交付接续；独立复刻在行为证据与成功标准充分后进入 reconstruction/Spec Kit。简洁说明结果、未知项和实际验证范围。

REA 由官方 setup 在回执的 Codex 配置根注册，保留全部工具。Spec Kit CLI 由全局安装提供；只有用户明确选择独立成果项目时，才使用该项目中官方 `--integration codex` 实际生成的原生技能。恢复、追版、知识维护均继续原 reverse 中立流程。报告回执中的未验证状态，不把安装视为任务通过。

组合任务的入口与记录归属只有这一条原链。PRIMARY 可按实际问题选择 REA 或 Craft 的有限工具操作；保留工具原件、ID与限制，作为原 case 的支持材料。不要因上游 Craft 工具可见而另开其调查、brief/plan/finding/handoff，覆盖原 Evidence、Spec tasks 或自动调用 rebuild_start。上游广域 Skill 的宿主禁用记录由安装器 plan/receipt/verify 管理；遇到新启用的竞争入口先报告配置缺口。Codex 上游 Craft 仅安装为工具伴随组件时，不具备原 R46 受控执行后端资格；实现批次仍交原 Spec runner 和默认 Worker，只有实际后端合格并被 runner 明确选择后才替换该批写者。
