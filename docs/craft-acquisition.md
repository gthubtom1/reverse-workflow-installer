# 从精确公开 pin 获取 Craft 和 reverse

`acquire_craft.py` 是换机下载准备入口，不是 installer、通用 updater 或自动选择 latest 的注册中心。它将我方 Craft 原生 bundle 与有新 R46 合同的 reverse 源准备到显式全新目录，再生成已有 installer 的 `--craft-bundle` / `--reverse-root` 参数。Pi/Node 继续通过现有官方 acquire-pi 流程获取，不重写 npm 安装或复制个人 profile。

本增量只完成离线元数据/文件/失败路径验证。**当前仓库仅提供不可下载的 `.example`，没有真实可用的 release pin；真实发布后必须由发布流程填精确记录并运行公开 acquisition 验收。** 单独 push main 不等于资产、reverse v1.9.0 或公共换机安装已可用。

## 一条准备命令

本 acquisition 入口仅支持 **Windows x64**。非 Windows/x64 的 CLI 与 worker 返回 `code: unsupported-platform`，在网络、stage 创建和任何进程启动前拒绝；没有运行时开关可以绕过。普通 Linux/macOS core installer 不受影响。

在 Windows x64 的 fresh clone 根目录、Python 3.11+ 与 Git 已安装时，使用发布后实际填写的 pin：

```text
python -B scripts/acquire_craft.py --pin-file adapters/craft-pi/releases/windows-x64.json --stage ../craft-download --deadline-seconds 600
```

也可用 `--pin '<完整JSON对象>'` 明确传入同一 schema；与 `--pin-file` 互斥。stage 的父目录必须已存在，stage 本身必须不存在，禁止路径 symlink/junction。不覆盖用户目录、不复用未完成目录；失败残片留作诊断，下次选新的 stage。

成功时 `complete.json` 仅由外层 supervisor 在 worker 已退出、外层 Windows Job 清理确认、结果与包/源码身份再次一致后生成。失败、超时或 cleanup unknown 不写 complete。`acquisition-candidate.json` 只是 worker 候选结果，不是完成标记。

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
| craft | repository 固定 `https://github.com/gthubtom1/reverse-workflow-installer`；tag 固定 `craft-pi-v0.1.0`；实际 release commit（40位小写hex）、asset 文件名、GitHub asset_id（正整数）、发布ZIP SHA256、包根 craft-bundle.json 原始字节 manifest_sha256 |
| reverse | repository 固定 `https://github.com/gthubtom1/reverse-skill`；tag 固定 `v1.9.0`；实际 commit、当场取得的该 commit codeload ZIP archive_sha256、最终 R46 descriptor_sha256 |
| upstream | repository 固定 `https://github.com/storytold/craft-anything`，commit 固定 `0326b4de8051f85a0f3139cd82f88f76911e6a35`；这是 Craft 来源证明，不是我方修改版资产所在仓库 |

包版本号不等于 installer 0.7.0。不把我方资产定位到 upstream Craft release，也不拿公共 reverse 1.8.2 顶替新合同。真实资产名/commit/id/hash 须发布现场取得；当前 final descriptor 为 `3ad158f3341fd502d974ebb331e10d659e04c9b86f65ef2a1a1ced7cc60cfecf`，发布源码若变化必须经原流程重审，不自动改 source 身份。

GitHub 生成的 source ZIP 不承诺永久字节不变。本 pin 记录发布现场取得的精确 ZIP 摘要；将来 GitHub 重生成导致摘要变化时应拒绝并由发布维护者重新核验记录，不能默默接受或宣称该 archive 本来就是永久 immutable asset。

## 获取和验证顺序

1. 严格校验 pin，再通过公开 GitHub API 核两仓 release/tag → 精确 commit、release ID/正式非 draft/non-prerelease、正确 repository release URL。我方 asset 必须唯一，name/id/API URL/browser URL/GitHub digest 与 pin 一致；不使用 target_commitish 字符串代替 tag commit。
2. 下载我方精确 release ZIP 和 reverse 固定 commit 的 codeload ZIP，分别校验真实 SHA256。下载请求不读取/发送 GH_TOKEN、Authorization、cookies 或个人 MCP 配置。只允许 HTTPS、受限 GitHub/API/codeload/storage hosts，正常 release-assets.githubusercontent.com / objects.githubusercontent.com 存储跳转允许；跨仓库/API/commit路径跳转拒绝，跳转请求不转发鉴权头。
3. 复用既有 safe_extract_zip，先检查整包再提取，拒绝绝对/逃逸路径、链接、重复/大小写碰撞、加密、凭据路径及解压大小/文件数量超限。`.github` 等合法源码文档不被笼统排除。Craft ZIP 直接包含包根文件；reverse ZIP 必须只含 `reverse-skill-<exactcommit>/` 一个项目根。
4. 复用 `craft.bundle` 和 `craft.reverse_contract` 检查实际 manifest、平台、运行工件、patch/base、VERSION/R46四文件身份与 pin manifest/descriptor 摘要。
5. 在新 stage clone reverse 的精确 tag（禁交互/全局配置/项目hooks/子模块递归），核实际 HEAD 为 pin commit、工作树干净。`core.autocrlf=false` 不覆盖官方 `.gitattributes`；例如 `*.ps1 eol=crlf` 的 checkout 合法具有 CRLF，而 canonical Git blob/archive 可为 LF。通过 `git ls-tree -r -z <commit>` 核全部唯一、安全、普通 blob 路径，再一次 `git cat-file --batch` 逐个解析并计算实际 canonical blob SHA256，与固定 commit archive 的全部路径/原始 hash 精确比较；不对文本或二进制手动换行归一化、不取消比较、不修改官方 attributes。拒绝缺失/额外（含 ignored）文件、untracked、脏树、submodule/link。结果分别记录 `reverse_canonical_files`（git-commit-blob-sha256）与 `reverse_files`（checkout-raw-file-sha256）；实际 VERSION/descriptor/四 Markdown 文件仍在所获 checkout 上执行原 reverse_contract，不能拿开发机字节替代。选择 Git checkout 是为兼容现有 installer 的完整 reverse Git identity，不向解压目录伪造 .git 身份，不需新增 reverse-pin CLI 参数。
6. 再解析一次 release 元数据，确认本次获取过程中身份未变化；写候选、参数。外层核 cleanup 和文件身份后写 complete，其中保留发布 pin、API解析身份、实际 bundle/源码摘要及 qualification。

单下载体最多2GiB，API JSON最多4MiB，解压沿用既有2GiB/100000项限制。网络 socket timeout20秒只是一次I/O上限；整个下载/解压/Git流程被 `packaging_process.run_owned` 的外层 Windows Job 总wall deadline覆盖（默认600秒，允许1..600，内含有限cleanup）。内部 Git/cat-file 通过 `subprocess.run` 直接继承该 Job，不再调用嵌套 run_owned、不创建新session/group/Job。单条Git timeout失败不认证清理；外层必须观测整个Job退出才可完成。持续慢流、Git shell与其监听后代也受外层Job控制。本入口明确不提供 Unix acquisition，避免把自身创建新session导致的后代遗漏称为外部逃逸。

## 接口与验证边界

`scripts/acquire_craft.py:validate_pin` / `resolve_pin` 为本入口精确 schema 和 GitHub 元数据校验；`craft.pinned_release` 只委托该解析器，不改变已冻结 installer plan/apply/verify/entry 合同函数。`acquire` 支持测试注入元数据/下载/checkout，生产 CLI 使用真实 HTTPS 和受管 Git。

离线 `tests/test_craft_acquisition.py` 使用结构化 GitHub 响应和真实 toy ZIP/文件、本地真实 Git repo/tag/attributes（tracked LF ps1、实际 checkout CRLF、二进制不变）、局部进程/慢HTTP流及 Windows 外层Job内实际Git shell/监听后代，验证正例、混错repo、移动tag、错commit/id/hash、篡改、ZIP逃逸、旧reverse、部分失败、fresh-root保护、正常存储跳转与清理。相关原 pinned_release 用例更新为我方资产仓库的新完整 pin 语义。它们不证明 v1.9.0 或 Craft release 已存在，也不等于真实公开下载/模型/业务任务已验收。

发布后主流程仍须：填真实 pin → 在全新 stage 实际跑该命令 → 使用官方获取的完整 Pi 参数生成 installer schema2 plan → 独立安装/verify/entry及适用任务/更新恢复验收。发布凭据和私有配置不进入 pin、包或公共记录。
