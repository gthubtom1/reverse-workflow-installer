# pi-remote-access

独立恢复 Pi Web 的 `/remote`，来源固定为 pi-seep-ext `2742f417`。包清单仅声明 `extensions/remote.ts`，不加载 persona、rewind、skills 或其他扩展。无需构建，也无需 npm install 即可加载。作为用户自定义本地包注册，工作台更新会保留该声明；完整插件源码随本包保留。

## 功能

- `/remote`、`/remote menu`：局域网、Tailscale、密码、自检、二维码菜单；沿用普通配置的 lastMode 排序。
- `/remote lan`：枚举并探测局域网地址，提供手机访问网址。
- `/remote tailscale`（`ts`）：读取 Tailscale 状态或网卡地址，报告访问网址；确认并成功保存后可启用 MagicDNS allowedHosts。
- `/remote check`：绑定、端口、地址可达性及密码是否开启。
- `/remote qr`：切换二维码显示。qrcode-generator 通过延迟导入作为可选能力；缺失时保留网址，不影响扩展加载。未声明必须安装的依赖。
- `session_start`：设置状态键 `command:/remote`，供 Pi Web 渲染为点击入口。

恢复版只执行 `tailscale status --json`。不执行 `tailscale up`、tasklist 或托盘启动；连接操作交给本机客户端。需要登录时只提示打开本机 Tailscale 客户端，不在会话、通知或其他 UI 输出可能含令牌的 AuthURL。原始启动源码完整保留在 `upstream/remote.ts.txt`，不属于扩展加载入口。

## 密码与配置

密码菜单只有「状态 / 生成 / 关闭」。状态与生成结果仅显示是否生效、凭据仓引用 `<CRED:pi-web-remote/password>` 及本机文件路径，不把密码值发送到 sendMessage、notify、console、状态按钮或二维码。路径引用用于本机凭据工具定位，不是把密码嵌入网址。不会提供显示密码的会话命令。

默认凭据服务目录：`~/.seep/secrets/pi-web-remote/`。`SEEP_CRED_ROOT` 覆盖 `~/.seep/secrets`，最终目录为 `<SEEP_CRED_ROOT>/pi-web-remote/`，支持 `~` 前缀。

| 文件 | 含义 |
| --- | --- |
| `password` | cred-store 兼容的普通值文件：密码原文，无 JSON 包装、无附加换行；只能用本机凭据工具读取 |
| `state.json` | `version: 1`、`passwordState: enabled/disabled`；enabled 还包含密码文件的 sha256 一致性标记 |

新密码由 node:crypto 的 randomInt 安全随机生成，默认 24 字符。密码及状态采用同目录临时文件加 rename 写入；临时密码也仅落在上述服务目录。两个文件全部提交成功后才更新当前进程的 PI_WEB_PASSWORD。任何写入失败均报告失败，并保留原进程环境值。若密码文件成功而状态写入失败，标记缺失或摘要不符会阻止重启恢复；此时需要本机再次成功生成，扩展不会假报成功。

只有明确 enabled 且摘要匹配的仓内密码才能恢复；不覆盖已有的非空进程密码。单独存在 `password` 文件不会启用认证。关闭操作必须确认，先持久写入 disabled，再清除当前进程密码。即使 password 文件留在仓内，重启或 session_start 也不会恢复它；之后明确选择生成才重新启用。该行为只影响 Pi Web 所在进程，不修改系统持久环境变量。

普通配置沿用 `<PI_CODING_AGENT_DIR>/pi-web-remote.json`，默认 agent 目录解析规则与上游一致。扩展只管理 `lastMode`、`allowedHosts`，保留已有未知字段，禁止 password 补丁。无效 JSON、非对象 JSON 或不可写文件均拒绝覆盖。旧 `password` 为 `null` 或空字符串时，正常保存普通字段并移除该空旧字段，不再写回 password；非空字符串（含纯空白）或不明类型仍拒绝覆盖，交给主流程另行处理。加载时不修改文件，也不自动启用旧密码。本次没有读取或改写真实文件。

## 验证边界

在本包目录运行：

```text
node --experimental-strip-types --test test/remote.test.mjs
```

20 项测试通过，覆盖包清单、注册、菜单、session_start 按钮、LAN/Tailscale/check/qr、规范凭据引用、消息和日志出口、独立于当前密码的 AuthURL 不泄露、凭据落盘及重启、写入失败保留 env、未知字段保留、空旧密码字段移除、非空或不明类型旧密码拒写、坏 JSON 拒绝覆盖、旧密码不启用、关闭确认及重启不复活。

测试使用注入的独立环境对象和假的 PI_CODING_AGENT_DIR，所有夹具均在 `test/.runs/` 临时隔离凭据仓内部创建并清理；仅合成密码，不读取真实凭据、不改 process.env。网络探测和 Tailscale 全为 mocks，exec mock 拒绝 status 之外的命令；未执行真实网络配置命令。现有 Pi SDK 1.4.0 的宿主集成与 Pi Web 点击界面验证由主流程负责，本包未宣称完成该验证。
