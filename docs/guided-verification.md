# Installer guided verification

本记录对应 installer 与 Pi 入口包 0.6.0，事务协议保持 0.2.0。当前活动组件是 REA、Spec Kit、reverse，以及默认关闭的可选 shell-guard 0.2.2。

## 离线验证范围

- 新计划的 `all` 和核心组件子集不会解析、安装、注册或写入 project-continuity。
- 含 project-continuity 的旧 receipt 在更新时只进入退役兼容路径：receipt 能定位唯一、未过滤的 Pi `packages` 注册时，更新事务移除该注册；缺少 root/身份、重复注册、hub/父目录或其他同名注册时，plan 明确失败。
- 退役更新写入的新 receipt 不包含 project-continuity 字段，旧包目录保留在历史版本目录中，不会被新 settings 加载。
- REA、Spec Kit、reverse 的现有范围、入口、配置保留、项目模板和恢复逻辑继续按各自 receipt 组件执行。
- shell-guard 继续按独立包的 commit/tree/hash、Pi 注册和 Everything CLI/GUI 配置规则执行；它不依赖已移除的组件模块。

## 运行边界

离线 Python 测试使用模拟官方 CLI/HTTP 和临时目录，不下载、不运行真实 npm/uv/setup/init，也不接触用户 profile。Node grilling 门面测试单独验证其文件与 wrapper 契约。`verify` 只检查静态包身份、配置、receipt 和注册；Pi/Web 实际加载、shell 拦截、Everything 可用性、REA MCP 真实握手、reverse 代表任务与 Spec Kit 真实成果仍需按目标机器单独验收。

不要把旧 receipt 中的历史字段当作当前组件支持声明；更新后的活动 receipt 只记录新计划选择的组件。若旧 receipt 无法安全迁移，应先审阅并清理确切 Pi 注册，再重新生成 plan。不会用手改 receipt 伪造通过。
