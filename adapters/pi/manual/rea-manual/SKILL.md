---
name: rea-manual
description: 用户显式请求单独使用官方 REA 时读取原包说明。
disable-model-invocation: true
---

读取本目录相对路径 `../../receipt-location.json`，再读活动回执。由 `paths.rea_package` 定位原包，按需读取其 `skills` 目录中的官方 SKILL 与 references，保持原文。使用原 REA MCP；它只是在 reverse-skill 已选定 PRIMARY 后提供 bounded analysis backend，不是总路由、case owner、授权判定或 Evidence authority。读取仓库本身不等于获准执行脚本、连接目标或 bootstrap；任何执行仍需当前 case 的 scope/auth 边界和用户已披露的计划。
