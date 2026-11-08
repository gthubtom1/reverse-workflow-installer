# Pi shell-guard 安装与迁移

Installer 与 Pi 入口包版本为 **0.6.0**，事务协议保持 0.2.0。shell-guard 是独立、可选的 Pi 扩展：默认关闭，默认 `all` 只选择原三组件。它检查部分 shell 命令形式，并提供 Everything 文件名/路径索引查询；不是操作系统沙箱，也不能保证所有命令均被识别或没有误判。历史回放不是未来无绕过保证。

目标固定为 `shell-guard-v0.2.3`、包名 `@toti/pi-shell-guard`、版本 `0.2.3`。安装器固定其公开 commit/tree；远程 tag 不存在或身份漂移时 plan 明确失败，不回退 main 或旧版本。

## 日常清理

主代理和子代理遵守相同规则：普通项目内的单条、单个字面路径 `rm` 移到 `<项目>/TEMP/<批次>/<原名>`，工具输出会告诉你移动位置。原来的 `rm` 不执行；你检查后可以自己清空 TEMP。

系统/盘根、已知数据库路径或文件名、`.git`、TEMP 本身、项目外目标、目标或其父路径中的链接，以及无法明确解析的删除不会自动执行。Bash 守卫不再弹出等待确认的窗口；无法处理时立即把原因返回给模型。常规读取、构建、测试继续按有限 timeout 执行。

更新后先重启实际 Pi/Pi Web，再用 `/shell-guard status` 查看版本。`/shell-guard check <命令>` 只评估，不移动文件。

## 选择与冻结计划

以下命令在 installer 仓库根执行。示例只选择 shell-guard，不需要 REA、Spec Kit、reverse 或成果项目；替换为自己的独立安装根与实际 Pi agent 目录。

```text
python scripts/install.py plan --components shell-guard --client pi --agent-dir ../guard-agent --root ../guard-install --output .local/guard-plan.json
python scripts/install.py install --root ../guard-install --plan-file .local/guard-plan.json --apply
python scripts/install.py verify --root ../guard-install
```

将它加入完整组合时，在原 plan/install/update 参数上增加 `--with-shell-guard`；不改变既有 root、client、agent 和 project。Codex、Claude Desktop 和 `none` 不能选择此插件。选择参数只适用于 plan/install/update。没有 `--apply` 的 install/update/restore 只预览；重放 `--plan-file` 使用冻结来源，不再次解析 tag。

远程 plan 冻结 tag、commit、仓库 Git tree、包名、版本、唯一扩展和必需文件清单。应用时精确 checkout，校验 commit/Git tree、插件子目录的干净状态和完整包文件；receipt 记录独立包内容 hash。必需内容包括 `package.json`、`index.ts`、`runtime.mjs`、`src` 的配置/Everything/授权/路径/策略/拆分模块及四个规则模块。运行时依赖包、额外 Pi skills/prompts/themes、hub 根和链接内容均拒绝。

agent-plugins 的 shell-guard 克隆目录使用 `agent-plugins-shell-guard`；只注册插件子目录，不注册 hub。已有 receipt 中若仍记录 project-continuity，普通新计划不会加载它；update 只有在 receipt 能唯一识别其 Pi 包注册时才会移除该注册，否则在 plan 阶段明确失败。旧包目录保留在历史版本目录中。

## 只读复用本地独立包

```text
python scripts/install.py plan --components shell-guard --client pi --agent-dir ../guard-agent --root ../guard-install --shell-guard-root ../agent-plugins/plugins/pi/shell-guard --output .local/guard-plan.json
```

目录必须恰好是独立的 **0.2.3** 包，并包含完整运行文件；不能指向仓库根或旧版本包。plan 不查询该插件的网络来源，不 clone、checkout、安装依赖或改动本地源码，冻结实际内容 hash、包名、版本和资源声明。应用前或安装期间内容变化都会拒绝/回退。本地 hash 一致不证明该目录等于远程发行 commit。

## Everything CLI

可在所选插件的 plan 中增加：

```text
--everything-es <现存CLI的绝对路径>
--everything-gui <现存Everything GUI的绝对路径>
--everything-autostart
```

Windows 使用实际 `es.exe` CLI；不能指向 Everything GUI、目录或相对路径。安装器只核文件存在/可执行身份并记录 SHA256，不启动该文件，不安装 Everything，也不证明服务、索引或查询可用。

安装器合并 `shellGuard.everything.esPath`、可选的 `guiPath` 和 `autostart`，保留 `shellGuard.enabled`、`shellGuard.everything.enabled`、规则、查询限制和其他用户字段。`autostart` 只有在 CLI 报告 IPC/服务不可用时，才允许运行时启动配置的 GUI 并重试一次；安装器本身不启动 GUI、不安装 Everything，也不证明服务、索引或查询可用。路径按规范形式比较；Windows 正反斜杠、大小写及 `.` 等价写法不会触发冲突，等价时保留用户原写法。已有不同且不归原 receipt 管理的路径配置会拒绝覆盖。未传参数时保留当前配置；已管理的路径及 CLI/GUI hash 在 verify/update 中继续检查。用户后来更改同一字段时，restore 保留该改动并报告 conflict。

实际 Pi 进程的 `PI_SHELL_GUARD_ES` 可以覆盖设置路径。安装器不读取或修改该环境覆盖，静态校验只针对 receipt 中管理的设置与文件。保留的禁用开关不会被安装器自动启用。

## 准确迁移已有开发注册

已有开发包在同一 agent 的 `settings.json.packages` 注册时，增加其准确旧目录：

```text
python scripts/install.py plan --components shell-guard --client pi --agent-dir ../guard-agent --root ../guard-install --shell-guard-root ../reviewed-shell-guard --replace-shell-guard-root ../old-dev-shell-guard --output .local/guard-migration.json
python scripts/install.py install --root ../guard-install --plan-file .local/guard-migration.json --apply
```

迁移只适用于尚未由该 receipt 管理的单个开发注册。plan 冻结旧包路径、版本、内容 hash 和原注册对象；应用前再次比对。原注册必须恰好匹配一个独立包。重复注册、另一副本、资源过滤、直接 `extensions` 注册、父目录或 hub 碰撞均拒绝，不静默去重。成功后只替换原 packages 项的来源，保留其他元数据及配置；旧开发包原字节保留。已有受管理安装使用正常 update。

## 更新、恢复与验收

已选中的 shell-guard 会在后续 update 中继续保留；未指定新本地路径时沿用原只读本地包。旧 receipt 没有该选择就不会自动启用。完整组合更新保留完整组件范围；不能通过省略插件或改组件子集卸载它。活动包、注册、受管理配置或 CLI 漂移时停止，不用新 plan 自动认领变化。

```text
python scripts/install.py restore --root ../guard-install
python scripts/install.py restore --root ../guard-install --apply
```

restore 沿现有事务恢复插件注册与我方配置字段；迁移会恢复原开发注册。用户后续修改保留并列 conflict，旧包/版本目录保留。存在冲突时活动 receipt 保持当前事务，处理后可以重试同一 restore；只有恢复完成才切换回执。迁移后的新注册若被用户编辑或移除，恢复不会重新加回旧开发包。失败不写成功 receipt；已有活动安装继续保留，journal 记录恢复材料。参见 [更新与恢复](updates.md)。

`verify` 只核静态包、摘要、配置与唯一注册。`accept` 不运行 shell-guard 的工具事件，将宿主加载、拦截和 Everything 可用性明确保留为未验证。更新插件后完整重启实际 Pi/Pi Web，分别检查扩展与工具加载、代表命令的真实拦截、文件查询及禁用/环境覆盖行为。SDK 模拟、历史回放或安装退出 0 都不能代替这些运行验收。
