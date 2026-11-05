# 兼容与验证状态

安装器 0.2.0；Python 3.11+ 标准库。最新稳定版本在每次 plan 解析，不把研究基线永久固定成安装目标。

| 项目 | 已核官方文档/源码 | 本仓离线验证 | 宿主真实加载/任务 |
|---|---|---|---|
| REA 6.8.0 | 官方 npm 包、Node engines、setup pi/codex、skill=false 与 scoped env | 模拟官方输出的保留配置、身份/失败/漂移检查 | 未由本仓执行 |
| Spec Kit 1.3.0 | 随包模板；init integration pi/codex、script py、non-interactive；version --json | 模拟 init 和更新保留项目文件 | 未由本仓执行 |
| 增强 reverse release/main | 固定用户仓库；RULES → 原 master-route → PRIMARY；已有薄 Codex 插件 | 本地工作副本只读身份检查、回执定位 | 专业路由/端到端任务由主流程验证 |
| Pi grilling 伴随技能 | 上游官方 `grilling`、`grill-me`、`grill-with-docs`、`domain-modeling`；Pi 门面适配脚本 | 官方技能逐个安装、Pi 门面幂等改写、官方 `grilling` 正文不变 | 当前电脑已部署；新会话中的模型级触发和事实委派仍需真实对话验收 |
| Pi | 当前安装版本文档的 skill-only package、资源精确排除、disable-model-invocation | manifest、配置与备份测试 | 实际加载、reload 后资源清单和显式 `/skill:reverse-workflow` 对话冒烟测试待验 |
| Codex | REA 官方 setup；Spec Kit 官方 skills integration；reverse 原插件路径契约 | 配置合并与项目薄技能夹具测试 | 实际 Codex 版本、项目 skill 发现和新会话触发待验 |
| 本机 accept 验收 | 官方 REA doctor、原 router 临时路由、官方 Spec Kit 临时 init | 当前 receipt 选定组件的真实本机验收 | 未运行即保持未验证 |

本地已执行 Windows/Python 3.12 的 unittest。CI 配置提供 Windows/Ubuntu × Python 3.11/3.12/3.13，未触发的 job 不计通过。没有对 macOS 或其他宿主作实测声明。

每次真实验收应在本机私有记录中补上：精确宿主版本、三个组件身份、运行时版本、加载路径/资源清单、MCP 握手和 tools/schema、provider 状态、原 router 输出、实际 Spec Kit 模板执行、代表任务结果、第二会话恢复和显式入口触发结果。receipt 中的 `unverified` 不会因文件存在、`verify` 通过或安装器退出 0 自动转为 passed。

不自动安装 Node/provider；不自动注册 Codex 插件；不自动升级已有项目模板。既有带特殊引号/数组表形式的 REA TOML 配置暂不支持自动编辑，明确拒绝。语义/等价/隔离验收均不属于安装静态检查。

官方接口变化时停止切换。维护者更新适配与有意义反例后才能扩大声明范围；不要静默改用较旧稳定版本或删除检查。
