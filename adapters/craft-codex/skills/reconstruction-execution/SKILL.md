---
name: reconstruction-execution
description: 仅在原 R46/Spec implement runner 已接收研究、选定明确任务并选择已安装 Codex Craft 后端后，执行该批受控 build/check/refine 与结果回传。
---

这是原复刻流程的实现阶段资源，安装在 receipt 的 `craft.resources`，不注册新的全局入口。不要从普通分析请求、上游 Craft 工具可见或历史任务启动本资源。

读取同目录 [执行 reference](references/execution.md) 及实际 bundle 的 entry protocol。确认活动 receipt 的 `scope.client=codex`、`craft`、原 reverse Codex 合同与全部冻结文件；通过受管 entry 检查后，按原 runner 接收的真实 handoff 验证、准备和运行。入口、分析、规格和最后接收继续由原 reverse/PRIMARY/Spec runner 负责。

实际执行是 `accepted research → validate/prepare → 单个 Codex Builder → build/check/refine → typed return → 原 runner/lead 接收`。缺证回原 PRIMARY/REA，规格问题回原 runner，权限或预算能力缺失返回 unsupported。cleanup 未证实时保留 lease，阻止新写者。不要调用上游独立 rebuild 流程、另派 Worker 或更改原 tasks/检查预期。

安装、协议 fixture、真实模型执行与业务验收分别报告；不得以 entry check、TurnDone、exit 0 或工具目录正常替代实际检查与独立接收。
