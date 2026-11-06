# 更新、备份与恢复

工具更新和成果追版是不同操作。`update` 跟随官方 REA/Spec Kit stable 与增强 reverse release/main；上游产品 1.0→1.1 的差分、规格和测试由原 reverse 专业流程在成果项目中处理。

Pi 的 `grilling` 伴随技能不属于 Python 安装器的核心事务。运行 `npx skills update` 后，要在安装器仓库根目录重新执行 `node scripts/pi-adapt-grill-skills.mjs`；这只重写 `grill-me` 和 `grill-with-docs` 门面，不修改官方 `grilling` 正文。核心安装器的 update/restore 不会自动回滚或升级 `~/.agents/skills/` 下的用户级技能。

工具更新沿用相同 root、client、agent 和 project，重新 plan 并保存冻结文件。同一安装根允许保留或扩展所选组件；收缩或替换组件范围会明确拒绝，避免把仍存在的包与配置变成无人校验的残留。需要缩小范围时先审阅 restore，或使用独立的新 root。

宿主入口更新按上一事务记录的摘要判断归属：我方旧版入口可以升级，用户修改会保留并报冲突；同一个 agent 不允许两个安装根争用同名入口。Pi 活动适配器目录按适配源码摘要切换，旧目录保留作恢复依据。选中 REA/Spec Kit 的重复安装复用已核摘要的原包；发生漂移时拒绝重新记成“通过”。

显式复用原包路径时，须先由其管理者在独立位置准备本次精确版本；版本不符则拒绝，安装器不会修改复用目录。省略复用参数可以在 root/versions 的新目录安装。`--reverse-root` 始终使用该工作副本，update 不会替你 git pull 或覆盖本地修改；先由仓库维护流程更新，再 plan。源码身份核对包含受版本管理的文件和未忽略的新源码，排除 Git 忽略的本地 case、临时日志与生成工具索引；日常分析记录不应被误判成源码漂移，真实源码修改仍会触发校验。

事务顺序：解析精确身份 → 隔离 npm/uv 目录 → 官方 setup 暂存 dry-run/yes → 检查只涉及 REA 字段和绝对 launcher → 官方 init 暂存（首次）→ 检查配置未漂移 → 写适配器和配置/新项目 → 回执。每个写入前持久化原字节和新字节、SHA256；失败条件恢复本次写入。旧活动 receipt 保留，首次失败不产生 installed:true。中断/crash 仍有 journal 可恢复；文件系统断电原子性和整个多文件事务的瞬时原子可见性不作保证。

配置 diff 是回执内的 path 与 before/after SHA256，完整字节差异在本地 journal。可自行离线检查备份的 base64；不要把含秘密的内容发布。安装根本身不受这个仓库的 .gitignore 保护，若你给安装根创建 Git 仓库，必须另行忽略 `.installer/`、versions、adapters 与运行数据。本仓内 `.local/` 和 receipt 模式已 ignored。

`restore --root <root>` 默认预览最近活动事务；加 `--apply` 后实际恢复。可显式 `--transaction <ID>`，但有活动安装时只允许最近事务，避免跨版本覆盖。连续 restore 按最新到最旧回退。

恢复遵循三方条件：原始值 B、安装后 A、现在 C。C 等于 A 才退回 B；C 有用户改动则保留。JSON 按字段/精确资源项处理，Codex TOML 按 REA 子表处理，项目/适配文件按完整字节处理。其他 MCP、模型和后来加入的 package 保留；变更过的本方字段/表或项目文件列 conflict，CLI 非零返回。conflict 并不表示用户改动被删除；先读取结果再决定如何人工整理。暂不自动合并用户修改过的同一 TOML 子表或同一项目文件。

重复安装不会重复下载完成且摘要一致的版本，不重复 init，不重复注册资源。失败留下的并列版本目录保留供诊断，重试用新的隔离目录；不覆盖旧目录。旧包、缓存、备份不自动删除或卸载。若外部修改了包，verify 报漂移，不能将该包冒充原安装身份。

已有成果项目的 constitution/spec/plan/tasks/UI/代码和原生模板均保留。需要新模板功能时，在新独立项目生成官方资源，再审阅迁移；本版没有自动化模板升级器。
