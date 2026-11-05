# 故障排查

| 现象 | 处理 |
|---|---|
| auto 没有证据/宿主证据冲突 | 明确 `--client pi` 或 `--client codex` 并指定配置根；不输出环境值 |
| Node engine 不满足 | 读 plan 的 node_engine；准备含 npm 的官方 Node 分发包，用 --node 指定可执行文件 |
| 找不到 npm-cli.js/semver | 当前安装器支持官方 Node 分发布局；不混用另一个 Node 的 PATH npm |
| GitHub 404 | 增强仓库可能尚无 main 或权限不可见；release 404 可回退解析 main，main 404 会明确失败 |
| GitHub 403/429/网络错误 | 安装器会停止，不把失败当作没有 release。若已登录 GitHub CLI，可在当前进程中设置 `GH_TOKEN` 后重新运行 plan，例如 PowerShell：`$env:GH_TOKEN = (gh auth token); python scripts/install.py plan ...`；token 只作为进程环境使用，不写入 receipt 或日志。没有认证时等待限流恢复；不会静默切换版本 |
| 配置或 reverse 漂移 | 旧计划不会覆盖新文件；审阅变化后重新 plan |
| 首次成果目录非空 | 使用独立空项目；不会用 --force 吞掉旧文件 |
| 官方 setup/init 接口不匹配 | 保留事务目录；按冻结版本核实际官方帮助/输出，再更新适配；不手改原包 |
| 复用版本不符 | 准备确切版本的新独立 prefix/tool dirs，或省略复用参数让安装器自行安装 |
| transaction.lock 残留 | 先确认没有活动安装/恢复进程，再删除该锁；按 journal 恢复中断事务 |
| restore conflict | 已保留后续用户修改，逐项审阅冲突路径；不重复强制恢复 |
| verify 通过但宿主没有技能/工具 | 确认启动所用 agent/CODEX_HOME、项目工作目录和信任设置；Pi /reload，核实际资源与 MCP，不把静态通过当加载通过 |
| accept 的 REA 检查失败 | 先看 receipt 中的 Node、REA package 和环境；accept 使用官方 `rea mcp doctor`，不重复安装或修改官方包 |
| REA Android/资源工具提示 provider 缺失 | 这是目标域 provider 前提，不等于 MCP 断开；例如 Android 代码分析需要用户提供指定版本的 JADX MCP JAR，资源解码需要 Apktool launcher。安装器记录缺口，不下载、猜测或把普通 jadx JAR 冒充官方 provider |
| accept 的 reverse router 检查失败 | 先检查 reverse 工作副本 dirty/commit 和原生 master-route；不要在 installer 中复制第二套路由 |
| accept 的 Spec Kit init 检查失败 | 检查官方 specify 版本、client integration 和临时目录权限；不要把失败模板写入用户成果项目 |
| Pi 旧 REA 技能仍竞争 | 按宿主资源清单找准 SKILL 路径，重新 plan --exclude-rea-skill 精确排除；不编辑官方原文 |

官方命令非零时，安装器输出命令入口与退出码，不回显可能含凭据的任意 stdout/stderr。可按事务 plan 中的路径在同一隔离环境手动执行官方命令查看具体诊断。成功 setup 的完整 JSON 保存在事务目录，仅供本机查看。安装器的日志不是操作系统隔离沙箱；它只限定自己配置和包管理器的目录。

首次失败后没有活动 receipt 时，可用失败目录名运行 `restore --root <root> --transaction <ID>`。如果仍有旧活动 receipt，失败事务的即时回退已保留旧活动版本；先检查失败 journal 状态，再手工处理进程中断留下的冲突。不要为了让 installed 字段变绿而修改回执。
