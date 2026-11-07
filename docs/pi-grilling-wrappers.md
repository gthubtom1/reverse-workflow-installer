# Pi Grilling 独立包装器

这两个脚本只管理独立输出目录中的 Pi 包。官方 `grilling`、`domain-modeling`、`grill-me`、`grill-with-docs` 是只读输入；脚本不安装官方技能，不联网，不运行 npm/uv/setup/init，也不写 Pi settings、profile 或安装器 receipt。Python 核心安装事务不自动登记这个可选包；部署时按下述两种加载方式选一种。

运行需要 Node.js 18 或更新版本；没有第三方运行依赖。所有路径参数相对于命令的当前工作目录解析，带空格的路径需要加引号。

## 独立命令

在 installer 仓库根执行。官方输入默认使用 Node `os.homedir()` 下的 `.agents/skills`，输出必须显式指定，并与官方目录完全分离：

```text
node scripts/pi-adapt-grill-skills.mjs --output-root ../workflow/pi-grilling --json
node scripts/verify-pi-grill-skills.mjs --output-root ../workflow/pi-grilling --json
```

使用其他官方输入目录时，两条命令必须使用相同参数：

```text
node scripts/pi-adapt-grill-skills.mjs --skills-root ../official-skills --output-root ../workflow/pi-grilling --json
node scripts/verify-pi-grill-skills.mjs --skills-root ../official-skills --output-root ../workflow/pi-grilling --json
```

兼容一个官方输入根的位置参数，例如：

```text
node scripts/pi-adapt-grill-skills.mjs ../official-skills --output-root ../workflow/pi-grilling
```

| 参数 | 契约 |
|---|---|
| `--skills-root <path>` | 可选，只读官方输入根；与位置参数二选一 |
| `--output-root <path>` | 必填，独立 installer-owned 包根；首次必须不存在或为空目录 |
| `--json` | 可选，stdout 输出单个 JSON 对象，告警和错误放在对象中 |
| `--help` | 单独使用，打印帮助，不读取输入或写文件 |

参数采用上面的空格分隔形式，不支持 `--key=value`。未知参数、重复参数、缺少值或缺少输出根返回 `2`。不提供隐式同级输出、`--force`、自动接管目录或绕过冲突的参数。官方目录更新后，使用同一条生成命令更新自有包，再运行校验命令。

| 退出码 | 含义 |
|---|---|
| `0` | 生成/更新成功或已经一致；对 verifier 表示本地结构、模板和哈希一致 |
| `1` | 输入缺失/格式错误、路径或所有权冲突、校验失败、I/O 错误 |
| `2` | 命令行参数错误 |

无 `--json` 时，正常信息在 stdout，告警和错误在 stderr。legacy companion 告警本身不改变成功退出码。

## 输出与主安装器接口

输出目录恰好包含以下四个文件：

```text
pi-grilling/
├── package.json
├── pi-grilling-manifest.json
├── pi-grill-me/
│   └── SKILL.md
└── pi-grill-with-docs/
    └── SKILL.md
```

`package.json` 是私有本地包 `@reverse-workflow-installer/pi-grilling-wrappers`，其 Pi 资源声明固定为：

```json
{
  "pi": {
    "skills": [
      "./pi-grill-me/SKILL.md",
      "./pi-grill-with-docs/SKILL.md"
    ],
    "extensions": [],
    "prompts": [],
    "themes": []
  }
}
```

输出若位于实际 Pi agent 的 `skills/pi-grilling/` 子目录，Pi 按官方 skills 发现规则递归加载其中两个 `SKILL.md`；不要再把同一目录登记到 packages，以免重复。输出若在其他位置，只向 Pi 注册返回的 **`outputRoot` 包目录**。不要注册 `package.json` 文件、installer 仓库、agent-plugins hub 或整个官方 skills 根来代替该输出包。生成命令不修改资源配置，也不会让 Pi 自动加载外部目录。

需要外部 package 注册的部署方应先检查生成与校验的退出码及 `ok`，再将 `outputRoot` 作为本地 package source 合并到其获授权的配置，保留其他资源与用户编辑，并记录自身的部署/恢复归属。相对 package source 由 Pi 按 settings 所在目录解析；自动集成可直接使用 JSON 返回的绝对 `outputRoot`，避免把脚本运行目录误当作 settings 目录。

独立使用者在已授权修改**成果项目**配置时，也可从成果项目运行 Pi 官方的 `pi install --local <输出包的绝对路径>`。该命令会修改成果项目 `.pi/settings.json`，不属于上述生成/校验脚本。完成注册后在实际宿主 reload 或重启，再分别检查 `/skill:pi-grill-me` 与 `/skill:pi-grill-with-docs`。静态 verifier 不替代宿主加载或访谈行为验收。

JSON 的成功结果和检查失败结果包含：

| 字段 | 含义 |
|---|---|
| `ok`, `mode` | 成功布尔值；模式为 `adapt` 或 `verify` |
| `officialRoot`, `outputRoot` | 解析后的绝对输入根与输出根 |
| `packagePath`, `manifestPath`, `skillPaths` | 自有 package、归属清单、两个技能文件的绝对路径 |
| `changed` | 计划生成/更新的输出相对路径；首次为四个文件，幂等时为空；verifier 中表示不一致项，不表示执行了写入 |
| `warnings`, `failures` | 告警与失败原因数组 |
| `writePhaseStarted` | 是否进入写入阶段；`false` 表示未进行输出写入，`true` 不保证四个文件都已写完 |
| `upstreamAuthentication`, `hostValidation` | 固定为 `not-performed` |

参数解析失败时 JSON 仅含 `ok`、`mode`、`warnings`、`failures`、`writePhaseStarted`；路径尚未建立，调用方不得假定路径字段存在。

## 输入和 legacy drift

`grilling/SKILL.md` 与 `domain-modeling/SKILL.md` 必须存在。两个官方 companions 可以完全缺席；如果其目录已存在，就必须有可读且格式有效的 `SKILL.md`。所有已存在的四份技能文件都记录原始字节 SHA-256；缺席 companions 记录为 `null`，不会自动创建。

带旧 `<!-- pi-adapter:` 标记的官方 `grill-me`、`grill-with-docs` 会产生 **legacy drift** 告警，但允许生成和校验新包。这两个文件保持原样，包装器只加载 `grilling` 与 `domain-modeling`。如果标记出现在这两个必需核心技能中，则停止并返回非零；脚本不会自行修复任何官方文件。

输入允许可读的目录符号链接/junction、文件符号链接和硬链接，以兼容 `npx skills` 的只读链接布局。真实目标必须是普通文件。悬空输入链接、目录/FIFO 充当技能文件、非法 UTF-8、空正文、错误的 name 或 description 都会失败。

为保持零依赖，frontmatter 使用明确受限的 YAML 解析：平铺标量、单/双引号，以及缩进的 `|`/`>` 块。支持 BOM、CRLF、注释；嵌套 metadata、数组、锚点、其他未支持语法和重复字段会拒绝。合法上游文件若采用未支持的 YAML 结构，也会安全停止，需要先扩展解析器，不能为通过检查而重写官方文件。

## 所有权、路径隔离和更新

所有输入和输出检查先完成，才创建输出目录或打开文件写入。输入缺失、格式错误和预先存在的路径/所有权冲突返回非零，并保持零输出写入。verifier 始终只读。

输出根与官方逻辑路径及已解析的实际路径不得重合、互为祖先或后代。输出根、祖先、包装器目录以及四个受管文件都拒绝符号链接/junction，包括悬空链接；输出普通文件拒绝多重硬链接。目录的 `nlink > 1` 不构成错误，因为这是 POSIX 的正常目录语义。Windows 输出还拒绝设备命名空间、ADS、保留设备名、非法字符及末尾点/空格，在创建父目录前报告路径错误。

归属清单记录 owner、schema/template 版本、输入逻辑/实际路径、四份官方 SKILL.md 的本地哈希与 legacy 状态，以及两份包装器和 `package.json` 的哈希。清单自身也有摘要，采用排序 JSON、固定换行且无时间戳；相同输入与路径产生相同字节，重复执行不重写文件。

更新前，当前四个文件必须匹配已记录的归属、摘要与已知生成模板。用户编辑、文件缺失、额外文件、无清单旧包装器、未知 owner/schema/template 或清单被编辑都会阻止整次更新；不会覆盖、删除或自动收养这些内容。仅有 pi-adapter 标记不能证明 installer 所有权。

旧 `templateVersion: 1` 的三文件清单可升级：必须仍符合旧版模板和哈希，而且 `package.json` 尚不存在。即使现有 package 的字节刚好与新模板一致，也不会自动接管它。当前输出使用 `templateVersion: 2`，且 package 纳入归属清单。

官方输入发生合法变化时，旧输出的 verifier 会失败；重新生成会更新仍由 installer 拥有的输出，再执行 verifier。若要迁移官方根或搬动输出包，使用新的空输出根重新生成；不要手改清单路径或摘要。遇到用户编辑冲突时，保留原目录，另选新的空输出根；检查链接后如需清理，应移动到回收站。

## 验证范围与故障恢复

清单是本地一致性记录，不是签名、上游身份认证或权限来源。脚本不遍历/认证官方技能的所有支持文件，不验证宿主资源加载，也不证明模型遵守了访谈流程。

写入前再次执行完整 preflight，逐文件打开时使用独占新建或不截断的已有文件句柄，重新检查原始字节与链接状态。调用方必须串行生成，避免并发编辑和目录/链接替换。Node 路径 API 不提供完整的跨平台目录句柄事务，因此不能把此实现当作对抗并发恶意文件系统替换的隔离边界。

四文件更新不是原子事务。manifest 最后写入；磁盘故障、中断或写阶段并发变化可能留下部分输出，此时返回非零且 `writePhaseStarted: true`。不要自动注册这个输出或伪造清单恢复成功。保留现场，使用新的空输出根重新生成并通过 verifier 后，由主安装器切换注册。

## 离线测试

从 installer 根运行：

```text
node --test tests/pi-grill-skills.test.mjs
```

夹具只写本仓 `.local/tests/`，不读取真实 profile、不联网、不调用真实安装命令。测试结束将本次夹具目录移动到 `.local/tests/.recycle/` 留存失败证据，不执行永久删除。

测试覆盖官方核心/companion/资源字节不变、legacy 告警、缺失/格式错误/冲突零写入、确定性与幂等、合法更新、旧清单升级、四文件逐项手改/缺失/链接保护、清单与模板反例，以及 CLI JSON 契约。POSIX FIFO 用例在 Windows 跳过；POSIX 上缺少系统 `mkfifo` 时明确跳过，其他链接用例仅在平台不允许创建该类链接时跳过。Windows 通过不能替代 Linux 实测；实际宿主加载和最终集成审查由部署主流程分别记录。
