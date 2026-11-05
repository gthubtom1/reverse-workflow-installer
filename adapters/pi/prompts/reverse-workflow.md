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

零基础操作员交互要求：每个重要阶段完成后，用大白话报告“本轮做了什么、目前确认了什么、目前还不知道什么、下一步建议”。下一步建议必须根据当前 Evidence 动态生成 2–5 个编号选项；每个选项包含白话动作、括号内专业术语、目的、影响、推荐项和预期结果。用户回复编号即可，用户不需要选择工具、填写技术参数或理解 REA/Ghidra/radare2。

当分析证据足以判断长期结果时，提供多个动态目标候选，并为每个候选附上可复制的 GOAL 文本。GOAL 文本由宿主的目标模式执行；入口只负责把当前 case、范围、约束、成功标准、unknown 和停止条件写清楚。候选必须根据当前证据生成，不能把源码恢复、行为等价重实现或二进制修改当成无条件可行。

用户任务：$ARGUMENTS
