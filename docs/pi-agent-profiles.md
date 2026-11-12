# Pi profile templates 安装说明

这组可选模板提供简短的用户级工作原则，以及 `subagent`、`reverse-operator`、`reverse-reviewer` 三个 profile。主对话按任务选择直接处理或协作，模板不规定团队组成或固定阶段。Pi Web 的内置代理和用户已有代理保持可用；本包不安装模型账号、凭据、技能包或 MCP 服务。

## 目标目录

优先使用当前 Pi 进程设置的 PI_CODING_AGENT_DIR。如果该变量没有设置，Windows 默认目录通常是：

%USERPROFILE%\.pi\agent\

不要把某台电脑的实际用户路径写死，例如不要写成 C:\Users\<用户名>\.pi\agent。另一台电脑的用户名、用户目录和盘符可能不同。Pi Web 必须和 Pi CLI 使用同一个 agent 目录；如果 Pi Web 已经运行，安装后需要 reload 或重启，再新建会话验证。

## 给 AI 安装代理的操作

1. 先读取本说明、当前仓库的 AGENTS.md，以及目标电脑的 Pi Web/Pi 配置。
2. 解析目标 agent 目录：优先读取 PI_CODING_AGENT_DIR；否则使用当前用户的 %USERPROFILE%\.pi\agent\。
3. 只创建目标目录及其 agents 子目录。
4. 从仓库的 [resources/pi-agent-profiles/](../resources/pi-agent-profiles/README.md) 复制 `AGENTS.md`，并仅复制 `agents/subagent.md`、`agents/reverse-operator.md`、`agents/reverse-reviewer.md` 到对应目标；本说明位于 `docs/`，不是模板源目录。
5. 如果目标文件不存在，可以创建。
6. 如果目标文件已经存在且字节相同，保持不变。
7. 如果目标文件存在但内容不同，先报告冲突，不静默覆盖用户修改；候选内容仅放在 profile 发现路径外。升级原 8 模板版本时，用可用回收站机制将 `ui-implementer.md`、`ui-reviewer.md`、`backend-worker.md`、`requirements-planner.md`、`scout.md` 这 5 个已退役文件精确移出发现路径，不留下 `.new` 或 disabled Markdown 副本。其他自定义 profiles 保留并报告，不按数量或通配符删除；若旧文件是链接，先核查目标。
8. 不复制 auth.json、models.json、settings.json、session、memory、日志或任何凭据。
9. 安装后 reload 或重启 Pi Web，并创建新会话。
10. 在 Pi Web 的 Agents 列表中确认本仓的 `subagent`、`reverse-operator`、`reverse-reviewer` 三项已出现，退役五项不再出现；其他用户自定义项单独报告。再运行一个只读分派确认实际使用了正确 profile。

可选 Craft 执行后端使用独立的按需 reconstruction-execution skill、builder instructions 和 bundle entry，不新增控制 profile，不自动部署或接管本页的人工 profiles/AGENTS。其安装恢复仅管理新包资源和精确注册，见 [Craft 指南](craft-install.md)。

## 模型和技能

模板不固定 provider、model 或 thinking level。目标电脑上的用户在 Pi Web 中选择实际可用模型。

load_skills: true 表示允许 profile 使用当前可发现的技能；它不是某个固定技能名称的绑定。技能是否实际使用由任务和技能描述决定。

`subagent` 用于通用分派任务，两个 reverse profile 分别提供逆向执行和只读审查能力。根据任务及宿主实际暴露的能力选择代理和技能；普通工作可由主对话直接完成。模型、工具权限和既有开关由目标用户决定，模板正文精简不等于更改这些配置。

reverse-workflow 是专业任务入口，原生 PRIMARY、scope 和 Evidence 仍按原契约管理。原件修改、接入、重新打包与独立复刻按实际交付接续；Spec implement/converge 用于适用的独立实现流程。宿主按需要承担原生职责，不要求注册同名角色。

## 验收边界

文件复制成功只证明模板已写入目标目录。还必须分别验证：

- Pi Web 是否读取了同一个 agent 目录；
- reload 或重启后 profiles 是否重新出现；
- 新会话是否能选择并运行 profile；
- 目标机器选择的 provider、model、Skills、Extensions 和 MCP 是否实际可用。

模板目录不包含模型账号、外部技能下载或本机安装路径。
