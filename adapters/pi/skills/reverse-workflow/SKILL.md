---
name: reverse-workflow
description: 针对明确逆向或安全分析目标的二进制、APK、前端签名、协议与 API 安全分析，以及复刻、行为对比、版本追踪和知识维护入口；按活动回执接续 reverse-skill 原生工作流。
---

普通开发、界面修改和一般问答按项目需要处理；此入口用于具有实际逆向或安全分析目标的任务。

1. 读取此技能目录相对路径 `../../receipt-location.json`，再读取其中 `receipt` 指向的本机 JSON。使用 `installed: true` 的活动安装。回执缺失时报告安装缺口，按安装仓库说明核验。
2. 从回执恢复 reverse.root、原 RULES.md、skills/MASTER-ROUTING.md 和 reverse.master，沿用已有目标、case、范围、用户决定和适用证据。
3. 使用原生 master-route 选择 PRIMARY，再按该专业技能处理。只读请求使用已支持的 dry-run，保持文件和目标状态只读；执行按已有授权进行。工具路径、参数和能力以活动安装为准。
4. 按实际交付接续分析、原件修改、接入或重新打包。独立复刻在行为证据和成功标准充分后进入 reconstruction，并在成果项目使用实际生成的 Spec Kit 资源。
5. 根据当前问题选择工具和协作方式。REA 是分析后端；目标、scope、Evidence 与完成结论仍由原 case 和专业工作流管理。运行活动遵循原范围、预算和资源清理要求。

关键结果、未知项和限制用简洁白话说明，完成声明对应实际验证范围。授权及功能门任务按原 `skills/ops/authorization-coverage.md` 契约核对本次范围内的证据；局部通过对应局部结论。

重要的目标、产品行为、范围和交付取舍由用户决定，常规技术方法在既定边界内自主处理。已有回答继续有效；Grilling 按明确访谈请求或真实决策需要使用官方技能。具体交互依据原 `skills/ops/guided-operator-contract.md` 与 `skills/ops/beginner-operator-guidance.md`。

本入口提供指令适配。安装记录、工具输出和真实业务验收分别核对；隔离能力、授权及完成证据以实际环境和原契约为准。
