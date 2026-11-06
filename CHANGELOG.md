## 0.3.4 — 2026-11-06

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
