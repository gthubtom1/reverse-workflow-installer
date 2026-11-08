## Next

- 更新可选 shell-guard 到 0.2.3：主代理与子代理共用 TEMP 回收规则；普通项目内 `rm` 移动到 TEMP，系统/盘根等受保护目标被阻止。Bash 工具不再打开等待确认弹窗。

## 0.6.0 — 2026-11-08

- 从 installer 的活动组件、manifest、resolver、CLI、计划、事务、receipt、verify/accept 与文档中移除 project-continuity；新 `all` 与所有子集都不会解析或加载它。
- 旧 receipt 更新增加安全退役迁移：receipt 能唯一识别未过滤 Pi 包注册时，在同一事务移除该注册；缺少身份、重复、hub 或其他同名注册时明确失败。旧包目录保留在历史版本目录中。
- 保留 REA、Spec Kit、reverse 与可选 shell-guard 的现有范围和配置行为；shell-guard 改用通用包身份工具，不再依赖已移除模块。
- 安装器与 Pi 入口包升级至 0.6.0，事务协议保持 0.2.0；补充旧回执兼容回归和更新后的 README、快速开始、兼容性、更新、维护与故障排查文档。

## 0.5.0 — 未发布

- 新增 Pi 独立可选 shell-guard：`--with-shell-guard` 默认关闭，旧 `all` 与旧 receipt 不自动启用，已选插件在 update 中保留。
- 支持 `--shell-guard-root` 只读复用精确 0.2.2 包；冻结远程 tag/commit/Git tree、本地包 hash、包名/版本及 index/runtime/src，拒绝漂移、额外资源、重复注册与 hub 碰撞。`--everything-gui` 与 `--everything-autostart` 的配置身份和漂移也纳入事务校验。
- 新增准确开发注册迁移与 Everything CLI 参数；冻结旧注册/hash 和 CLI SHA256，只管理 `shellGuard.everything.esPath`。Windows 等价路径按规范身份比较，保留用户原写法及其他配置。
- 强化 restore：保留后来编辑的注册，避免复活旧副本；处理首次创建的资源列表；部分恢复可安全重试，冲突解决前保留当前 receipt。
- 目标 `shell-guard-v0.2.2` 已发布并固定 commit/tree；远程身份变化时停止，不回退 main 或旧版本。

## 0.4.0 — 2026-11-07

- Add explicit official `--spec-kit-version` pins, preserving latest-stable defaults and frozen replay/version/hash checks when existing official packages must remain unchanged.
- Guided Pi entry uses stable result/scope/delivery cards, copied aliases and adaptive technical paths bounded by the original reverse case.
- Independent Grilling wrappers preserve all official input bytes, track local hashes and reject output-path/ownership conflicts. Legacy adapted companions are reported without rewriting them.
- Pin project-continuity 1.2.0 as a standalone child package; retain exact release/commit/tree validation and old-release update checks.
- Clarify per-component authorization coverage, failed regressions, reconstruction levels, and separated mechanical/host/model validation.

## 0.3.6 — 2026-11-06

- Correct the verification document's installer release link to the current v0.3.5 docs release.


- Refresh verification identity for reverse v1.7.2 and the final active remote deployment.


- Record the isolated fresh-default installation and the current v0.3.3 verification documentation identity.


- Refresh public project-continuity verification for 1.1.0, reverse v1.7.1, the remote frozen deployment, and the separated host/semantic verification limits.


- Allow an intact older frozen project-continuity release to pass update preflight; the new plan still validates and installs the newer published identity.
- Add an offline regression covering an older active plugin release during update.


- Integrate project-continuity 1.1.0 with the published frozen tag and update tests/docs.
- Roll back pending journals safely before a new install; stop when a later user edit makes rollback ambiguous.
- Reject Pi package registrations that are hub/parent directories capable of loading project-continuity twice.
- Clarify REA as a bounded backend and make APK decode/rebuild/Frida bootstrap explicit with `-AllowBootstrap` / `--allow-bootstrap`.
- Clarify read-only reverse review mode and make completion artifacts conditional on applicability.

## 0.3.0 — 2026-11-06

- 默认 Pi `all` 安装与旧三组件安装的更新加入 project-continuity 1.0.0；支持显式 opt-out 和只读本地插件目录复用。固定来源 ref 为 `project-continuity-v1.0.0`，由插件维护方发布。
- 只注册独立插件子目录；校验 package/index/runtime/store、唯一扩展入口、零运行时依赖、冻结 commit 与必需 tree hash，拒绝计划后漂移及禁用扩展的注册过滤。
- 保留用户 packages、项目文件及失败更新前的活动 receipt；restore 按事务撤销插件注册。accept 明确保留插件加载与跨会话恢复为未验证。
- 修正恢复测试误检查入口包的问题；离线 Python 套件从 79 项扩充至 101 项并通过，覆盖既有范围更新、缺文件/hash、篡改来源、错误 checkout、漂移与回退反例。
- 同步 README、快速开始、兼容记录、维护流程与插件安装说明。补充 [发布与部署验收记录](docs/project-continuity-verification.md)：实际 Pi Web 状态页面、活动升级、全新默认安装、SDK/RPC 生命周期及外部模型三轮抽样通过；验证边界分别保留。
