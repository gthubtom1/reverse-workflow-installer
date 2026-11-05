---
description: 显式进入 reverse 原生工作流并按 receipt 定位已安装组件
argument-hint: "[任务]"
---
请先进入已加载的 `reverse-workflow` skill，再处理下面的任务。不要绕过入口直接开始普通命令。

工作要求：
1. 读取本机 receipt，确认安装状态和组件范围；
2. 读取 reverse-skill 原 `RULES.md`、`MASTER-ROUTING.md` 和原生 router；
3. 由原生 router 选择 PRIMARY，再读取 PRIMARY 的 SKILL.md；
4. 保留用户原话、目标身份、范围、unknown 和证据链；
5. 只有在 PRIMARY 委派后才按原流程调用 REA MCP；需要独立项目时使用成果项目中的 Spec Kit 资源。

用户任务：$ARGUMENTS
