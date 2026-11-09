# 格式化后：给安装 AI 的整环境恢复交接

把本仓库链接交给安装 AI，从这页开始即可逐层恢复工具能力和规则。**公开仓库不是整盘备份**：账号、模型密钥、私有服务连接、人格正文、项目/case/证据/数据库和会话历史必须由用户重新提供或从独立私人备份恢复。下面给出来源和已有安装路线，不新增一套安装器。

本页记录 2026-11-09 的 **Windows x64 参考环境**。先检测新电脑 OS/架构和各组件支持范围；其他平台的 core installer 可按既有兼容说明使用，但不自动继承本轮 Craft/桌面能力资格。网络下载、源文件存在、宿主发现和真实运行分别验收；本轮未格式化电脑或执行整环境重装。

## 给安装 AI 的一段话

> 请从本仓库当前 main 的 README、AGENTS 和 docs/environment-recovery.md 恢复环境。先检测 OS/架构、Python/Git/uv/Node 与实际 Pi Web agent/skills 目录，按下表顺序使用现有官方安装和仓库复制路线；工具仓库与成果项目分开。简要列出写入范围后，在我已有授权内连续完成，不为每个包重复问许可，不新增安装框架。不默认将所有组件升级到 latest，不绕过原有 plan、冲突和版本门。缺账号/密钥/私有连接由我填写，不猜值、不打印秘密。复制文件、资源发现、真实工具运行分别报告；已有文件内容不同先保护并报告。最后明确哪些能力就绪，哪些仍缺私人备份或登录，不把本页当成整机已验证保证。

## 格式化前另存的私人备份

由用户使用自己的私人或加密备份工具保存下面四类材料，不能提交公开仓库。仅持仓库链接且没有私人备份，无法找回凭据与历史；新机须重新解析目录，操作系统凭据仓可能依赖原系统密钥，需要重新登录，不能假定跨系统复制即可使用。

- 实际 `<agent-dir>` 中的 auth/models/settings/MCP 配置、自定义 provider 扩展（如可能含密钥的 `magpie.ts`）、personas/rules/sessions、自定义 packages/skills；备份过程不向公开报告输出内容。
- `~/.agents/skills` 中的本地定制副本及其引用、脚本和数据，不能只备一个 SKILL.md。
- 成果项目、cases、Evidence、Spec、数据库及任务所需外部数据，保留可重新关联的目录结构。
- 外部凭据仓（如 `~/.seep/secrets` 或系统 credential store）和用户需要保留的环境配置；原安装 receipt 可作为私人追溯材料，但不能复制到新机冒充安装成功。

## 恢复顺序与覆盖范围

`<agent-dir>` 优先取宿主实际 `PI_CODING_AGENT_DIR`，否则通常为 `~/.pi/agent`；通用技能根通常为 `~/.agents/skills`。Windows 使用当前用户目录，不照抄旧电脑盘符。Pi Web 与 CLI/安装计划必须使用同一 agent 目录。

| 顺序 / 层 | 来源与安装位置 | 人工必填或前置条件 | 本页能证明什么 / 仍需验证 |
|---|---|---|---|
| 1 基础工具 | [Python](https://www.python.org/downloads/) 3.11+、[Git](https://git-scm.com/downloads)、[uv](https://docs.astral.sh/uv/getting-started/installation/)、[Node/npm](https://nodejs.org/en/download)；按 OS 官方方式安装 | 用户选目录；Node 同时满足 Pi Web、REA 和可选组件各自 engines | Pi Web 要求 Node ≥22.19；不要只看命令存在就认定满足全部组件 |
| 2 宿主 Pi Web | [agegr/pi-web](https://github.com/agegr/pi-web)，本机参考 npm `@agegr/pi-web@0.15.0`，内含 Pi 1.5.0；见下方命令 | 浏览器；实际 agent 目录；首次账号配置 | 已核公开 npm 元数据与该版源码 README；普通 Pi CLI 不替代 Pi Web UI；新机启动仍需实测 |
| 3 模型与登录 | Pi Web Models / Pi 官方登录；自定义 provider 由用户重新配置 | 账号、API key、订阅、私有网关信息 | 仓库不含这些值；私有 `magpie.ts` provider 扩展不可公开复制，需要私人备份或重新实现其配置 |
| 4 核心多工作流 | 本仓 [快速开始](quick-start.md)、[使用手册](reverse-workflow-playbook.md)：reverse 原生 router + REA MCP + Spec Kit；独立安装根，成果项目另建 | root/agent/project 路径；Node、uv；按任务需要准备 Java/Ghidra/外部分析引擎 | 原 plan → apply → verify → accept 路线不变。参考 reverse 1.9.0 / REA 6.8.0 / Spec Kit 1.3.1；新 plan 的官方解析结果须重核，不能假定永远相同；Spec 可按[固定版本](version-pins.md)保留 1.3.1 |
| 5 主/子代理 | [resources/pi-agent-profiles](../resources/pi-agent-profiles/README.md) → `<agent-dir>/AGENTS.md` 和 `agents/*.md`，按[安装说明](pi-agent-profiles.md) | 用户选可用模型；保留已有 frontmatter/用户修改 | 包含主协调与合理委派/检索规则、8 个 Worker 模板；不是固定全员阵容，资源发现后再做适用任务检查 |
| 6 通用技能 | [五个第一方技能](pi-agent-skills.md) → 实际通用 skills 根 | 无模型/账号绑定；检查同名冲突 | 范围、调试、验证、审查和轻量架构原件在仓库；复制不等于模型已使用 |
| 7 设计与访谈技能 | [Impeccable](impeccable.md)、下方 UI/UX 与 unslop 固定来源、[grilling 与两个 Pi wrappers](pi-grilling-wrappers.md) | 外部来源网络；保留许可/相对资源；避免重复发现 | Impeccable 原件在仓；其余按上游及现有 wrapper 指南恢复，不把本机定制副本冒充上游原件 |
| 8 桌面与网页扩展 | `npm:@injaneity/pi-computer-use@0.5.1`、`npm:pi-web-access@0.46.0`；用 Pi 官方 package 安装或 Pi Web Plugins UI | 桌面会话/平台权限与 helper；搜索服务按需登录或配置 | 已核本机包版本和公开来源，原注册未 pin；这些不是宿主必然内置能力，基本搜索与高级 provider/视频能力分开检查 |
| 9 人格/回退与远程菜单 | [resources/pi-local-packages](../resources/pi-local-packages/README.md)：persona-rewind 0.3.1、remote-access 0.1.0 → `<agent-dir>/packages/`，分别注册精确目录 | 人格正文、远程认证与 Tailscale 账号另配 | 带本地补丁的纯源码已保留；不含旧工作台、用户规则、运行配置或密码；本轮未加载执行 |
| 10 重试扩展 | [固定 retry-level.ts](https://github.com/gthubtom1/agent-plugins/blob/388def3a183ca805955e2bfbd224366b6e65e7f4/plugins/pi/retry-level/retry-level.ts) → `<agent-dir>/extensions/retry-level.ts`，保留同源许可 | 用户原有退避/重试偏好另备；检查是否已有相同入口 | 公开文件 Git blob `3e9a4472daee2a96183d972c1bb753fa597ecf7f` 与本机相同；不恢复整个 hub 或已退役 continuity |
| 11 可选 shell-guard / Everything | [shell-guard 指南](shell-guard-install.md)，固定 tag `shell-guard-v0.3.0`；[Everything GUI](https://www.voidtools.com/downloads/) 与独立 [es CLI](https://www.voidtools.com/support/everything/command_line_interface/) | Windows 实际 es/GUI 路径、服务/索引；显式选择 shell-guard | `all` 不包含此扩展，安装器不安装 Everything；按既有 `--everything-es` / GUI 参数配置，不能把 GUI 当 CLI；查询与拦截仍需运行检查 |
| 12 可选 Craft | [精确 pin 获取](craft-acquisition.md) → [Craft 安装](craft-install.md)，[Windows x64 pin](../releases/windows-x64.json) | 显式选择、合格 bundle、独立 Pi/Node、实际 provider；短路径预算 | 默认 Worker；`all` 不包含 Craft。只有被原 R46/Spec runner 选择的合格批次才用，不自动接管路由或验收 |
| 13 其他 MCP | 当前清单有 chrome-devtools、playwright、github、web-search；REA 属核心安装器路线 | 前两者原为单独 stdio/Node 注册；确切包/版本/启动参数须私人备份或重新选定。后两者原连接信息需用户提供 | 不能从工具名字推断宿主内置或伪造通用 endpoint；本仓不含原连接信息，也不因装了网页/桌面扩展就声称全部 MCP 恢复 |
| 14 用户资料与项目 | 用户独立的私人备份；按新路径重新关联 | projects/cases/Evidence/DB、Spec 项目、sessions、人格/规则、定制技能与配置；账号重新登录 | 公开源码无法生成遗失历史；原安装 receipt/备份含机器路径甚至秘密，不作为新机成功回执重放 |

## 宿主和公开扩展：沿用官方命令

[Pi Web 0.15.0 来源 README](https://github.com/agegr/pi-web/blob/f130910abf662b506b2ef2f475fc21a2fe57badc/README.md)提供 npm 安装和 `pi-web` 启动。为恢复参考版本可用：

```text
npm install -g @agegr/pi-web@0.15.0
pi-web --help
pi-web --no-open
```

最后一条会启动服务；在新机获准启动时执行，默认仅绑定本机 `127.0.0.1:30141`，之后正常打开页面。未配置模型时到 Models 登录。这里的固定版本是参考，不承诺未来依赖解析或其他系统自动兼容；升级另作选择，不将 `@latest` 等同本机版本。单独 Pi CLI 若已存在，用 `pi install`；否则可在 Pi Web Plugins UI 添加相同 package source，不为注册扩展另换配置根。

```text
pi install npm:@injaneity/pi-computer-use@0.5.1
pi install npm:pi-web-access@0.46.0
```

来源：[pi-computer-use](https://github.com/injaneity/pi-computer-use)（MIT，Node ≥20.6）与 [pi-web-access](https://github.com/nicobailon/pi-web-access)（MIT，Node ≥22.19）。桌面扩展遵循该版平台 setup，不套用 macOS 权限步骤到 Windows；网页扩展按需配置搜索 provider，免费/无需 key 的路径也仍依赖网络服务可用。不要公开旧配置中的 key、cookies 或私有 URL。

核心发行身份保持 **installer I `70cf9c779ec0198eb725b864af868ee88bcfbce9` (0.7.0)**、**Craft C `010e2e323f912806f3fc3f2b17b1f9f06c29c944` (0.1.0)**、**reverse R `7cc3109bf14a570c9c852dc76cce05fff424e88c` (1.9.0)**、**acquisition A `d29b1fe5b207cb36faf3df9533dad4faf23e1e72` (0.1.1)**。当前 main 提供新教程和 profile/技能资源；资产仍按正式 pin/版本取得。不要移动旧 tag、改 receipt 或用 latest 覆盖冻结身份。本页不是新 release；核心 installer 不负责安装上表所有层。

## 外部技能：固定来源获取，保留完整目录

- **UI/UX Pro Max**：[官方项目](https://github.com/nextlevelbuilder/ui-ux-pro-max-skill)，参考 commit `4f2dbb67e64969a9a30ab00742f2d55d66ddec2b`，完整复制 [`.claude/skills/ui-ux-pro-max/`](https://github.com/nextlevelbuilder/ui-ux-pro-max-skill/tree/4f2dbb67e64969a9a30ab00742f2d55d66ddec2b/.claude/skills/ui-ux-pro-max) 到实际通用 skills 根的 `ui-ux-pro-max/`，连同同 commit MIT LICENSE。必须保留 scripts/data/references；Python 搜索脚本按实际技能绝对路径调用，Pi 不假定 Claude 专用变量。上游另有 CLI universal 安装路线，按选定版本 README 使用，不盲装全部助手或 latest。本机副本可能有适配，未建立与该 commit 字节相同的证明；需要原样恢复定制时另备其完整目录。
- **unslop**：[官方项目](https://github.com/heydamir/unslop)，参考 commit `97daa3eb365670ea3f87ed85356cbfcee18105a5`，完整复制 [`skills/unslop/`](https://github.com/heydamir/unslop/tree/97daa3eb365670ea3f87ed85356cbfcee18105a5/skills/unslop) 到 `<agent-dir>/skills/unslop/`，保留同 commit LICENSE、引用和脚本；CC BY 4.0，保留 Damir Sokolovsky（[@heydamir](https://x.com/heydamir)）署名与来源链接。此固定上游不等于本机旧版/定制副本。截图/视频能力另需 Playwright 浏览器及 ffmpeg；只恢复技能文本不必先安装这些或运行远程脚本。
- **grilling / domain-modeling / grill-me / grill-with-docs**：来自 [mattpocock/skills](https://github.com/mattpocock/skills)。按[快速开始](quick-start.md#pi-grilling-伴随技能)恢复两个核心；如需原四个命令，按同一上游选定 ref 的 README/技能目录安装 companions。记录所选 ref 并保留其许可，勿将“当前上游”声称为旧本机完全相同。两个核心齐备后，运行仓内既有 adapter/verifier 生成独立 `pi-grill-me`、`pi-grill-with-docs`；见 [wrapper 指南](pi-grilling-wrappers.md)。不要把 wrapper 写进官方正文，也不把访谈变成每次任务必经审批。
- **Impeccable**：仓内已固定官方 commit `cf7ea4a8fe56f3e186e9ffaca3124937e36e6430` 的完整 Pi 构建，按[专页](impeccable.md)复制一个主技能及 LICENSE/NOTICE；CLI、hooks、native engine 等按需启用，不能因文件复制就认定运行完成。

以上都是来源选择与恢复步骤；动态技能策略继续由当前主预设和任务决定，不要求每次研究或设计加载固定全套技能。

## 加载和最小验收

完成获授权安装后正常 `/reload` 或新建会话，核对实际上下文/技能/Agents/Plugins 的发现路径，不能用“文件已写入”代替加载。主预设的检索规则会结合本地实现、官方文档、真实 issues/论坛经验，并要求本地验证；它不会让简单修复强制联网，也不自动安装浏览器。

核心组件运行既有 `verify`、`accept`；它们不替代宿主、个人扩展、Everything、其他 MCP 或模型认证验收。每个选中能力用一个合适的小型检查即可：例如确认一个只读 MCP 请求、一次已有本地文件查询、技能发现与主预设路径。模型任务、远程访问、浏览器控制仅在相应授权和登录条件满足后进行；失败报告准确缺口，不凭标记文件声称全环境已恢复。只有配置规则变化时按宿主 `/reload` 加载即可；程序/扩展要求的首次启动或重启按其文档另办。
