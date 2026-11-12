# 从精确公开 pin 获取 Craft 和 reverse

`acquire_craft.py` 是换机下载准备入口，不是 installer、通用 updater 或自动选择 latest 的注册中心。它将我方 Craft 原生 bundle 与有新 R46 合同的 reverse 源准备到显式全新目录，再生成已有 installer 的 `--craft-bundle` / `--reverse-root` 参数。Pi/Node 继续通过现有官方 acquire-pi 流程获取，不重写 npm 安装或复制个人 profile。

正式 [Windows x64 pin](../releases/windows-x64.json) 已固定真实 [Craft-Pi v0.1.1](https://github.com/gthubtom1/reverse-workflow-installer/releases/tag/craft-pi-v0.1.1) 资产和 [reverse v1.9.0](https://github.com/gthubtom1/reverse-skill/releases/tag/v1.9.0) 源码身份。它位于仓库根 `releases/`，不进入已冻结 adapter/runtime 资源。旧 `adapters/craft-pi/releases/windows-x64.json.example` 是历史结构模板，不是当前下载 pin；保留原字节以维持 native 资源来源证明。公共获取仅认证本次实际下载的包/源码身份，不替代 Pi/provider、安装或业务接受。

## 获取辅助工具维护版本

本页对应获取辅助工具 **0.1.1**，其独立源码发行身份为 [`craft-acquisition-v0.1.1`](https://github.com/gthubtom1/reverse-workflow-installer/releases/tag/craft-acquisition-v0.1.1)，实际 tag→commit 以 GitHub 为准。使用该 tag 或包含此修复的 main 运行下载辅助脚本；安装器核心正式身份仍为 **v0.7.0 / `70cf9c779ec0198eb725b864af868ee88bcfbce9`**，native Craft-Pi 为 **0.1.1**，reverse 固定 **1.9.0**。此辅助维护发行不移动 installer tag、不改 release pin、受管资源或 native ZIP。

原 v0.7.0 获取 CLI 的长 stage 与默认 Git 传输失败记录不能写成完整获取通过；修复辅助工具源码 A 的实际短 stage 全流程结果须另行记录，不能借用原源码 I 的成功身份。

reverse 的网络 Git clone 使用单次命令局部 `git -c http.version=HTTP/1.1`，用于提高默认协商路径的网络兼容性；它不保证所有网络都能完成 clone，连接仍可能被当前链路 reset。仅限制该公开 Git HTTP 请求的协议版本：不写全局 Git 配置、不关闭 TLS/证书校验、不加 token 或鉴权头、不新增失败重试/API fallback。后续本地 HEAD/status/blob/archive 命令不加此网络选项，所有 Git 仍继承外层 Windows Job。

## 一条准备命令

本 acquisition 入口仅支持 **Windows x64**。非 Windows/x64 的 CLI 与 worker 返回 `code: unsupported-platform`，在网络、stage 创建和任何进程启动前拒绝；没有运行时开关可以绕过。普通 Linux/macOS core installer 不受影响。

在 Windows x64 的 installer checkout 根目录、Python 3.11+ 与 Git 已安装时，先创建短路径父目录 `D:/cw`，再使用实际 pin（stage 须全新）：

```text
python -B scripts/acquire_craft.py --pin-file releases/windows-x64.json --stage D:/cw/craft-0.1 --deadline-seconds 600
```

也可用 `--pin '<完整JSON对象>'` 明确传入同一 schema；与 `--pin-file` 互斥。公开 CLI 在任何网络、进程启动或 stage 写入前检查解析后的绝对路径：stage 根最多 **64 个 UTF-16 code units**（emoji 等非BMP字符占两个单位）。超限返回 `code: stage-path-too-long` 和短根建议，只输出计数/上限，不回显完整个人路径。即使当前系统支持长路径，也仅按首版 portable Win32 范围处理，不改注册表或添加扩展路径前缀。

当前固定发行包已核：620项Craft ZIP的最长派生相对路径113 units，reverse ZIP的最长带commit前缀路径185 units；64-unit根下分别为178与250，低于259文件上限。这个固定根预算不是任何未来包都安全的承诺：下载并核SHA后、每次解压前仍逐项检查实际成员路径、目录/父目录（247上限）、单组件及24-unit atomic临时basename预算（完整路径259上限），保留 `.github`、许可证原名称与内容。Git pack元数据路径和结果写入也预检；新版本成员变长必须重新核预算，不能静默安装至中途才报IO错误。

stage 的父目录必须已存在，stage 本身必须不存在，禁止路径 symlink/junction。不覆盖用户目录、不复用未完成目录；旧失败残片保持原状，下次选新的短 stage。此门是下载stage门；安装根的 Craft plan/apply 路径门另见 [安装说明](craft-install.md)，两者不互相替代。

成功时 `complete.json` 仅由外层 supervisor 在 worker 已退出、外层 Windows Job 清理确认、候选 JSON/pin/argv 一致性检查通过后生成；全量文件 hash 在 worker 内核验，supervisor 不独立重算所有文件摘要。失败、超时或 cleanup unknown 不写 complete。`acquisition-candidate.json` 只是 worker 候选结果，不是完成标记。

`installer-options.json` 是两个准确参数的 JSON argv 数组；`installer-options.txt` 是供复制的当前平台命令行转义形式。将它与现有 acquire-pi 产生的精确 Pi 参数拼到 installer plan 中，另外明确提供自己的 root、agent、project 及 core 组件。示意：

```text
python scripts/install.py plan --components reverse,spec-kit,craft --client pi --root ../workflow --agent-dir ../workflow-agent --project ../my-project <installer-options.txt中的参数> <官方acquire-pi生成的Pi参数> --output .local/plan.json
python scripts/install.py install --root ../workflow --plan-file .local/plan.json --apply
```

尖括号部分必须换成生成结果，不是 shell 原生语法。脚本不启动 installer、不写宿主配置、不调用模型、不自动发布或切 active。原 core/all 不使用此下载入口，行为不变。

## Pin schema 1

顶层恰为 `schema_version`（整数1）、`craft`、`reverse`、`upstream`。严格 JSON 禁止重复字段、未知字段与缺字段。完整示例结构在 `adapters/craft-pi/releases/windows-x64.json.example`；其中 null 值故意使 validator 在网络/worker 启动前拒绝，不得把它改成假 commit、hash 或 URL 来通过。

| 对象 | 必需字段与来源 |
|---|---|
| craft | repository 固定 `https://github.com/gthubtom1/reverse-workflow-installer`；tag 固定 `craft-pi-v0.1.1`；实际 release commit（40位小写hex）、asset 文件名、GitHub asset_id（正整数）、发布ZIP SHA256、包根 craft-bundle.json 原始字节 manifest_sha256 |
| reverse | repository 固定 `https://github.com/gthubtom1/reverse-skill`；tag 固定 `v1.9.0`；实际 commit、当场取得的该 commit codeload ZIP archive_sha256、最终 R46 descriptor_sha256 |
| upstream | repository 固定 `https://github.com/storytold/craft-anything`，commit 固定 `0326b4de8051f85a0f3139cd82f88f76911e6a35`；这是 Craft 来源证明，不是我方修改版资产所在仓库 |

包版本号不等于 installer 0.7.0。不把我方资产定位到 upstream Craft release，也不拿公共 reverse 1.8.2 顶替新合同。正式 pin 的 Craft 资产 ID 为 `726614154`，ZIP SHA256 为 `3f354290ffc8d9e14e2bb917254c8fe28ed3c610ced614a8ffa75194579ad841`，来源 commit `010e2e323f912806f3fc3f2b17b1f9f06c29c944`；reverse commit `7cc3109bf14a570c9c852dc76cce05fff424e88c`，实际 archive SHA256 `763757fef2a934481b63959e2e96eeef0f1e0dfa90ffedf2c55ac178c9ec7842`，descriptor `47ee133eb10c0f53e7ca3be91413baa115f01282057d30c0c3e969b4b2b223f2`。模板里的旧 descriptor 不代表此正式 pin；发布后身份变化必须重新审查，不能自动刷新来掩盖漂移。

GitHub 生成的 source ZIP 不承诺永久字节不变。本 pin 记录发布现场取得的精确 ZIP 摘要；将来 GitHub 重生成导致摘要变化时应拒绝并由发布维护者重新核验记录，不能默默接受或宣称该 archive 本来就是永久 immutable asset。

## 获取和验证顺序

1. 严格校验 pin，再通过公开 GitHub API 核两仓 release/tag → 精确 commit、release ID/正式非 draft/non-prerelease、正确 repository release URL。我方 asset 必须唯一，name/id/API URL/browser URL/GitHub digest 与 pin 一致；不使用 target_commitish 字符串代替 tag commit。
2. 下载我方精确 release ZIP 和 reverse 固定 commit 的 codeload ZIP，分别校验真实 SHA256。下载请求不读取/发送 GH_TOKEN、Authorization、cookies 或个人 MCP 配置。只允许 HTTPS、受限 GitHub/API/codeload/storage hosts，正常 release-assets.githubusercontent.com / objects.githubusercontent.com 存储跳转允许；跨仓库/API/commit路径跳转拒绝，跳转请求不转发鉴权头。
3. 复用既有 safe_extract_zip，先检查整包再提取，拒绝绝对/逃逸路径、链接、重复/大小写碰撞、加密、凭据路径及解压大小/文件数量超限。`.github` 等合法源码文档不被笼统排除。Craft ZIP 直接包含包根文件；reverse ZIP 必须只含 `reverse-skill-<exactcommit>/` 一个项目根。
4. 复用 `craft.bundle` 和 `craft.reverse_contract` 检查实际 manifest、平台、运行工件、patch/base、VERSION/R46四文件身份与 pin manifest/descriptor 摘要。
5. 在新 stage clone reverse 的精确 tag（禁交互/全局配置/项目hooks/子模块递归），核实际 HEAD 为 pin commit、工作树干净。通过 `git ls-tree -r -z <commit>` 与 `git cat-file --batch` 逐项保留 canonical blob SHA256；再以原生 `git -c core.autocrlf=false archive --format=zip <commit>` 计算导出文件摘要，与固定 codeload archive 的全部路径/原字节 hash 精确比较。GitHub codeload 与 Git archive 都会应用仓内 `.gitattributes`：例如 `*.ps1 eol=crlf` 的导出和 checkout 合法具有 CRLF，canonical blob 可为 LF；不能把两种身份混同。不手工改换行、不取消比较、不修改来源 attributes。拒绝缺失/额外（含 ignored）文件、untracked、脏树、submodule/link。结果分别记录 `reverse_canonical_files`（git-commit-blob-sha256）、`reverse_archive_files`（git-archive-export-file-sha256）与 `reverse_files`（checkout-raw-file-sha256）；实际 VERSION/descriptor/四 Markdown 文件仍执行原 reverse_contract。Git checkout 保留 installer 所需完整 Git identity，不向解压目录伪造 .git，也不需新增 reverse-pin 参数。
6. 再解析一次 release 元数据，确认本次获取过程中身份未变化；worker 内核验全量文件 hash 后写候选、参数。外层核生命周期/cleanup 及候选 JSON、pin、argv 一致性后写 complete，不独立重算所有文件摘要；其中保留发布 pin、API解析身份、实际 bundle/源码摘要及 qualification。

单下载体最多2GiB，API JSON最多4MiB，解压沿用既有2GiB/100000项限制。网络 socket timeout20秒只是一次I/O上限；整个下载/解压/Git流程被 `packaging_process.run_owned` 的外层 Windows Job 总wall deadline覆盖（默认600秒，允许1..600，内含有限cleanup）。内部 Git/cat-file 通过 `subprocess.run` 直接继承该 Job，不再调用嵌套 run_owned、不创建新session/group/Job。单条Git timeout失败不认证清理；外层必须观测整个Job退出才可完成。持续慢流、Git shell与其监听后代也受外层Job控制。本入口明确不提供 Unix acquisition，避免把自身创建新session导致的后代遗漏称为外部逃逸。

## 接口与验证边界

`scripts/acquire_craft.py:validate_pin` / `resolve_pin` 为本入口精确 schema 和 GitHub 元数据校验；`craft.pinned_release` 只委托该解析器，不改变已冻结 installer plan/apply/verify/entry 合同函数。`acquire` 支持测试注入元数据/下载/checkout，生产 CLI 使用真实 HTTPS 和受管 Git。

离线 `tests/test_craft_acquisition.py` 使用结构化 GitHub 响应和真实 toy ZIP/文件、本地真实 Git repo/tag/attributes（tracked LF ps1、实际 checkout CRLF、二进制不变）、局部进程/慢HTTP流及 Windows 外层Job内实际Git shell/监听后代，验证正例、混错repo、移动tag、错commit/id/hash、篡改、ZIP逃逸、旧reverse、部分失败、fresh-root保护、正常存储跳转与清理。相关原 pinned_release 用例更新为我方资产仓库的新完整 pin 语义。它们不证明 v1.9.0 或 Craft release 已存在，也不等于真实公开下载/模型/业务任务已验收。

从正式 tag 的干净 checkout 在全新 stage 运行实际公共获取，记录真实 HTTP 下载、包/hash、Git 三种身份与 Job cleanup；这不等于在实体第二台电脑上测试。后续安装还须使用完整官方 Pi 参数生成 schema2 plan，再独立验证安装/entry及适用任务、更新恢复。发布凭据和私有配置不进入 pin、包或公共记录。
