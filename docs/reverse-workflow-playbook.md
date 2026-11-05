# Reverse 工作流使用手册

这份手册解决一个实际问题：安装完成以后，面对一个 EXE、DLL、APK、JS 应用或协议样本，应该先发什么，看到什么结果后再发什么，什么时候让 REA 分析，什么时候进入动态验证，什么时候开始独立实现。

安装仓库负责把组件接到 Pi/Codex；真正的专业流程由已安装的 `reverse-skill` 执行。下面的提示词可以直接复制到 Pi Web 或 Codex。

## 先记住三件事

```text
reverse-workflow = 唯一入口
reverse-skill    = 路由、case、阶段和证据总控
REA              = PRIMARY 选定后的定点分析执行器
Spec Kit         = 独立成果项目的规格、计划和任务
```

REA 不是第二个 router。遇到逆向任务，先进入 `/skill:reverse-workflow`，由原生 router 选择 PRIMARY，然后 PRIMARY 根据当前 Evidence 创建 bounded work item，再调用 REA。

一次 work item 只回答一个 Evidence 问题。例如：

```text
确认这个字符串被哪些函数引用
确认这个函数的返回值和调用者
确认这个 PE 的导入表和证书状态
确认一次运行时行为
```

不要把“全量字符串、全量反编译、动态运行、网络观察”塞进一个 work item。Ghidra、IDA、radare2、capa 等重型 provider 默认一次只运行一个；超时后先清理，再决定下一步。

## 安装完成后的首次使用

在安装器仓库执行：

```text
python scripts/install.py verify --root <安装根>
python scripts/install.py accept --root <安装根>
```

然后重启或 reload Pi/Codex。新会话里先输入：

```text
/skill:reverse-workflow
```

再发送具体任务。`/skill:reverse-workflow` 只负责进入工作流；它不是完整任务描述。只发送技能命令时，旧会话可能会继续旧上下文，所以新任务最好明确写出目标对象和范围。

## 一次任务的标准生命周期

```text
0. 目标和范围
1. Triage 分诊
2. Static 定向静态分析
3. Dynamic 动态验证（只有静态证据不足时）
4. Synthesis 汇总
5. 独立实现/行为对比（需要时）
6. 报告、journal 和收尾
```

每一阶段结束时，智能体应该报告：

```text
已观察 Observed
推断 Inferred
未知 Unknown
Evidence
当前 Finding
下一步 Path
```

你不需要手工选择每一个工具。你需要选择的是任务阶段和要回答的问题。工具由 PRIMARY 和 REA 按 Evidence 选择。

## 第一次分析一个新目标

新目标的第一条完整提示词使用下面模板：

```text
/skill:reverse-workflow

请分析下面的目标，先做只读离线分诊，不要执行目标程序，不要修改原文件，不要联网。

目标对象：
[绝对路径或成果项目中的相对路径]

任务范围：
[只读结构分析 / 协议分析 / 功能还原 / 独立复刻 / 行为对比]

我希望回答的问题：
[一个具体问题，例如“它是否包含授权校验，授权状态如何影响功能”]

请先完成：
1. 读取本机安装回执；
2. 读取 reverse-skill 的 RULES.md 和 MASTER-ROUTING.md；
3. 运行原生 router 选择 PRIMARY；
4. 恢复或创建当前 case；
5. 只做 bounded triage；
6. 报告 Observed、Inferred、Unknown、Evidence 和下一步 Path。

执行约束：
- REA 由 PRIMARY 在需要时调用；
- 一个 work item 只回答一个 Evidence 问题；
- 默认只使用一个重型 native provider；
- 不运行无界限全量扫描；
- provider 超时或中断后先清理进程；
- 不要在没有证据时直接修改或补丁目标。
```

这一轮你只需要等待分诊结果。不要马上追加“继续全量分析”。先看它是否已经确认了文件类型、架构、壳、导入/导出和主要组件。

## 分诊结果出来以后怎么继续

如果分诊已经得到清晰入口，发送：

```text
继续当前 case。

请根据刚才的 E-triage 创建下一个 bounded work item，只回答这个问题：
[写一个问题]

优先使用 REA 做定向分析，返回：
- Evidence
- Finding
- Unknown
- provider/session
- elapsed 和 peak memory
- cleanup 状态
- 下一步 Path

不要扩大到全量反编译，也不要启动第二个重型 provider。
```

常用问题示例：

```text
确认 `license.cdk` 的所有引用函数和调用者。
```

```text
确认 `check_hash` 命令对应的函数和它调用的服务层函数。
```

```text
确认这个 URL 是更新检查、业务请求还是遥测请求，并列出引用它的函数。
```

```text
确认这个函数的返回值结构，重点关注成功、失败和未知状态的分支。
```

## 未加壳 PE/ELF/Mach-O

未加壳目标一般按下面路径走：

```text
Triage
  -> imports/exports
  -> strings/URLs/resources
  -> 定位关键函数
  -> REA 定点 dossier
  -> 必要时动态验证
```

提示词：

```text
当前目标已初步判断为未加壳原生二进制。

请进入 Static 阶段，但只分析当前 Evidence 指向的关键路径：
1. 记录 imports/exports 分类摘要；
2. 定位 [函数/字符串/API] 的引用；
3. 用 REA 分析已经确认的目标函数；
4. 不做全量 decompile_all；
5. 给出函数地址、调用者、返回值、关键分支和 Unknown。
```

如果需要分析多个函数，明确限制数量：

```text
只分析以下三个已确认函数：
- [地址或符号]
- [地址或符号]
- [地址或符号]

请使用小批量 bounded work item。不要分析其他函数。
```

## 有壳、强混淆或导入表异常的 PE

加壳目标不能直接把乱码 IAT 当结论。正确顺序是：

```text
确认壳特征
  -> 尝试脱壳或记录失败
  -> 尝试修复 IAT
  -> 修复失败就记录 E-iat-repair-fail
  -> 转 Dynamic/API 断点
```

提示词：

```text
当前目标疑似加壳或强混淆。

请先只做可行性判断：
1. 说明壳/混淆证据；
2. 判断当前 imports 是否可读；
3. 如果不可读，记录 quality=unreadable/packed；
4. 说明脱壳或动态 API 观察哪个是合法前提；
5. 不要把乱码 IAT 当成能力结论；
6. 不要无限重试静态修复。

如果 IAT 修复失败，记录 E-iat-repair-fail 并转入动态路径。
```

如果用户明确要求“现在就看 IAT”，即使它不可读，也应该执行并标记质量：

```text
按当前要求记录 IAT 结果，但明确标记 quality=unreadable/packed。
不要根据这份乱码表判断样本没有网络、文件或注入能力。
```

## .NET/C# 程序

.NET 没有传统 native IAT 时，使用等价锚点：程序集、元数据、IL、引用和敏感 API。

```text
/skill:reverse-workflow

请分析这个 .NET/C# 目标。

先完成：
- 程序集身份和版本；
- 类型/方法入口；
- 程序集引用和 P/Invoke；
- 关键字符串和配置；
- 授权、网络、文件和进程相关 API。

把 IL/元数据摘要写入 E-imports 等价证据槽，再选择一个具体方法做定点分析。不要因为没有传统 IAT 就跳过导入锚点。
```

## APK/Android

APK 任务先走 APK PRIMARY，不要在通用 R0 里直接开 JADX。分阶段提示词：

```text
请对这个 APK 做离线分诊：
- manifest、组件、权限、签名；
- DEX 数量和架构；
- native .so；
- 网络域名和证书配置；
- 可能的授权、设备绑定和完整性检查。

先不要改包、重签名或安装。输出 E-triage 和下一个 bounded work item。
```

如果 APK 需要 JADX，而本机 accept 报告缺少 JADX provider，先把它作为明确缺口记录，不要把普通 JADX JAR 自动当成官方 provider。

## JavaScript/Electron/Tauri 前端

先区分“静态前端资源”和“native backend”。

```text
请先判断这个目标是 Electron、Tauri、普通 Web bundle 还是其他桌面框架。

先做静态分析：
- 入口文件和模块图；
- IPC/preload/native boundary；
- API、路由和配置；
- source map 是否存在；
- 只选与当前问题相关的 source_paths。

不要执行应用，不要把静态路由候选当成已达成行为。
```

如果是 Tauri/Rust，前端命令名只能作为线索；需要 REA 对 native command 或调用者做定点确认。

## Dynamic 什么时候开始

只有静态分析无法回答关键问题时才进入 Dynamic，例如：

```text
- 关键字符串是运行时解密的；
- 静态调用链无法确认实际分支；
- 需要确认某个网络请求是否真的发生；
- 需要确认程序是在内存中解包还是直接从磁盘读取；
- 反调试导致静态证据无法闭合。
```

提示词：

```text
静态 Evidence 目前不足以确认：[具体未知项]。

请创建单独的 Dynamic bounded work item：
- 目标进程：[明确目标]
- 观察点：[API/函数/网络/文件/窗口]
- 预期 Evidence：[具体输出]
- 时间盒：[例如 180 秒]
- 结束条件：[具体条件]
- cleanup：必须确认目标和 provider 进程状态

不要同时运行第二个重型静态 provider。
```

动态阶段结束后，发送：

```text
根据 Dynamic work item 的实际输出，回到 Synthesis。
请把静态假设、动态观察和仍未知内容分开，给出：
Evidence -> Finding -> Path
不要把一次运行结果扩展成所有版本、所有环境都成立的结论。
```

## 看到失败、超时或内存异常时怎么发

不要发送“再试一次”。使用：

```text
当前 provider/work item 已失败或超时。

请先：
1. 报告错误和最后一个有效 Evidence；
2. 确认 provider/session 是否关闭；
3. 确认没有遗留进程；
4. 将 work item 标记为 timed_out、failed 或 blocked；
5. 说明换方法的 Evidence 依据；
6. 再提出下一个 bounded work item。

禁止重复完全相同的命令和参数。
```

如果是进程问题：

```text
先只做 provider cleanup，不开始新分析。
列出 case、work item、PID、子进程、cleanup 结果和剩余 PID。
清理未确认完成前保持 blocked。
```

## 已有项目如何继续

继续旧项目时不要重新说“分析这个程序”。使用：

```text
/skill:reverse-workflow

继续当前成果项目和已有 case。

请先读取：
- scope.md
- timeline.md
- workitems.md
- evidence/
- notes/
- 上次报告
- Spec Kit 的 feature、plan、tasks（如果已有）

先报告：
- 已验证内容；
- 失败内容；
- 未知内容；
- 当前 work item；
- 上一次停止位置；
- 下一步唯一 Evidence 问题。

不要重新解包，不要重复已经通过的分诊，不要创建第二个 case。
```

## 分析完成以后如何进入独立实现

当你已经确认了一个功能的行为，再进入 Spec Kit/独立项目：

```text
请把刚才已经有 Evidence 支持的功能做成独立实现。

先创建或恢复成果项目的 Spec Kit feature/plan/tasks，然后明确：
- 原版行为规格；
- 已确认输入输出；
- 错误和边界行为；
- 当前 unknown；
- 独立实现任务；
- 原版对照测试。

不要把未验证的推断写成需求事实。
先实现最小已验证功能，再做原版对照。
```

原版对照：

```text
请对原版和独立实现执行行为对比。

使用相同输入和相同环境，逐项记录：
- 输出；
- 文件变化；
- 网络观察；
- 错误；
- 退出状态；
- 未执行项；
- 不能比较的环境差异。

通过、失败和未知分开写，不要用“基本一致”代替证据。
```

## SkinForge 2.8.1 这类任务的继续模板

当前已有案例可以这样恢复：

```text
/skill:reverse-workflow

继续 SkinForge 2.8.1 已有 case，不创建新 case。

项目：
D:\Project\lol-hf

case：
D:\Project\lol-hf\work\skinforge-2.8.1

目标副本：
D:\Project\lol-hf\work\skinforge-2.8.1\extracted\skinforge.exe

请先读取 scope.md、timeline.md、workitems.md、analysis/、evidence/ 和上次报告。

第一步只做一个 bounded work item：
用 REA open_binary 打开 skinforge.exe，然后定点分析：
- fcn.1404d9710
- fcn.1408ce8b0

问题：确认授权状态解析函数与上层授权门之间的调用关系。

返回：
- Evidence
- Finding
- Unknown
- provider/session
- 资源状态
- cleanup 状态
- 下一步 Path

不要运行全量 Ghidra、全量 capa 或第二个重型 provider。
```

## 什么时候你需要继续发消息

每个阶段通常只需要一条推进指令：

```text
初始提示词 -> 等待 triage
```

```text
triage 结果 -> 指定一个 Evidence 问题
```

```text
static 结果 -> 继续定点分析或转 dynamic
```

```text
dynamic 结果 -> 回到 synthesis
```

```text
规格确认 -> 进入 Spec Kit 独立实现
```

如果智能体已经明确报告“当前唯一下一步由 gate 决定”，你不需要人为选择菜单；让它继续即可。如果它报告两个证据充分、结果不同的分支，再选择其中一个。

## 不要这样使用

```text
分析一下这个软件
```

问题：目标、范围、问题和输出都不明确。

```text
全量逆向，所有功能都还原出来
```

问题：没有阶段、预算和验收标准，容易启动多个重型 provider。

```text
再跑一次 Ghidra / r2 / capa
```

问题：没有说明上一次失败原因，也没有 cleanup 和新的 Evidence 问题。

```text
看到了 license、token、update 字符串，所以它一定有这些功能
```

问题：字符串只能作为静态线索，不能单独证明功能可达或真实运行。

```text
直接改原文件，然后测试
```

问题：没有保留原始样本、没有副本边界，也无法准确比较前后行为。

## 结束一个阶段时应看到的结果

一个合格的阶段结果至少应包含：

```text
当前 case：明确
当前 work item：明确
目标 hash：明确
实际 provider：明确
实际执行动作：明确
Evidence：有编号或可定位产物
Finding：和 Evidence 对应
Unknown：没有被隐藏
资源状态：时间、内存或 provider 状态
cleanup：已完成或明确 blocked
下一步：一个具体 Path
```

如果缺少这些字段，不要急着进入下一个重型工具。先让智能体补齐当前阶段状态。
