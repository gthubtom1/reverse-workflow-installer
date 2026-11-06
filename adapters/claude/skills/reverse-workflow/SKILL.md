---
name: reverse-workflow
description: 逆向、二进制、APK、前端签名、协议、API 安全、复刻、行为对比、版本追踪或知识维护任务的统一入口；读取 receipt 后进入原 reverse-skill router。
---

这是 Claude 宿主中的 reverse-workflow 薄入口。它不创建第二套路由，也不替代 reverse-skill。

执行顺序：

1. 读取本机 receipt，确认 installed=true；
2. 从 receipt.reverse.root 读取原 RULES.md、skills/SKILL.md 和原生 router；
3. 运行原生 master-route 选择 PRIMARY；
4. 创建或恢复当前成果项目的 case/scope；
5. 只有 PRIMARY 委派后调用官方 REA MCP；
6. 每个重要阶段用大白话汇报进度，已授权范围和预算内的常规工作自动继续，不把汇报当审批；
7. 只有需要用户取舍结果、补充授权或独有材料时才提问；技术方法和工具选择由 agent 负责，编号选项仅用于真实决策；
8. Evidence 足够时生成多个动态目标候选和可复制 GOAL 文本；
9. 使用单重型 provider、资源预算和进程 cleanup 规则；
10. 不把字符串或静态线索写成已经确认的行为。

当前 receipt：{{RECEIPT}}
