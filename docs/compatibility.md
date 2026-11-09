# 兼容与验证状态

本次安装器与 Pi 入口包为 0.6.1；安装事务协议保持 0.2.0，以兼容已有回执。Python 3.11+ 标准库。最新稳定版本在每次 plan 按所选组件解析，不把研究基线永久固定成安装目标。shell-guard 当前冻结目标为已发布的 0.3.0。

| 项目 | 已核官方文档/源码 | 本仓离线验证 | 宿主真实加载/任务 |
|---|---|---|---|
| REA 6.8.0 | 官方 npm 包、Node engines、setup pi/codex、skill=false 与 scoped env | 模拟官方输出的配置保留、身份/失败/漂移检查 | 本机 MCP 基础验收通过，工具目录完整；具体目标 provider 和实际行为分别验证 |
| Spec Kit 1.3.1 | 官方 `version --json` 与 `init`；pi/codex/claude integration 参数 | 模拟 init、扩展安装、更新保留项目文件 | 本机 Pi 临时 init 与版本检查通过；现有成果项目模板保留，不自动迁移 |
| 增强 reverse release/main | 固定用户仓库；RULES → 原 master-route → PRIMARY；已有薄 Codex 插件 | 本地工作副本只读身份检查、回执定位 | 专业路由/端到端任务由主流程验证 |
| 旧 project-continuity receipt | 新计划不再解析、加载或写入该组件；更新在 receipt 能唯一识别 Pi 包注册时移除注册，否则明确失败。旧包目录保留为历史缓存，不作为活动配置 | 新增离线回归覆盖唯一注册、过滤注册和重复注册 | 不代表插件仍受支持；需单独验证更新后的宿主加载 |
| Pi shell-guard 0.3.0 | 独立 `@toti/pi-shell-guard`、唯一 `./index.ts`；使用 `src/readonly.mjs` AST/Node-helper 与随包固定的 ISC `unbash` 文件，不在目标机安装 npm 依赖。目标 `shell-guard-v0.3.0` 已发布并固定 commit/tree | 安装器离线回归覆盖默认关闭、Pi 限定、本地/远程身份冻结、旧回执更新、配置保留、准确迁移、重复/hub 拒绝、漂移和事务回退；插件107项测试、258项惰性Bash的实际SDK事件检查及Ubuntu/Windows CI通过 | 本次没有部署或修改真实 profile；宿主加载、拦截事件与 Everything 可用性未验证。常见只读 `for`/`if`/`test`/`echo`/`printf` 允许、单个字面项目内 `rm` 移到 TEMP；硬保护和 Everything 不变，且不弹确认窗口。不是沙箱；详见 [安装说明](shell-guard-install.md) |
| Pi 可选 Craft 本地 bundle | 固定 Craft base 0326；独立 contract/min_reader/capabilities、全量工件/hash、显式 Pi Node/CLI/version、相对 bundle 入口；默认关闭且要求显式 reverse/Spec Kit | 离线真实文件行为覆盖精确复制、漂移、缺文件、重复注册、旧 receipt、并列更新、失败/重试、pending、用户编辑与 receipt 最后恢复；使用 toy 工件，未构建产品包 | RPC/policy/owner 联调、真实 Pi/provider、宿主加载、取消及业务切片未验证；远程兼容资产未发布，公共换机分发 unsupported；见 [指南](craft-install.md) |
| Pi grilling 伴随技能 | 官方 `grilling`、`domain-modeling`、`grill-me`、`grill-with-docs` 保持原文；installer 只生成 `pi-grill-me`、`pi-grill-with-docs` wrapper | Node 离线夹具验证缺依赖时零写入、幂等、官方文件不变、wrapper 路径和引用一致 | 本地检查只证明结构与适配内容一致；上游来源真实性需另有基线，对话触发单独验证 |
| Pi | 当前安装版本文档的 skill-only package、资源精确排除、disable-model-invocation | manifest、配置与备份测试 | 实际加载、reload 后资源清单和显式 `/skill:reverse-workflow` 对话冒烟测试待验 |
| Codex | REA 官方 setup；Spec Kit 官方 skills integration；reverse 原插件路径契约 | 配置合并、全局/项目入口、子集扩展与升级反例 | 本机部署 verify 通过；Codex 新会话实际触发仍单独验收 |
| Claude Desktop | 显式 JSON MCP 配置、全局 skill 与项目 CLAUDE.md；不依赖 Claude CLI | provider 环境保留、子集/完整安装、入口升级与项目扩展反例 | 本机既有部署 verify 通过；Desktop 实际加载和新对话触发仍单独验收 |
| 本机 accept 验收 | 官方 REA doctor、原 router 临时路由、官方 Spec Kit 临时 init | 按 receipt 选定组件验收 | Pi 基础验收通过；REA 工具目录完整。JADX 深度代码 provider 尚缺用户提供的桥接 JAR，不能声明 APK 深度分析已就绪 |

本地已执行 Windows/Python 3.12 的 unittest，并增加 Node 门面适配夹具。2026-11-06 使用一个已配置模型做了有限抽样：在一次请求里连续读取两个自有文本夹具，中途没有要求“继续”；新运行/联网范围保持未执行并请求补充确认。此抽样仅覆盖交互边界，不证明完整逆向、复杂加壳目标、所有模型或浏览器/桌面 provider 已验证。

shell-guard 的远程 plan 要求 tag 解析出精确 commit 和 Git tree，应用后记录独立包文件 hash；本地包只证明所选目录与冻结内容一致，不认证它等于远程发行。`verify` 不读取宿主进程的 `PI_SHELL_GUARD_ES` 覆盖，也不把保留的禁用开关当成已启用；`accept` 将运行效果明确留作未验证。发布、真实加载与运行时的验收由插件主流程补齐。

CI 配置提供 Windows/Ubuntu × Python 3.11/3.12/3.13，未触发的 job 不计通过。没有对 macOS 或其他宿主作实测声明。

旧版本的 project-continuity 说明和验证材料已从 installer 交付中移除。`guided-verification.md` 仅保留 installer 当前组合的可复现验证边界；它不再作为 continuity 插件的支持声明。

每次真实验收应在本机私有记录中补上：精确宿主版本、三个核心组件身份、Pi 伴随技能目录与适配状态（如使用 Pi）、运行时版本、加载路径/资源清单、MCP 握手和 tools/schema、provider 状态、原 router 输出、实际 Spec Kit 模板执行、代表任务结果、第二会话恢复和显式入口触发结果。receipt 中的 `unverified` 不会因文件存在、`verify` 通过或安装器退出 0 自动转为 passed。

不自动安装 Node/provider；不自动注册 Codex 插件；不自动升级已有项目模板。既有带特殊引号/数组表形式的 REA TOML 配置暂不支持自动编辑，明确拒绝。语义/等价/隔离验收均不属于安装静态检查。

官方接口变化时停止切换。维护者更新适配与有意义反例后才能扩大声明范围；不要静默改用较旧稳定版本或删除检查。
