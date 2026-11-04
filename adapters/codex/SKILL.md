---
name: reverse-workflow
description: 从本机安装回执定位 reverse-skill 原仓库及现有 Codex 薄插件，处理用户授权的分析、独立实现、验证、恢复、追版与知识维护。
---

读取本机回执 `{{RECEIPT}}`，要求 `installed: true`。从 `reverse.root` 得到用户增强仓库的显式本地路径；先读其原 `RULES.md`。

优先读取回执 `reverse.codex_plugin` 指向目录内的 `skills/reverse-skill-router/SKILL.md`，把 `reverse.root` 作为明确提供的本地仓库路径传入。该插件的 manifest 与原文保持不变；无需猜测或执行插件注册命令。

如该版本没有原生薄插件，读取原 `skills/MASTER-ROUTING.md` 与回执 `reverse.master`，使用原生 `skills/scripts/master-route` 决定 PRIMARY，再读取其原 SKILL。只按原 RULES 建立 scope 与 case；不要在此入口另行路由。

REA 由官方 setup 在回执的 Codex 配置根注册，保留全部工具。Spec Kit 使用当前成果项目中官方 `--integration codex` 实际生成的原生技能。恢复、追版、知识维护均继续原 reverse 中立流程。报告回执中的未验证状态，不把安装视为任务通过。
