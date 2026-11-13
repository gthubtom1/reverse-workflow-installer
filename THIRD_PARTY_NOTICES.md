# 第三方来源与边界

- **REA / morluto**：https://github.com/morluto/rea ，npm 包 rea-agents。分析引擎、MCP、证据语义和官方技能属于其原项目；保留原包 LICENSE、DISCLAIMER、THIRD_PARTY_NOTICES 与 licenses。安装器只调用原 CLI，不 fork、不改源码、不摘抄其技能正文。
- **Spec Kit / GitHub 及贡献者**：https://github.com/github/spec-kit ，PyPI 包 specify-cli。规格/计划/任务、随包模板和 integration 属于原项目，按原 MIT 等随包许可保留。生成文件与用户后续成果的归属遵守各原件许可；本仓不改工具源码。
- **reverse-skill / ZhaoXu 及贡献者**：上游 https://github.com/zhaoxuya520/reverse-skill ，本组合增强发行 https://github.com/gthubtom1/reverse-skill 。原 MIT、作者署名与贡献记录由该仓库保留。本仓只引用其 RULES、原 router、PRIMARY 与既有 Codex 薄插件路径，不复制知识或另建路由。
- **Pi / Earendil Works 及贡献者**：https://github.com/earendil-works/pi 。本仓按官方 package/skills/settings/MCP 文档适配；不分发 Pi 本体。
- **grilling / mattpocock 及贡献者**：https://github.com/mattpocock/skills 。`grilling`、`grill-me`、`grill-with-docs` 和 `domain-modeling` 的官方正文与原许可证归上游；本仓只提供 Pi 门面适配脚本和使用说明，不把它们并入核心安装事务。
- **Codex / OpenAI 及贡献者**：https://github.com/openai/codex 。只使用已声明的项目技能发现与官方组件集成，不假定所有版本都具备相同插件命令。

## 随仓资源的来源索引

`resources/` 的来源与许可单独列于下表；不能把本仓 MIT 解释为这些资源统一换证，也不能把历史来源记录当成当前文件完整性清单。

| 资源 | 来源与许可 | 分发与核对入口 |
| --- | --- | --- |
| `resources/external-skills/impeccable/` | [pbakaus/impeccable](https://github.com/pbakaus/impeccable/tree/cf7ea4a8fe56f3e186e9ffaca3124937e36e6430/.pi/skills/impeccable)，固定 commit `cf7ea4a8fe56f3e186e9ffaca3124937e36e6430`，Apache-2.0 | [来源说明](resources/external-skills/README.md)、[LICENSE](resources/external-skills/impeccable/LICENSE)、[分发 NOTICE](resources/external-skills/impeccable/NOTICE.md)、[复制与运行边界](docs/impeccable.md)。58 个官方技能文件保持原字节；NOTICE 带本仓补充说明。 |
| Impeccable 的 iOS/Android 派生参考来源 | [ehmo/platform-design-skills](https://github.com/ehmo/platform-design-skills)，MIT | [保留的 MIT 原文](resources/external-skills/impeccable/THIRD_PARTY_LICENSES/platform-design-skills-MIT.txt)。许可证查验 ref 与尚未确认的派生内容 commit 的区别见上述 NOTICE。 |
| `resources/pi-local-packages/pi-persona-rewind/` | [agent-plugins/pi-seep-ext](https://github.com/gthubtom1/agent-plugins/tree/2742f417d4dcf275a9a57bdf654af4a53ff25ddf/plugins/pi/pi-seep-ext)，固定来源 commit `2742f417d4dcf275a9a57bdf654af4a53ff25ddf`，MIT；本副本含适配补丁 | [LICENSE](resources/pi-local-packages/pi-persona-rewind/LICENSE)、[历史来源与补丁记录](resources/pi-local-packages/pi-persona-rewind/UPSTREAM.json)、[当前分发边界](resources/pi-local-packages/README.md)。UPSTREAM.json 中的历史摘要、case-dir 与工作台补丁不是当前包的必备文件/schema 声明。 |
| `resources/pi-local-packages/pi-remote-access/` | 同一 agent-plugins/pi-seep-ext 固定来源，MIT；独立恢复并适配的远程菜单 | [LICENSE](resources/pi-local-packages/pi-remote-access/LICENSE)、[来源与修改](resources/pi-local-packages/pi-remote-access/UPSTREAM.md)、[包说明及历史验证边界](resources/pi-local-packages/pi-remote-access/README.md)。`upstream/*.ts.txt` 为不加载的历史源码快照。 |
| `resources/pi-agent-profiles/`、`resources/pi-agent-skills/` | 本仓自有模板与技能，适用本仓 [MIT](LICENSE) | [profile 模板说明](resources/pi-agent-profiles/README.md)、[技能说明](resources/pi-agent-skills/README.md)。它们不是 REA、grilling 或 Impeccable 官方正文；profile 字段由目标宿主支持的 schema 解释。 |

这些来源说明提供分发导航，不新增安装组件、运行时配置 schema、校验器或自动加载入口。可选包的实际加载入口由各自 `package.json` 的 `pi.extensions` 声明。

本仓 MIT 仅覆盖本方安装器、薄适配、自有模板/技能和文档。组件依赖及目标样本不由该声明重新许可。运行时版本、来源、原包摘要在本机 receipt 中记录，不进入公开源码。
