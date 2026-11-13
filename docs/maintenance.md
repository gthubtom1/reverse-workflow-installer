# 维护与发布闭环

普通使用者直接阅读 [零基础开始](reverse-workflow-playbook.md#零基础一键开始)。本文用于维护两个仓库，避免只改规则、漏掉入口或教程。

## 修改时检查关联位置

| 修改内容 | 必须核对的关联位置 |
|---|---|
| reverse 行为规则 | `RULES.md`、`RULES_zh.md`、master skill、对应 ops 契约与实际 PRIMARY；不修改原始路由语义来迁就测试 |
| 用户沟通方式 | Pi skill 与短 prompt、Claude/Codex 入口、quick-start、usage、playbook；阶段汇报不能被模板变成每步审批 |
| Pi 用户级原则与 profiles | `resources/pi-agent-profiles/`、profile/skill 安装说明与目标用户入口；同时核对活动 adapter 的短 prompt/skill 来源。正文、frontmatter 与宿主开关分别核对，活动资源通过安装事务更新 |
| 安装/更新/恢复 | 冻结 plan、上一事务的文件归属、receipt、verify、配置保留、组件子集与完整安装的离线反例测试 |
| shell-guard 分发 | Pi 可选默认关闭；0.3.0 AST adapter 与精确文件清单、ISC vendor 来源、独立包 name/version/index/runtime/src、最终 commit/tree/hash、旧回执、准确迁移、CLI/GUI/自动启动配置保留、重复/hub 拒绝、漂移/回退反例和 shell-guard-install/README/quick-start/updates/compatibility/troubleshooting |
| Craft bundle 分发 | Pi 显式可选，all 不扩大，依赖不静默补选；全量文件/hash/固定 base/有序 patch/OS/arch/contract/min_reader，显式 Pi Node/入口/version；隔离副本、按需 skill/instructions/entry、唯一注册、旧 receipt/未知 reader、失败重试/pending/用户后改/多事务条件恢复；正式资产按 [pin](../releases/windows-x64.json) 与独立 [获取 helper](craft-acquisition.md) 核身份，不预填未来资产；见 [指南](craft-install.md) |
| grilling wrapper | 独立输出目录、所有权/hash、链接与手改冲突 fixture；四个官方技能文件保持只读，旧门面漂移单独报告 |
| 发布和换电脑部署 | 两仓 GitHub 受保护 main 的确切 commit、必需状态门与可选 Craft pin；当前核心 reverse 默认解析 main，未合并修复分支不会被默认安装获取；旧 release/pin 不移动 |

目标是减少用户负担：技术选择和证据检查由 agent 负责，目标/结果取舍和新增授权由用户决定。不要为了凑固定菜单而添加流程，也不要为每个小步骤生成一整份状态表。

## 验证顺序

1. **离线回归**：在 installer 运行 `python -B -m unittest discover -s tests -v` 和 `node --test tests/pi-grill-skills.test.mjs`；在 reverse 执行其原生路由、coherence、兼容性与文档检查。
2. **真实部署**：用同一安装根重新 plan/update，复用原官方包时核版本和摘要。通过事务写入，保留用户修改；不要手改 receipt 让 verify 变绿。
3. **本机验收**：运行 `verify`、`accept`，检查实际使用的配置根、全局入口和活动 package。官方工具/宿主加载/模型行为分别记录。
4. **对话抽样**：至少观察“已授权的两步检查不中途请求继续”和“新运行/联网范围保留必要确认”。检查实际工具事件，不能只凭模型自述。抽样通过不等于所有模型和困难目标已验证。
5. **发布**：按保护规则完成 PR 和合并；查询两个远程 main 并检查新安装计划冻结的 reverse commit。当前核心策略解析增强 main，不能把只推审查分支当默认用户已拿到修复；正式 release 与 Craft 旧 pin 另核，旧 tag 不移动。

旧 project-continuity receipt 的退役兼容只在 installer 中处理：新计划不解析或加载该组件；更新时冻结唯一注册并通过事务移除，无法识别则停止。插件仓库和其他 agent-plugins 目录不在本仓任务范围内。shell-guard 0.3.0 使用 pi-trash 风格 AST/Node-helper 适配及随包 ISC `unbash` 文件，不安装目标 npm 依赖；发布前主流程需核对最终文件清单并设置最终 commit pin，再核 tag 身份、完整文件与运行验收。Everything 接线及安装事务/配置规则保持不变。

Craft 当前正式身份为 core v0.7.0、native Craft-Pi v0.1.1、reverse v1.9.0；独立获取 helper 为 `craft-acquisition-v0.1.1`，不是核心版本升级。以 [正式 pin](../releases/windows-x64.json) 核 tag/commit/资产摘要，按 [获取指南](craft-acquisition.md) 实际下载并校验 Craft/reverse；核心 installer 仍只消费本地 bundle，没有直接 fetch flag。新版本须重新 freeze/build、核全量 hash/许可与兼容/升级/回退，并走受保护 PR/发布门，不移动 immutable 旧 tag。资产存在不证明本机 Pi/provider、宿主加载或业务接受；fresh 网络最后一次匿名 API 403、无 complete 的边界保留，不能把 GET/hash 检查写成完整换机通过。旧 0.6.1 verify 忽略新组件，不认证 Craft，新入口必须使用能力 gate。

`verify` 通过表示静态安装一致，`accept` 表示本机工具基本运行通过。只有真实目标的证据和测试才能说明功能正确；尚无证据时保持 unknown。

Pi 用户级技能的检查只证明目录、frontmatter 和本地门面内容满足适配要求；没有上游基线时，它不能证明官方正文来源真实。更新外部技能后执行适配和检查，再 reload 宿主。
