# 给安装 AI 的 Impeccable 接入说明

Impeccable 是官方设计技能。只有一个主技能 `impeccable`；`critique`、`audit`、`polish` 等是任务命令，无需分别安装。本次使用官方 Pi 构建，不改原文，不需要 wrapper。

- 来源：<https://github.com/pbakaus/impeccable>
- 固定 commit：`cf7ea4a8fe56f3e186e9ffaca3124937e36e6430`
- 上游目录：[.pi/skills/impeccable/](https://github.com/pbakaus/impeccable/tree/cf7ea4a8fe56f3e186e9ffaca3124937e36e6430/.pi/skills/impeccable)
- 本仓复制源：`resources/external-skills/impeccable/`，58 个官方技能文件及同一 commit 的原始 LICENSE、NOTICE.md。来源说明见 [external-skills README](../resources/external-skills/README.md)。

## 安装操作

1. 先看当前用户的实际 Pi agent 目录：优先 `PI_CODING_AGENT_DIR`，否则通常是 `~/.pi/agent`（Windows 为 `%USERPROFILE%\.pi\agent`）。目标是 `<agent目录>/skills/impeccable/`。
2. 检查该目录、`~/.agents/skills/` 和项目技能中是否已有同名技能。Pi 同名保留先发现的一项；不要重复安装。目标不存在则复制整个源目录，保留 `SKILL.md`、`reference/`、`scripts/`、LICENSE、NOTICE 及相对路径；Unix 保留 `scripts/impeccable` 的可执行位。
3. 已有内容相同就保持不变；内容不同则保留原目录，把候选放在技能发现路径外并报告冲突，不静默覆盖。不要复制个人 settings、MCP、auth、会话或模型配置。
4. UI 任务由通用 `subagent` 按任务描述动态选择设计技能，无需额外 UI profile，也无需将设计预设正文写入通用 profile。三个现用 profile 的安装与升级按 [profile 指南](pi-agent-profiles.md) 操作，保留已有 frontmatter、模型、tools 和 flags。
5. 完成后正常 `/reload` 或开新会话，确认 `impeccable` 的发现路径。文件已复制不表示当前会话已经加载，也不保证模型自动使用。

## 实际用法与边界

Pi 使用原生技能命令，参数会作为请求交给技能：

```text
/skill:impeccable critique 当前设置页的操作路径，只读评估
/skill:impeccable polish 当前表单，保留品牌与真实业务行为
```

本次没有注册官网示例中的 `/impeccable` 或独立 `/audit` 快捷命令。也可让 UI Worker 根据任务和动态技能描述选择，实际加载相关说明并应用到成果。

技能启动脚本首次调用可能下载固定版本的 native engine 到 `~/.impeccable/bin/`。本次只复制技能，未运行 launcher、engine 或 detector，未启用 hook、Live Mode、浏览器插件、服务或项目 init。技能已安装不表示这些能力就绪；未来调用仍受用户和项目授权、联网条件约束。launcher 不可用时按官方 SKILL 的降级路径读取已有项目上下文及适用参考继续，如实说明未运行的检查。

官网另有 `npx impeccable install`、共享技能安装等路线；npx 路线需 Node 18.19+，本次手工复制不依赖它，也不要顺带运行 latest CLI、开启 hooks 或创建 PRODUCT.md / DESIGN.md。上游技能中的 permission 或工具声明不扩大现有授权。复制技能不保证 UI 自动变漂亮，效果仍需真实任务验证。

升级时重新选择精确 commit，整体核对技能、引用、LICENSE 和 NOTICE 后替换获准更新的副本；不混用新 SKILL 和旧参考。恢复技能时保留用户后续修改；移除技能时将自己的目录移出技能发现路径后 reload。以上均是独立用户资源，不改变 Python 安装事务、旧 tag、pins 或现有运行时。
