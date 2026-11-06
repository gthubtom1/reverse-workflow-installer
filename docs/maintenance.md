# 维护与发布闭环

普通使用者直接阅读 [零基础开始](reverse-workflow-playbook.md#零基础一键开始)。本文用于维护两个仓库，避免只改规则、漏掉入口或教程。

## 修改时检查关联位置

| 修改内容 | 必须核对的关联位置 |
|---|---|
| reverse 行为规则 | `RULES.md`、`RULES_zh.md`、master skill、对应 ops 契约与实际 PRIMARY；不修改原始路由语义来迁就测试 |
| 用户沟通方式 | Pi skill 与短 prompt、Claude/Codex 入口、quick-start、usage、playbook；阶段汇报不能被模板变成每步审批 |
| 安装/更新/恢复 | 冻结 plan、上一事务的文件归属、receipt、verify、配置保留、组件子集与完整安装的离线反例测试 |
| project-continuity 分发 | components.json 的固定 tag 与包身份；只注册插件子目录；冻结计划、旧三组件 update 扩展、runtime/index/store/package 完整性、必需 hash、漂移/restore 反例及 project-continuity-install、README、quick-start、compatibility |
| grilling 门面 | 本仓适配/检查脚本及离线 fixture；官方 `grilling`、`domain-modeling` 原文保持外部管理 |
| 发布和换电脑部署 | GitHub 默认分支、必需 CI、reverse 正式 release；仅推 main 不会覆盖安装器优先选择的旧 release |

目标是减少用户负担：技术选择和证据检查由 agent 负责，目标/结果取舍和新增授权由用户决定。不要为了凑固定菜单而添加流程，也不要为每个小步骤生成一整份状态表。

## 验证顺序

1. **离线回归**：在 installer 运行 `python -B -m unittest discover -s tests -v` 和 `node --test tests/pi-grill-skills.test.mjs`；在 reverse 执行其原生路由、coherence、兼容性与文档检查。
2. **真实部署**：用同一安装根重新 plan/update，复用原官方包时核版本和摘要。通过事务写入，保留用户修改；不要手改 receipt 让 verify 变绿。
3. **本机验收**：运行 `verify`、`accept`，检查实际使用的配置根、全局入口和活动 package。官方工具/宿主加载/模型行为分别记录。
4. **对话抽样**：至少观察“已授权的两步检查不中途请求继续”和“新运行/联网范围保留必要确认”。检查实际工具事件，不能只凭模型自述。抽样通过不等于所有模型和困难目标已验证。
5. **发布**：PR 检查通过后按保护规则合并；reverse 若仍有更早 release，发布指向已验证提交的新正式版本。重新检查安装器解析的确切 tag/commit，再记录本机与远程身份。

project-continuity 由插件仓库维护方在最新 main 的独立 worktree 集成，不在 installer 任务修改插件代码；目标 tag 保持 `project-continuity-v1.0.0`。发布后再核对 tag 解析的精确 commit。tag 未发布时远程 plan 应明确失败，不回退 main；如用本地 worktree 先验收，必须对实际插件目录重新 plan，receipt 不宣称本地包等于远程 tag。本次 installer 离线回归与代码审查不代替插件发布、真实部署或 profile 变更。

`verify` 通过表示静态安装一致，`accept` 表示本机工具基本运行通过。只有真实目标的证据和测试才能说明功能正确；尚无证据时保持 unknown。

Pi 用户级技能的检查只证明目录、frontmatter 和本地门面内容满足适配要求；没有上游基线时，它不能证明官方正文来源真实。更新外部技能后执行适配和检查，再 reload 宿主。
