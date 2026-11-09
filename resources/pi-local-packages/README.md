# 本地扩展的可恢复源码

这里保留两个已部署小包的源码副本，供新电脑恢复工具能力，不包含个人配置、人格正文、密码、会话、测试运行目录或 node_modules。它们不是 Python 安装器组件，不会随 `all` 自动安装，也不注册整个 agent-plugins hub 或已退役的 project-continuity。

| 包 | 当前副本 | 加载入口 |
|---|---|---|
| pi-persona-rewind | 0.3.1；11 个文件 | `extensions/persona.ts`、`extensions/rewind.ts` |
| pi-remote-access | 0.1.0；17 个文件 | `extensions/remote.ts` |

两包都源自 [agent-plugins 的 pi-seep-ext](https://github.com/gthubtom1/agent-plugins/tree/2742f417d4dcf275a9a57bdf654af4a53ff25ddf/plugins/pi/pi-seep-ext)，保留 MIT LICENSE 和 UPSTREAM 来源内容；remote 的 UPSTREAM.md 仅将旧电脑绝对路径改为恢复时解析位置的说明，其余内容不变。这里复制的是带本地补丁的源码，不是该上游 commit 的原样副本；只下载上游不能复原这些补丁。逐文件复制摘要保留在本轮本地交付证据中，不是新安装协议。

原始 provenance 保留历史记录，不能当作当前文件清单：persona 的 `UPSTREAM.json` 提及本次源目录实际不存在的 `lib/case-dir.ts`，且其 package.json 历史摘要与当前文件不同。本副本保留实际 11 个文件，不补造缺失文件；现有源码的相对导入不依赖 case-dir。该记录还提到旧工作台 load-system-prompt 的补丁，本包并不包含或恢复旧工作台。remote 的 README 包含原先测试命令和历史通过记录，本恢复副本不包含 test 目录，不能据此声称本次重跑或新机通过；`upstream/*.ts.txt` 只是来源快照，不是加载入口。

## 新机安装 AI 操作

1. 先按[整环境恢复交接](../../docs/environment-recovery.md)准备实际 Pi Web/Pi agent 目录，检查同名包与重复扩展注册。
2. 将每个完整包目录复制到 `<agent-dir>/packages/<包名>/`。相同内容不重写，不同内容先保留并报告冲突；不覆盖个人配置。无需构建或在这些包中运行 npm install。
3. 用当前宿主 Plugins UI 添加这两个**精确包目录**，或在同一 `PI_CODING_AGENT_DIR` 下分别执行 Pi 官方命令：

   ```text
   pi install "<agent-dir>/packages/pi-persona-rewind"
   pi install "<agent-dir>/packages/pi-remote-access"
   ```

   将占位符替换为新机实际绝对目录；本地包原地加载，不会由该命令复制文件。不要同时登记包及其单文件入口。Pi Web 如未提供独立 `pi` CLI，可使用 Plugins UI；不要为此换成另一个不共享配置的宿主。
4. 正常 `/reload` 后核对命令发现，再在隔离对话核 `/persona list`、`/rewind list`。不要在用户原会话试回退；回退上下文不会撤销工具对文件产生的效果。
5. `/remote` 源码恢复不等于开放远程访问。默认保持宿主本机绑定；需要远程时由用户重新配置认证、网络与 Tailscale 登录。包可读写本机凭据仓，复制目录本身不调用这些操作；本次未加载或执行扩展。二维码依赖 `qrcode-generator` 是可选项，缺失时仍显示网址，不为恢复基本能力强装依赖。

人格文件、旧工作台规则、模型账号及远程密码均须另行私人备份或重新配置。当前宿主版本参见恢复总览；本轮只核源码复制、相对导入和清单，不证明格式化后安装、宿主 API 兼容或远程连接已经通过。
