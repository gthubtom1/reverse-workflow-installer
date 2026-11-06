# project-continuity 插件安装

本仓提供 Pi `project-continuity` 1.0.0 的安装集成。来源 ref 为 `project-continuity-v1.0.0`；发布由插件维护方完成。本次离线测试不证明远程 tag 已发布，也不证明真实 Pi/Web/SDK 已加载插件。

## 安装范围

`project-continuity` 是独立的 Pi 插件包，来源为 `gthubtom1/agent-plugins` 的 `plugins/pi/project-continuity`，包名为 `@toti/pi-project-continuity`。插件没有运行时依赖；Pi 提供宿主接口。安装器只注册该子目录，不注册 hub 根或其他 personality/retry 扩展，也不执行插件包的 npm install。

- `--components all`（默认）与 Pi 宿主组合时自动加入插件，包括对原有 REA/reverse/Spec Kit 三组件安装执行 update。
- `--without-project-continuity` 在新安装或尚未包含插件的旧安装更新中跳过插件，且不查询插件版本来源。
- `--components project-continuity --client pi` 可在独立 root 只安装插件；必须显式指定 agent/config 目录，无需成果项目、REA、Spec Kit 或独立 Node。
- 显式组件子集如 `--components reverse` 不自动加入插件；需要时将 `project-continuity` 加入逗号列表。
- Codex/Claude 的默认组合不安装插件；显式为非 Pi 宿主选择该组件会拒绝。
- 显式选中插件与 `--without-project-continuity` 互斥。已经包含插件的活动 root 不允许通过 opt-out 静默缩减范围；应按事务 restore，或使用独立 root。

## 冻结来源与内容校验

远程模式在 plan 阶段通过 `GET <api>/commits/<release_ref>` 将固定 tag 解析成 40 位 commit。tag 不存在即失败，不回退 main。安装按冻结 commit checkout；回放 plan 不重复查询版本。plan 展示插件获取与注册操作。

安装器检查 `package.json` 的 name/version，要求 `pi.extensions` **恰为** `["./index.ts"]`，其他 skills/prompts/themes 为空，dependencies/optionalDependencies 为空。`package.json`、`index.ts`、`runtime.mjs`、`store.mjs` 四个文件缺一即失败。插件树中的符号链接被拒绝，避免外部目标内容绕过摘要。

安装完成后必须在 receipt 和 `complete.json` 中记录插件 tree hash。verify 检查必需 hash、manifest、路径、注册和克隆模式的实际 Git HEAD；缺少 hash 不算通过。复用 complete.json 时同样要求 hash 存在并一致。更新已安装插件前先检查活动身份，不能通过重新 plan 把旧插件漂移记为成功。安装中发现源文件改变会回退配置事务。

Pi 注册支持插件目录字符串，或不带资源过滤的 `{"source": "<插件目录>"}`。带 extensions/skills/prompts/themes 覆盖的对象会被报告为需审阅的注册变化；例如 `extensions: []` 不能被当作插件已启用。安装器保留该用户设置并拒绝覆盖。

## 本地只读复用

`--continuity-root <插件包目录>` 可以复用父任务准备的独立 worktree 中的插件包。仅校验和读取，不 clone、checkout 或修改该目录。plan 冻结路径、manifest 身份和 tree hash；内容改变后旧计划不可应用。

本地模式不查询远程 tag，也不宣称本地包等于公开发行 commit。正式发布来自最新 main 的独立 worktree 时，使用其实际插件目录重新生成 plan；不能将先前目录的 hash 复用到新 worktree。远程模式的 tag 名仍为 `project-continuity-v1.0.0`。

## 首次安装与既有安装更新

在安装器仓库根运行，以下均使用相对路径；agent/project/root 必须与活动 receipt 一致。

```text
python scripts/install.py plan --root ../workflow --client pi --agent-dir ../workflow/pi-agent --project ../my-project --reverse-root ../reverse-skill --output .local/continuity-plan.json
python scripts/install.py update --root ../workflow --plan-file .local/continuity-plan.json --apply
python scripts/install.py verify --root ../workflow
```

首次安装可将第二行的 update 换成 install。旧三组件 root 更新时保留 `all` 范围；不能用 `--components project-continuity` 代替完整范围，这会被判定为收缩。更新保留既有成果项目和 Spec Kit 模板。

如果复用现有 REA/Spec Kit 包，在 plan 加上原安装的 `--node`、`--rea-prefix`、`--spec-kit-tools` 和 `--spec-kit-bin`。它们必须匹配本次解析版本；来源有新版本时不能把旧包伪装成新版本。仅需本地插件集成时可再传 `--continuity-root`，但完整范围的其他组件仍遵循各自版本解析规则。

`--plan-file` 的范围与资源选择全部来自冻结文件；不要在回放时追加 `--without-project-continuity`，应重新 plan。install/update 不加 `--apply` 只预览。

## 回执与恢复

receipt 的 `project_continuity` 段记录 mode、root、name、version、extensions、plugin_dir、repository、tree_hash；克隆模式另有 commit。本地模式的 plan 也保存 tree_hash。

restore 撤销最近活动事务的注册变化，保留后来新增的用户 packages 和用户修改的注册对象，保留插件文件。旧三组件安装增加插件后 restore，会恢复此前 receipt 与入口；并不删除用户成果文件。失败更新保留原活动 receipt。

## 离线证据与真实验收

运行 `python -B -m unittest discover -s tests -v`。夹具模拟版本服务与 Git/官方 CLI，只写 `.local/tests/`；覆盖默认安装、旧范围扩展、opt-out、子集查询、冻结回放、缺文件、来源篡改、缺 hash、漂移、注册过滤、失败回退和保留用户配置的 restore。

verify 是静态检查。accept 不运行插件事件，会将 `project-continuity host loading and cross-session recovery` 保留在 unverified。重载实际 Pi/Web/SDK 后，还需在真实成果项目验证插件加载、事件触发、第二会话恢复和结果正确性，分别记录证据。安装器不创建项目记忆、不替代 reverse 原路由，也不把续接记录当作分析结论正确的证明。参见 [兼容记录](compatibility.md) 与 [维护流程](maintenance.md)。
