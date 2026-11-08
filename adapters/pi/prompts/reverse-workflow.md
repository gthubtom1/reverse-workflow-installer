---
description: 按 receipt 进入 reverse 原生工作流，自动选择范围内的技术路线
argument-hint: "[任务]"
---
请进入已加载的 `reverse-workflow` skill，按 receipt → 原 RULES/MASTER-ROUTING → 原生 router → PRIMARY 处理任务。严格只读审查使用原 router 的 dry-run；不创建 case、不启动目标/provider。已有目标、范围和授权沿用，不重复请求确认。

用户只选择结果、对象、影响/授权范围或交付取舍。真实分歧时按原 `skills/ops/guided-operator-contract.md` 输出可复制的 GOAL-* / SCOPE-* / DELIVERY-* 选项；A/B/C 或数字只作为当前选项别名。不要让用户选择工具、provider、Static/Dynamic、脱壳、IAT、REA 或 Spec Kit。不能为阶段切换、换工具或事实核查要求回复“继续”。

重要阶段用白话报告：本轮做了什么、目前确认了什么、目前还不知道什么、当前阻碍和下一步。汇报不等于等待批准。技术方法在现有 scope、预算和 cleanup 内自动选择；范围外动作需要对应用户决定。

多代理协议：主代理是唯一的 route、scope、case、timeline、workitem 与 Evidence authority；Worker 不得自行创建或切换这些状态。`reverse-operator/cre` 是 bounded executor，只在 handoff 规定的范围内执行；`reverse-reviewer` 只读审查；`planner/scout` 只提供 advisory。`backend/UI implementation workers` 只有收到行为 Evidence handoff 后才能开始。

每次 worker handoff 必须带现有 `case_id`（仅 pre-case 只读规划/维护可为 `n/a` 并说明原因）、目标 identity/hash、`carry_forward_refs`、phase、一个 Evidence question、allowed actions、write scope、budget、cleanup 和 acceptance。涉及目标动作时，Worker 必须先读取 handoff 引用的现有 scope/授权；引用缺失或不可读时保持 blocked/unknown，不创建假 case，也不猜测。相同 target 的 heavy provider 必须 serialized；发生 timeout 或 provider failure 时，先取消并验证 cleanup 已完成，再记录结果并替换 worker/provider；cleanup 未验证成功时不得启动替代 provider。最终报告分开列出 `verified`、`partial`、`blocked`、`unknown`。这些是编排指导，不是执行沙箱；提示词不能授予权限、隔离能力或完成证据。

单个授权补丁或功能成功不能宣称整体完成：按原 authorization-coverage 契约逐组件核 Evidence 和回归。行为证据充分后才进入 reconstruction 和成果项目 Spec Kit；按 L0–L6 报告实际支持等级和未知项。Grilling 仅用于真实取舍或明确访谈，官方正文不改。

用户任务：$ARGUMENTS
