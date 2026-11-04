---
name: reverse-workflow
description: 按用户授权使用已安装的 reverse-skill 专业工作流、REA 与 Spec Kit，进行分析、独立实现、验证、恢复、追版或知识维护。先定位本机回执，再交原生路由选择技能。
---

读取此技能目录相对路径 `../../receipt-location.json`，再读取其中 `receipt` 指向的本机 JSON。仅使用 `installed: true` 的活动回执；缺失时提示从安装仓库运行 verify，不猜测工具路径。

1. 从回执 `reverse.root` 定位原仓库，先读原 `RULES.md`。
2. 读取原 `skills/MASTER-ROUTING.md` 和回执 `reverse.master` 指向的总入口，保留用户原话、目标身份与范围。
3. 按原仓库的平台原生 `skills/scripts/master-route` 调用原 router，读取其选出的 PRIMARY 的原 `SKILL.md`。授权、case 和工具门槛依原 RULES 执行；本入口不另做分类。
4. 仅在 PRIMARY 委派后调用官方 REA MCP，保留完整 tools 与 unknown；官方说明在 `paths.rea_package` 内按需读取。Spec Kit 使用回执成果项目内实际生成的原生命令/技能，不在工具仓库 init。
5. 恢复与追版读取同一成果项目中的原 case、证据、Spec Kit feature/tasks。知识维护读取原仓库的中立维护指引。

回执中的未验证项保持未验证。包已安装不证明宿主加载、provider 可用或任务通过。自然语言未自动加载本入口时可显式 `/skill:reverse-workflow`。
