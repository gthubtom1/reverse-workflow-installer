# Project Continuity 1.1.0 验收记录

日期：2026-11-06。插件发布 tag 为 [`project-continuity-v1.1.0`](https://github.com/gthubtom1/agent-plugins/releases/tag/project-continuity-v1.1.0)，提交 `11089f8549200a486c5b473e985262450ce11f0d`，插件 tree hash 由 installer receipt 冻结。安装器最新发布为 [`v0.3.3`](https://github.com/gthubtom1/reverse-workflow-installer/releases/tag/v0.3.3)（包含 v0.3.2 的更新修复），当前 reverse 正式发布为 [`v1.7.1`](https://github.com/gthubtom1/reverse-skill/releases/tag/v1.7.1)。

## 当前版本检查

| 层次 | 实际结果 | 能说明什么 |
|---|---|---|
| 插件离线回归 | 85/85；Node 语法检查通过 | 项目/目标/分支隔离、取消终态、ID/alias 碰撞、stale source、并行失败、CAS、日志完整性、中断事务和有界恢复符合夹具 |
| 实际 Pi Web bundled SDK/RPC | Pi SDK 1.5.0、bundled CLI RPC；290/290 断言通过；加载当前发布插件目录无 loader/extension errors | 真实宿主 runner 注册三个工具和 `/continuity`，prompt/compact/tree/reload/resume/adopt/branch lifecycle 接线有效；验证使用隔离 deterministic provider，不调用账号模型 |
| 安装器离线回归 | Python 103/103；grilling 门面回归保持通过 | 默认组合、旧版本 continuity update、事务恢复、重复 hub 注册拒绝、精确来源、漂移拒绝、过滤配置和 restore 保留用户设置 |
| 当前活动部署 | 远程 plan 解析 reverse `v1.7.1` commit `c035cb0e5dbd12a5d3551971de43e93541e404` 与 continuity `v1.1.0` commit `11089f8`；verify 无 failures | 活动 checkout、manifest、独立插件注册和 tree hash 一致；reverse 不再使用本地 working copy |
| 当前 accept | REA 6.8.0：229/229 tools；reverse identity/router 通过；Spec Kit 1.3.1 version/init 通过 | 四合一静态和基础宿主验收未被插件升级破坏；JADX provider 仍因缺少 caller-supplied bridge JAR 保持 optional failure |
| 隔离 fresh-default | 新安装根和 agent/project，远程取得 reverse `v1.7.1` 与 continuity `v1.1.0`，Spec Kit 新项目 init；verify/accept 通过，JADX 仍为 optional missing bridge | 证明默认 `all` 路径在独立目录获取公开冻结版本并完成静态安装；复用本机已符合版本要求的官方工具，不冒充无工具裸机测试 |
| 实际宿主扩展烟雾 | 新 trusted session 注册 `continuity_status`, `continuity_search`, `continuity_save` 与 `/continuity`；fresh → save → resume → untrusted 全部通过 | 当前已安装 release 可被实际 Pi Web bundled runtime 加载，项目隔离和 trust gate 生效 |

`accept` 的 JADX 检查分类为 `missing_analysis_engine`：需要调用方通过 `REA_JADX_MCP_JAR` 提供 `jadx-headless-mcp 0.7.1`，REA 不自动下载或安装它。这不阻塞 continuity plugin、reverse router 或安装部署。宿主 loading、MCP schema、真实 reverse 任务和 Spec Kit 实际成果语义仍分别报告，机械验收不替代业务证明。

## 1.0.0 历史基线


| 层次 | 实际结果 | 能说明什么 |
|---|---|---|
| 插件离线回归 | 80/80，通过 Windows、Linux CI；插件仓库全套 156/156 本地通过 | 文件身份、项目隔离、取消/替代、条件失败、并发 CAS、日志完整性、中断事务和有界恢复符合夹具 |
| 安装器离线回归 | Python 101/101；grilling 门面 9/9；Windows/Linux CI 通过 | 默认安装、旧范围升级、精确来源、漂移拒绝、过滤配置和 restore 保留用户设置 |
| 真实宿主流程 | Pi Web 0.15.0 内的 Pi SDK 1.5.0、bundled CLI RPC；290 项断言通过 | 实际 prompt、compact、tree、reload、resume、分支变化、adopt 和命令消息链路有效；这里用本地模拟 provider |
| 外部模型抽样 | 同一模型三轮：保存两个独立决定、撤销一个、新会话续接；实际工具记录与落盘状态符合预期 | 本次抽样正确保存 cancelled，并保持未撤销的 accepted 约束；不代表所有模型 |
| 当前 Pi Web 部署 | 安装器 update 取得发布提交并注册独立插件；verify 无 failures | 活动配置、checkout、manifest 与文件摘要一致 |
| 实际 Web 页面 | 隔离项目新会话执行 `/continuity status`，页面显示取消角色与有效离线约束；无模型调用 | Web 前端可见输出，且真实服务加载了已安装扩展 |
| 全新默认安装 | 新安装根、agent 配置、成果项目；默认 all 自动含插件，远程取得同一发布 commit，verify 通过 | 新设备默认路径能获取插件；测试复用了本机符合版本要求的官方工具，不冒充裸机全工具下载测试 |
| 原组合基础验收 | REA 6.8.0 的 229/229 tools、原 master-router、Spec Kit 1.3.1 的版本/init 通过 | 插件接入未破坏这些基础路径；原有 JADX 桥接缺口仍单独报告 |

## 1.0.0 历史发现与修正


首次外部模型抽样把两个独立决定合成一条，撤销角色时只改文字、保留了 accepted 状态。恢复后的回答虽正确，记录粒度却不符合取消语义。补明确“一条记录对应一个可独立变更的对象/决定”和按类型选择 status 的工具说明后，用**相同三条用户提示**复测：两个决定分别保存，原角色 id 为 cancelled，另一约束保持 accepted，新会话正确续接。原失败与复测的完整本地报告均保留，未用成功自述替代落盘检查。

Windows CI 还暴露了一处短路径/规范路径的测试断言差异；修正为比较真实路径，未改变插件识别规则。修复后的两个平台均通过。

## 可复验入口

```text
# 插件目录：无网络的存储和运行时测试
node --test test/*.test.mjs

# 对实际宿主包运行 SDK/RPC 生命周期验证；PI_SDK_DIR 指向该包目录
PI_SDK_DIR=<实际 pi-coding-agent 目录> node scripts/verify-sdk.mjs

# 安装器目录
python -B -m unittest discover -s tests -v
node --test tests/pi-grill-skills.test.mjs
python scripts/install.py verify --root <安装根>
python scripts/install.py accept --root <安装根>
```

Windows PowerShell 用 `$env:PI_SDK_DIR = '<实际目录>'` 设置后执行 Node 命令。SDK 脚本不访问账号或网络，报告默认写系统临时目录；它不在已冻结的插件源码目录生成报告。

在实际 Pi Web **新会话**中执行 `/continuity status` 检查当前项目。已有会话可 `/reload` 后再查。第一次工作尚未保存时不会凭空出现历史；普通启动和查询不会自动建立项目记忆。旧项目应先复核原 case、报告和证据，再增量保存可信续接记录。

## 验证边界

- 记录只在各项目 `.pi/memory/`；不集中汇总、不自动上传，也不自动提交到 Git。
- 默认恢复正文最多 6,000 字符，另有稳定规则与工具声明；这不是完整宿主上下文或 token 数上限。
- 当前文件日志按记录数线性读取。已覆盖模拟二十天的修改/取消关系，未完成真实连续二十天或数万条记录的性能对照。
- 模型仍需正确调用保存工具；扩展不能保证所有重要信息都被记录，不能把推断或“改文件成功”证明成业务完成。
- `verify` 不执行宿主，`accept` 也不执行续接事件，所以其 unverified 字段保持原义；独立宿主验收记录不伪造回执里的检查项。
- 单个来源文件限 5 MiB；大样本与长日志通过小型证据索引引用原材料和实际身份。
- 原始会话、真实配置、回执备份与完整模型 trace 留在本机，不随本文发布。
