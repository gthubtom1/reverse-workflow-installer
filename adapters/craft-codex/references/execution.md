# Codex 接续原 R46 的执行批次

本资源只由原 R46/Spec implement runner 为已接收、依赖已满足的任务批次读取。唯一主线仍是 reverse 原 router → PRIMARY → case/scope/Evidence → lead → Spec tasks；REA/其他分析工具生产事实，Craft 接续实现和检查。没有第二研究入口、第二任务账本或额外控制模型。

从活动 installer receipt 的 `craft.entry` 和 `craft.resources` 定位本资源；`craft.root` 是隔离 native bundle。要求 `scope.client=codex`、backend `craft-codex-app-server-v1`、permission `codex-dynamic-bounded-v1`，并通过其原 reverse Codex descriptor 与 bundle/resource/runtime hash 门。上游 Craft MCP 注册或 GUI 安装不能替代这个 receipt。

## 从正式 handoff 到执行

原 runner 先完成项目官方 prerequisites/checklists/hooks、任务依赖和 lead 接收决定。handoff 必须引用真实 case/scope/workitem、feature/spec/plan/tasks/acceptance、selected task IDs、原目标及外部 baseline、源码与检查基准、实际模型 profile、预算和单写 owner。字段以安装 bundle 的 `runtime.entry_protocol` 及 executor `--inspect` 为准，不从本文猜 schema，不用夹具或填假 hash 替代原权威输入。

按 receipt 中的准确 entry 执行：

```text
python -B <craft.entry> --check
python -B <craft.entry> --execute -- --inspect
python -B <craft.entry> --execute -- --validate <absolute accepted handoff JSON>
python -B <craft.entry> --execute -- --prepare <absolute accepted handoff JSON>
python -B <craft.entry> --execute -- --run <prepare 返回的 absolute execution JSON>
```

`--check`/`--inspect` 不启动 Builder；`--validate` 验证真实输入，`--prepare` 在新的 owned roots 写入绑定后的 policy、check plan 和 execution，模型调用数为零。`--run` 只接收准备后的输入，重核原 handoff/lead 决定及所有绑定；不能手改 execution 并刷新局部 hash 来认领批准。默认不跨 run 恢复旧 thread，也不搜索 latest session。

## Builder、工具和权限

复用固定 Craft `AcceptedResearch`、`RebuildRun`、bounded Engine、external checks 和 typed reports。一个 batch 只有一个活 owner 和一个 Codex Builder；每次执行或 refine 形成明确的 thread/turn 记录。Builder 只取得以下受控操作：`build_files_list`、`build_file_read`、`build_file_write`、`build_file_edit`、`build_command_run`、`build_checklist`。原 Engine 决定可读引用、授权写根、受保护路径、冻结 command/cwd 和效果，动态工具参数不授予新权。

Codex 受限 thread/turn 不得获得原生环境、shell/edit、浏览器、研究、任意 MCP、插件或协作工具旁路。工程读写与命令只通过六个受控操作。原生无环境文件操作、关闭的 Code Mode 与禁用委派的真实拒绝结果分别验证；资源辅助接口仍受 wall/deadline 与拒绝规则约束。driver 将动态请求交给原 bounded Engine；未知工具、跨 thread/turn、重复 call ID、native approval 或新权限请求均拒绝并停止。完整工具声明与实际可执行效果要分别检查，不能只看开关或把虚拟编排器的名称误当 OS shell。

驱动使用目标机原有 Codex CLI 的明确路径、完整版本和已验证 binary SHA，按 bundle 内 `codex-stock-bounded-v1` profile 固定启动受控 app-server。官方 `agents.enabled=false` 主开关禁止模型预设重新启用委派；空 environment、关闭 Code Mode/web/plugins/hooks 和逐次原 Gate 限定实际效果。额外声明可见不等于权限可执行，实际控制须由 native effect probe 和本批检查证明。正常账号由 Codex 通过选定配置根使用；安装器和执行桥不复制认证文件、不导出账号秘密。实际生效 provider/model/effort、拒绝切换和 usage 的证据来源必须在 driver contract 中明确；缺失量保留 unknown，不从请求值、消息文本或其他宿主补齐。

## 检查、失败与回传

Builder 仅在冻结计划与 refinement budget 内实现和修正；原 external baseline/check plan 及 required 预期不可改。冻结命令的实际输出、artifacts 和每个 external scenario/check 的结果进入 typed report。required unknown、unsupported、未执行或失败不能成为合格 candidate。

缺事实由 typed `return_summary` 回原 PRIMARY/REA；needs-spec 回原 Spec runner/lead，needs-scope 回 lead，未知权限或本批不支持能力返回 unsupported。新证据被原 owner 接收后，用新引用/decision/selection 和 fresh run root 再准备，不覆盖历史、不暗中 Study。Build/check/refine 不能关闭原 Evidence unknown 或双写 spec/tasks。

原 runner 对照 task IDs、源基准、diff、required checks、实际报告和 cleanup 接收候选，继续剩余 implement 与官方 converge，再由独立验证者验收。`accepted` 不由 backend 自行置真；Ready/Finished/TurnDone、exit 0 或源码 hash 单独均不表示成品通过。

## 预算、取消与退出

只接受本批明确批准且 profile 实际支持的预算模式。Codex 版本未支持强制单响应或总 token/费用限额时，必须声明该能力缺失；audit 模式记录实际 usage，并执行已验 wall/refine/deadline 边界。要求不支持的硬限时在模型启动前拒绝；不得把统计或 kill-after-timeout 称为 token 硬上限。

取消身份继续绑定 run/turn/generation/token。Codex 使用本机协议的 `turn/interrupt`，同时等待相应终态并处理 pending 请求，再有界关闭 owned app-server/工具进程及管道；不伪造 Pi clear_queue/abort 回执。Windows Job 的 root-exited、owned-members-empty、pipes-closed 和 owner observer/worker join 等事实共同决定 cleanup。未知 cleanup 保留 lease、返回 blocked-cleanup，阻止替代写者；不按进程名结束无关 Codex Desktop/其他任务。

安装恢复只条件恢复部署资源和入口，不回滚用户成果、原 case 或业务数据。模型/provider、scope/任务、基线、check plan 或源码非法漂移时，先停旧写者并保存事实，再由原 owner 接收新版；相关旧 proof 按适用性失效。
