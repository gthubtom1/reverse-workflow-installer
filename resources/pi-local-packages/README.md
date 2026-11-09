# 公开可选 Pi 扩展包

这里分发两个可供任何 Pi 用户选择的小型扩展包：人格/会话回退与远程访问菜单。按目标机器和用途安装，包内不携带个人设置或账号。它们不是 Python 安装器组件，不会随 `all` 自动安装，也不注册整个 agent-plugins hub 或已退役的 project-continuity。

| 包 | 当前副本 | 加载入口 |
|---|---|---|
| pi-persona-rewind | 0.3.1；11 个文件 | `extensions/persona.ts`、`extensions/rewind.ts` |
| pi-remote-access | 0.1.0；17 个文件 | `extensions/remote.ts` |

两包都源自 [agent-plugins 的 pi-seep-ext](https://github.com/gthubtom1/agent-plugins/tree/2742f417d4dcf275a9a57bdf654af4a53ff25ddf/plugins/pi/pi-seep-ext)，保留 MIT LICENSE 和 UPSTREAM 来源内容；remote 的 UPSTREAM.md 将机器专属源码位置改为部署时解析的说明。这里分发的是带适配补丁的独立包，不是该上游 commit 的原样副本；部署使用本目录完整包即可。

原始 provenance 保留历史记录，不能当作当前文件清单：persona 的 `UPSTREAM.json` 提及实际包目录中不存在的 `lib/case-dir.ts`，且其 package.json 历史摘要与当前文件不同。本副本保留实际 11 个文件，不补造缺失文件；现有源码的相对导入不依赖 case-dir。该记录还提到旧工作台 load-system-prompt 的补丁，本包并不包含或恢复旧工作台。remote 的 README 包含原先测试命令和历史通过记录，本分发包不包含 test 目录，不能据此声称目标机器已验证通过；`upstream/*.ts.txt` 只是来源快照，不是加载入口。

## 安装 AI 操作

1. 先按[公共整环境部署指南](../../docs/environment-recovery.md)确认目标是 Pi Web/Pi，按所需功能选择包并准备实际 agent 目录，检查同名包与重复扩展注册。
2. 将每个完整包目录复制到 `<agent-dir>/packages/<包名>/`。相同内容不重写，不同内容先保留并报告冲突；不覆盖个人配置。无需构建或在这些包中运行 npm install。
3. 用当前宿主 Plugins UI 添加这两个**精确包目录**，或在同一 `PI_CODING_AGENT_DIR` 下分别执行 Pi 官方命令：

   ```text
   pi install "<agent-dir>/packages/pi-persona-rewind"
   pi install "<agent-dir>/packages/pi-remote-access"
   ```

   将占位符替换为目标机器实际绝对目录；本地包原地加载，不会由该命令复制文件。不要同时登记包及其单文件入口。Pi Web 如未提供独立 `pi` CLI，可使用 Plugins UI；不要为此换成另一个不共享配置的宿主。
4. 正常 `/reload` 后核对命令发现，再在隔离对话核 `/persona list`、`/rewind list`。不要在用户原会话试回退；回退上下文不会撤销工具对文件产生的效果。
5. 安装 `/remote` 不自动开放远程访问。默认保持宿主本机绑定；用户选择远程能力后，按目标机器配置认证、网络与 Tailscale 登录。包可读写目标机器凭据仓，复制目录本身不调用这些操作。二维码依赖 `qrcode-generator` 是可选项，缺失时仍显示网址，不为基本菜单能力强装依赖。

用户在目标机器自行选择人格内容、登录模型账号并配置需要的远程认证。按实际宿主 API 和平台检查所选命令；包源码存在不表示扩展已加载或远程连接已可用。
