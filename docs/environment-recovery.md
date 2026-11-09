# 给安装 AI 的公共整环境部署指南

任何人都可以把本仓库链接交给能够读取仓库、执行命令的 AI 助手，由它根据**目标电脑的 OS、架构、已有工具、实际路径和目标宿主**部署公开工具能力。先读 README、AGENTS 和本页，再使用下面链接中的既有安装路线。安装 AI 所在的宿主不自动等于要部署的目标宿主；账号由用户在目标机登录或配置。

## 可直接交给安装 AI

> 请部署本仓推荐环境。先读 README、AGENTS 和 docs/environment-recovery.md，检测目标电脑 OS/架构、已有工具版本与路径，确认目标是 Pi Web、Pi、Codex 或其他受支持 client。按电脑能力选择兼容项，复用合格安装，简要说明安装范围后在已有授权内连续推进。缺用户账户只问实际缺项；跳过不支持的可选组件并说明，不把跳过当已安装。保留已有配置，同名内容冲突先报告；不要照抄示例机器路径、全局改 PATH 或新增安装框架。完成后分别报告安装、宿主加载和代表性能力检查结果。

## 先确定机器与宿主

1. 检测 OS/架构、Python 3.11+、Git、uv、Node/npm 及其实际路径。按所选组件的公开 metadata、engines 和[兼容说明](compatibility.md)判断资格，不能只看命令存在。缺依赖时，在已有安装授权内按官方方式补齐；无权限或不支持则说明具体缺项，只暂停依赖它的部分。
2. 用户未指定宿主且需要网页界面时，推荐 [Pi Web](https://github.com/agegr/pi-web)；已有 Pi 或 Codex 则按实际目标选择。Pi Web 是独立网页宿主，普通 Pi CLI 不能替代其界面。核心安装器也支持 Claude Desktop，按 [README](../README.md) 的对应 client 路线使用。
3. Pi Web 按官方 README 选择公开稳定发行，安装前解析并记录精确版本、Node 要求及兼容性，再使用 npm 安装和 `pi-web` 启动；不要将某台机器的版本当作必装基线，也不要将所有依赖无条件升级到 latest。Codex 等宿主按各自官方方式准备。
4. 确定独立工具安装根、目标配置目录和成果项目目录。Pi 优先使用实际 `PI_CODING_AGENT_DIR`，默认通常为 `~/.pi/agent`；Codex 使用其实际配置根。Pi Web、Pi CLI 与安装计划必须指向同一目标配置。复用已有合格包，不覆盖用户修改，不用其他机器的 receipt 或路径代替本次 plan。

基础工具公开入口：[Python](https://www.python.org/downloads/)、[Git](https://git-scm.com/downloads)、[uv](https://docs.astral.sh/uv/getting-started/installation/)、[Node/npm](https://nodejs.org/en/download)。需要旁置 Node 时使用既有 `--node` 参数，不替换正在运行的宿主 Node。

## 推荐完整组合：按层安装

这是面向通用开发、逆向与实现任务的推荐能力组合；**推荐组合不等于安装器的单个 `all` 参数**。Pi 专属资源只安装到 Pi 目标，其他 client 使用对应原生集成，不能把 Pi profiles/extensions 强写进 Codex 配置。

| 层 | 推荐部署内容与方法 | 选择和依赖 |
|---|---|---|
| 宿主与模型 | 准备用户选择的 Pi Web/Pi 或其他受支持 client，在目标机配置模型登录 | 满足所选宿主的公开 OS/Node 要求；不复制其他人的账号配置 |
| 核心工作流 | reverse 原生路由 + REA MCP + Spec Kit，按[快速开始](quick-start.md)与[工作流手册](reverse-workflow-playbook.md)走 plan → apply → verify → accept | Python 安装器默认 `all` 仅包含这三件核心组件；成果项目另建，不在工具仓库 init |
| Pi 主/子代理 | [主 AGENTS 与 8 个 Worker 模板](pi-agent-profiles.md)，从仓库 resources 复制到目标 agent 目录 | 配置可用模型、保留已有 frontmatter/用户修改；动态派发，不要求每次启动全员 |
| 通用开发技能 | [五个第一方技能](pi-agent-skills.md)：范围控制、调试、验证、审查、轻量架构 | 放入目标宿主实际发现的 skills 根，检查同名冲突 |
| 设计能力 | [Impeccable](impeccable.md)、下方 UI/UX Pro Max 与 unslop 官方来源 | 推荐用于含 UI 的开发环境；纯后端目标可省略；各技能按任务选择，不绑定全套必用 |
| 访谈与领域建模 | 官方 grilling/domain-modeling，按需加 grill-me/grill-with-docs；Pi 使用[两个独立 wrappers](pi-grilling-wrappers.md) | 按[快速开始](quick-start.md#pi-grilling-伴随技能)安装官方输入再生成 wrappers，不修改官方正文，不作为每次任务审批门 |

核心安装器按 `components.json` 和官方元数据解析版本：REA/Spec Kit 新 plan 默认解析官方稳定包，reverse 优先正式 release；需要固定 Spec 时见[版本指南](version-pins.md)。当前公开分发为 installer core **0.7.0**、reverse **1.9.0**，可选 native Craft-Pi **0.1.0**，获取 helper **0.1.1**；这些是分发身份，不是个人电脑快照。main 提供当前教程与资源，冻结资产仍依正式 pins 取得，不修改旧 tag 或伪造回执。

## 按用途选择可选能力

| 能力 | 公开来源 / 安装路线 | 什么时候选择 |
|---|---|---|
| Craft 执行后端 | [精确 pin 获取](craft-acquisition.md)、[安装](craft-install.md)、[Windows x64 pin](../releases/windows-x64.json) | 现有 native 分发为 Windows x64；需明确选择、合格 bundle 和独立 Pi/Node。`all` 不包含；普通 Worker 默认，原 R46/Spec runner 只为合格批次 opt-in |
| shell-guard 与 Everything | [shell-guard 指南](shell-guard-install.md)，固定 `shell-guard-v0.3.0`；[Everything GUI](https://www.voidtools.com/downloads/) 与独立 [es CLI](https://www.voidtools.com/support/everything/command_line_interface/) | Pi 需要命令检查时显式选；`all` 不包含。Everything 按 Windows 支持范围准备实际 CLI/GUI 路径和索引，安装器不安装 Everything |
| 专业分析引擎 | REA 官方文档及对应分析工具指南；按实际任务准备 Java、Ghidra、JADX 所需引擎等 | 工具 schema 存在不代表引擎已安装；缺某引擎不阻塞其他适用工作流 |
| 桌面操作 / 网页搜索 | [pi-computer-use](https://github.com/injaneity/pi-computer-use)、[pi-web-access](https://github.com/nicobailon/pi-web-access) | Pi 需要桌面或网络能力时安装；按目标 OS/helper/权限和所选包版本准备，搜索 provider 按需配置 |
| 人格、会话回退、远程菜单 | 仓内[两个公开可选 Pi 扩展包](../resources/pi-local-packages/README.md)，复制后分别注册精确包目录 | 按用户用途启用；人格内容自行选择，远程访问默认不开启，需另配认证/网络；这些包不携带个人设置 |
| 重试策略 | [固定 retry-level.ts](https://github.com/gthubtom1/agent-plugins/blob/388def3a183ca805955e2bfbd224366b6e65e7f4/plugins/pi/retry-level/retry-level.ts)，保留同源许可，放入实际 Pi extensions 目录 | 用户需要该重试策略时选择并配置，不安装整个 hub 或退役的 continuity |
| 浏览器 / GitHub MCP | [Chrome DevTools MCP](https://github.com/ChromeDevTools/chrome-devtools-mcp)、[Playwright MCP](https://github.com/microsoft/playwright-mcp)、[GitHub MCP Server](https://github.com/github/github-mcp-server) | 按目标 client 的实际 schema 和官方 README 注册，分别检查浏览器/运行依赖和 GitHub 凭据；不是必须全装 |

Pi package 使用官方 `pi install npm:<包名>@<所选精确版本>`，或在 Pi Web Plugins UI 添加同一 package source；先查所选发行版本与要求，再安装，不编造 Python installer 参数。网页搜索可由 pi-web-access、兼容 provider 或宿主已有搜索工具提供，无需复刻特定人的私有 web-search MCP。已有浏览器/MCP 能完成目标时优先复用，避免重复注册。

不支持的 OS/架构、缺少对应工件或权限时跳过可选组件并列明原因，不借其他平台的通过记录。下载失败保留准确错误，不生成完成标记。远程网络设置、桌面权限和需要用户登录的步骤按目标机器实际处理。

## 外部技能的公开基线

完整复制技能及相对引用、scripts/data/reference 资源和同源许可，放入目标宿主实际 skills 根；同名不同内容先报告冲突。这些是可部署的官方基线，无需取得任何旧电脑副本。

- **UI/UX Pro Max**：[官方项目](https://github.com/nextlevelbuilder/ui-ux-pro-max-skill)，已核固定来源 `4f2dbb67e64969a9a30ab00742f2d55d66ddec2b` 的 [`.claude/skills/ui-ux-pro-max/`](https://github.com/nextlevelbuilder/ui-ux-pro-max-skill/tree/4f2dbb67e64969a9a30ab00742f2d55d66ddec2b/.claude/skills/ui-ux-pro-max)，MIT。按目标宿主发现规则复制到 `ui-ux-pro-max/`；Python 搜索脚本从实际技能路径调用，不假定 Claude 专用变量。也可按选定发行 README 使用官方 CLI 的对应宿主路线。
- **unslop**：[官方项目](https://github.com/heydamir/unslop)，已核固定来源 `97daa3eb365670ea3f87ed85356cbfcee18105a5` 的 [`skills/unslop/`](https://github.com/heydamir/unslop/tree/97daa3eb365670ea3f87ed85356cbfcee18105a5/skills/unslop)。保留 CC BY 4.0 LICENSE、Damir Sokolovsky（[@heydamir](https://x.com/heydamir)）署名与来源；截图/视频任务才按需准备 Playwright 浏览器与 ffmpeg。
- **grilling 系列**：[mattpocock/skills](https://github.com/mattpocock/skills)，按所选 ref 的官方安装说明与仓内[wrapper 指南](pi-grilling-wrappers.md)部署。记录 ref、保留许可，Pi wrapper 放独立目录，避免重复发现。
- **Impeccable**：仓内已包含官方 `cf7ea4a8fe56f3e186e9ffaca3124937e36e6430` Pi 构建，按[专页](impeccable.md)复制一个主技能和 LICENSE/NOTICE；native engine、CLI、hooks 按实际用途另外选择。

## 在目标电脑做最小验收

先运行核心组件既有 `verify`、`accept`，再按目标宿主文档 reload 或启动新会话，核对实际 agent/skills/Plugins/MCP 路径。选择适用的一个只读 MCP 请求、技能发现和小型代表任务，分别记录 **已安装、已加载、已运行**；静态复制和退出码不能替代宿主或业务检查。

只对选中的能力验证，不为一个文档或小功能重装整个环境。失败时说明具体缺项、跳过项与下一步；不能把“任意 AI 可按本指南部署”写成“任意 OS/硬件都已实测兼容”。本页提供公共部署路线，本次文档维护未实际在所有平台安装运行。
