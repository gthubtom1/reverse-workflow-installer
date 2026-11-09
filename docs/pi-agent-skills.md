# Portable Pi skills 安装说明

这组技能是为当前主代理、requirements-planner、Worker 和 reviewer 设计的小型通用技能。它们不安装模型、不安装账号、不安装 MCP 服务，也不替代 reverse-workflow、ui-ux-pro-max 或 grilling。

部署完整工具环境时先读[公共整环境部署指南](environment-recovery.md)，按目标电脑和宿主选择通用技能、UI/UX、unslop、访谈技能与适用扩展。

另有独立保留的 [Impeccable 官方 Pi 设计技能](impeccable.md)：按固定来源复制一个主技能，安装路径、冲突处理和用法见该交接说明。

## 目标目录

全局技能目录通常是：

%USERPROFILE%\.agents\skills\

如果宿主或项目明确使用其他 skills 根目录，以实际配置为准。不要把用户名或盘符写死。

## 给 AI 安装代理的操作

1. 读取本说明、仓库的 [resources/pi-agent-skills/README.md](../resources/pi-agent-skills/README.md) 和目标主机的 Pi 配置。
2. 找到当前用户实际使用的全局 skills 目录；默认使用当前用户的 %USERPROFILE%\.agents\skills\。
3. 从仓库 `resources/pi-agent-skills/` 复制每个技能目录及其 `SKILL.md`；本说明的 `docs/` 不是技能源目录。
4. 目标技能不存在时创建；内容相同则保持不变。
5. 目标技能已经存在但内容不同，先报告冲突，不要静默覆盖。
6. 不复制 auth.json、models.json、settings.json、session、memory 或凭据。
7. 安装后 reload 或重启 Pi/Pi Web，并在新会话检查技能是否出现在技能清单中。

## 和当前 profile 的关系

当前 profiles 使用 load_skills: true，让模型可以看到动态技能清单。技能不会绑定到固定的 UI、后端或逆向名称；模型根据任务描述选择相关技能。

主代理和 requirements-planner 负责需求、边界和架构；Worker 使用调试、反过度设计和验证技能；reviewer 使用审查和验证技能。逆向仍优先使用 reverse-workflow，UI 仍优先使用现有 UI/UX 技能。

## 验收边界

文件复制成功只证明技能已写入 skills 目录。还需要在新会话确认：技能被发现、相关任务会选择它、技能没有覆盖项目规则，并且实际检查结果符合任务验收标准。