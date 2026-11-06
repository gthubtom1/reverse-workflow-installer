# 兼容与验证状态

本次 Pi 入口包为 0.3.0；安装事务协议保持 0.2.0，以兼容已有回执。Python 3.11+ 标准库。最新稳定版本在每次 plan 按所选组件解析，不把研究基线永久固定成安装目标。

| 项目 | 已核官方文档/源码 | 本仓离线验证 | 宿主真实加载/任务 |
|---|---|---|---|
| REA 6.8.0 | 官方 npm 包、Node engines、setup pi/codex、skill=false 与 scoped env | 模拟官方输出的配置保留、身份/失败/漂移检查 | 本机 MCP 基础验收通过，工具目录完整；具体目标 provider 和实际行为分别验证 |
| Spec Kit 1.3.1 | 官方 `version --json` 与 `init`；pi/codex/claude integration 参数 | 模拟 init、扩展安装、更新保留项目文件 | 本机 Pi 临时 init 与版本检查通过；现有成果项目模板保留，不自动迁移 |
| 增强 reverse release/main | 固定用户仓库；RULES → 原 master-route → PRIMARY；已有薄 Codex 插件 | 本地工作副本只读身份检查、回执定位 | 专业路由/端到端任务由主流程验证 |
| Pi project-continuity 1.0.0 | 独立包 `@toti/pi-project-continuity`；固定 ref `project-continuity-v1.0.0`；实际入口依赖 runtime.mjs/store.mjs | 安装器 101 项测试通过；插件 80 项通过。覆盖旧安装 update、opt-out、精确 commit、hash/文件、注册过滤、漂移与 restore | Pi Web bundled SDK 1.5.0 与 CLI RPC 的真实生命周期通过 290 项断言（本地模拟模型）；外部模型三轮抽样通过：取消角色、保留另一约束、新会话恢复。实际 Web 页面、新会话状态命令、活动部署 verify 和隔离全新默认安装均通过；详见 [验收记录](project-continuity-verification.md) |
| Pi grilling 伴随技能 | 上游 `grilling`、`grill-me`、`grill-with-docs`、`domain-modeling`；只适配两个门面 | Node 离线夹具验证缺依赖时零写入、幂等、旧路径检出，以及适配前后两个官方技能字节不变 | 本地检查只证明结构与适配内容一致；上游来源真实性需另有基线，对话触发单独验证 |
| Pi | 当前安装版本文档的 skill-only package、资源精确排除、disable-model-invocation | manifest、配置与备份测试 | 实际加载、reload 后资源清单和显式 `/skill:reverse-workflow` 对话冒烟测试待验 |
| Codex | REA 官方 setup；Spec Kit 官方 skills integration；reverse 原插件路径契约 | 配置合并、全局/项目入口、子集扩展与升级反例 | 本机部署 verify 通过；Codex 新会话实际触发仍单独验收 |
| Claude Desktop | 显式 JSON MCP 配置、全局 skill 与项目 CLAUDE.md；不依赖 Claude CLI | provider 环境保留、子集/完整安装、入口升级与项目扩展反例 | 本机既有部署 verify 通过；Desktop 实际加载和新对话触发仍单独验收 |
| 本机 accept 验收 | 官方 REA doctor、原 router 临时路由、官方 Spec Kit 临时 init | 按 receipt 选定组件验收 | Pi 基础验收通过；REA 工具目录完整。JADX 深度代码 provider 尚缺用户提供的桥接 JAR，不能声明 APK 深度分析已就绪 |

本地已执行 Windows/Python 3.12 的 unittest，并增加 Node 门面适配夹具。2026-11-06 使用一个已配置模型做了有限抽样：在一次请求里连续读取两个自有文本夹具，中途没有要求“继续”；新运行/联网范围保持未执行并请求补充确认。此抽样仅覆盖交互边界，不证明完整逆向、复杂加壳目标、所有模型或浏览器/桌面 provider 已验证。

CI 配置提供 Windows/Ubuntu × Python 3.11/3.12/3.13，未触发的 job 不计通过。没有对 macOS 或其他宿主作实测声明。

project-continuity 的离线通过不单独证明发布 tag 或活动部署身份；发布使用最新 main 集成结果和 `project-continuity-v1.0.0` tag，本机安装由 receipt 固定 commit/tree hash。本地 `--continuity-root` 只证明所选目录与冻结 hash 一致。accept 不运行扩展，所以仍对插件加载与跨会话恢复保留 unverified；独立 SDK/RPC 和外部模型抽样证据不反向修改这个静态回执字段。首次模型抽样曾把两个独立决定合成一条；补明确状态说明后，相同提示复测通过，不能将一次复测扩大为所有模型的保证。

每次真实验收应在本机私有记录中补上：精确宿主版本、三个核心组件身份、Pi 伴随技能目录与适配状态（如使用 Pi）、运行时版本、加载路径/资源清单、MCP 握手和 tools/schema、provider 状态、原 router 输出、实际 Spec Kit 模板执行、代表任务结果、第二会话恢复和显式入口触发结果。receipt 中的 `unverified` 不会因文件存在、`verify` 通过或安装器退出 0 自动转为 passed。

不自动安装 Node/provider；不自动注册 Codex 插件；不自动升级已有项目模板。既有带特殊引号/数组表形式的 REA TOML 配置暂不支持自动编辑，明确拒绝。语义/等价/隔离验收均不属于安装静态检查。

官方接口变化时停止切换。维护者更新适配与有意义反例后才能扩大声明范围；不要静默改用较旧稳定版本或删除检查。
