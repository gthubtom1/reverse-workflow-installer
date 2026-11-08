# 故障排查

| 现象 | 处理 |
|---|---|
| auto 没有证据/宿主证据冲突 | 明确 `--client pi` 或 `--client codex` 并指定配置根；不输出环境值 |
| Node engine 不满足 | 读 plan 的 node_engine；准备含 npm 的官方 Node 分发包，用 --node 指定可执行文件 |
| 找不到 npm-cli.js/semver | 当前安装器支持官方 Node 分发布局；不混用另一个 Node 的 PATH npm |
| GitHub 404 | reverse 的 latest-release 404 可按其既有策略解析 main；shell-guard 固定 tag 不回退 main。shell-guard 0.2.1 tag 不可用或身份不符时停止，不能改装旧版本 |
| GitHub 403/429/网络错误 | 安装器会停止，不把失败当作没有 release。若已登录 GitHub CLI，可在当前进程中设置 `GH_TOKEN` 后重新运行 plan，例如 PowerShell：`$env:GH_TOKEN = (gh auth token); python scripts/install.py plan ...`；token 只作为进程环境使用，不写入 receipt 或日志。没有认证时等待限流恢复；不会静默切换版本 |
| 配置或 reverse 漂移 | 旧计划不会覆盖新文件；审阅变化后重新 plan |
| 旧 receipt 仍含 project-continuity | 新计划不会加载它；更新只在 receipt 能定位唯一、未过滤的 Pi 包注册时移除该注册。缺少 root、重复/过滤/hub 注册或其他同名注册时，先清理并重新 plan；旧包目录会保留在历史版本目录 |
| 首次成果目录非空 | 使用独立空项目；不会用 --force 吞掉旧文件 |
| 官方 setup/init 接口不匹配 | 保留事务目录；按冻结版本核实际官方帮助/输出，再更新适配；不手改原包 |
| 复用版本不符 | 准备确切版本的新独立 prefix/tool dirs，或省略复用参数让安装器自行安装 |
| transaction.lock 残留 | 先确认没有活动安装/恢复进程，再删除该锁；按 journal 恢复中断事务 |
| shell-guard 缺文件/版本不符 | `--shell-guard-root` 必须指向独立 0.2.1 包目录，含 `index.ts`、`runtime.mjs`、所需 `src` 与精确 manifest；hub 根或旧版本包不能冒充目标 |
| shell-guard 重复/hub/过滤注册 | 审阅 plan 中的准确来源；开发迁移用 `--replace-shell-guard-root` 指定唯一旧包。先解决重复来源，安装器不静默去重或覆盖资源过滤 |
| shell-guard 迁移源/CLI 漂移 | 旧包内容、注册和显式 CLI hash 在 plan 中冻结；审阅真实变化后重新 plan。活动插件漂移不能靠新 plan 覆盖原 receipt 身份 |
| Everything 路径不合法/有用户配置 | `--everything-es` 与可选 `--everything-gui` 仅接受现存可执行文件的绝对路径；`--everything-autostart` 必须配 GUI。已有非本事务管理的不同路径配置会拒绝覆盖；其他 shellGuard 字段保留 |
| shell-guard verify 通过但未拦截/无法查询 | 完整重启实际 Pi/Pi Web，核对唯一插件包和工具加载。保留的禁用开关、宿主 `PI_SHELL_GUARD_ES` 覆盖、Everything 服务/索引均需单独检查；静态校验不会启用这些能力 |
| restore conflict | 已保留后续用户修改，逐项审阅冲突路径；不重复强制恢复 |
| verify 通过但宿主没有技能/工具 | 确认启动所用 agent/CODEX_HOME、项目工作目录和信任设置；Pi /reload，核实际资源与 MCP，不把静态通过当加载通过 |
| accept 的 REA 检查失败 | 先看 receipt 中的 Node、REA package 和环境；accept 使用官方 `rea mcp doctor`，不重复安装或修改官方包 |
| REA Android/资源工具提示 provider 缺失 | 这是目标域 provider 前提，不等于 MCP 断开；例如 Android 代码分析需要用户提供指定版本的 JADX MCP JAR，资源解码需要 Apktool launcher。安装器记录缺口，不下载、猜测或把普通 jadx JAR 冒充官方 provider |
| accept 的 reverse router 检查失败 | 先检查 reverse 工作副本 dirty/commit 和原生 master-route；不要在 installer 中复制第二套路由 |
| accept 的 Spec Kit init 检查失败 | 检查官方 specify 版本、client integration 和临时目录权限；不要把失败模板写入用户成果项目 |
| Pi 旧 REA 技能仍竞争 | 按宿主资源清单找准 SKILL 路径，重新 plan --exclude-rea-skill 精确排除；不编辑官方原文 |
| Pi 的 grilling 没出现或 wrapper 异常 | 核官方 `grilling` / `domain-modeling` 路径及独立 `--output-root`；按 [wrapper 指南](pi-grilling-wrappers.md) 运行生成/verify 并重载。旧 companion 漂移只报告、不改写；所有权冲突先核用户修改，不强制覆盖。 || grilling 提出了本来可以查证的事实问题 | 让它先暂停提问，要求 agent/subagent/REA 查文件、跑工具或比对字节；事实返回后再继续方案 frontier |
| 每个阶段都要求回复编号或“继续” | 汇报不是审批：当前目标、授权与预算内的事实检查和技术路线自动推进。沿用已答问题，不为选工具或形成结论重开 grilling；仅新目标取舍、授权或用户独有材料才暂停 |
| grilling 和 reverse 输出格式混在一起 | reverse 负责阶段报告并继续常规工作，只有真实决策才给 2–5 项编号选项；grilling 访谈使用 Q1/推荐答案；先完成访谈并确认共识，再发实施指令 |

官方命令非零时，安装器输出命令入口与退出码，不回显可能含凭据的任意 stdout/stderr。可按事务 plan 中的路径在同一隔离环境手动执行官方命令查看具体诊断。成功 setup 的完整 JSON 保存在事务目录，仅供本机查看。安装器的日志不是操作系统隔离沙箱；它只限定自己配置和包管理器的目录。

首次失败后没有活动 receipt 时，可用失败目录名运行 `restore --root <root> --transaction <ID>`。如果仍有旧活动 receipt，失败事务的即时回退已保留旧活动版本；先检查失败 journal 状态，再手工处理进程中断留下的冲突。不要为了让 installed 字段变绿而修改回执。
