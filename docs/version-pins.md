# 固定官方 Spec Kit 版本

默认 plan 从官方 PyPI 选择最新非撤回稳定版。需要保持已有官方包不变时，可显式使用 `--spec-kit-version 1.3.1`；安装器仍从官方元数据核对该版发行文件、SHA-256 和 Python 要求，不修改官方包，也不把旧版标为 latest。

```text
python scripts/install.py plan --root ../workflow --client pi --agent-dir ../pi-agent --project ../result --spec-kit-version 1.3.1 --output .local/plan.json
python scripts/install.py install --root ../workflow --plan-file .local/plan.json --apply
```

只读复用已有包时，再同时提供 `--spec-kit-tools <UV_TOOL_DIR>` 和 `--spec-kit-bin <UV_TOOL_BIN_DIR>`。真实 `specify version` 必须等于冻结版本，原有版本、文件摘要和配置漂移门不变。指定不存在、预发布、全部撤回或没有有效发行文件摘要的版本会失败；不选择 spec-kit 时不能传该参数。

显式选择记录在 `scope.spec_kit_version`，组件记录标记 `version_selection=explicit-pypi-stable-release`，receipt 保留具体版本和发行信息。`--plan-file` 不重新查询 latest；命令行可省略 pin，若再提供必须与冻结组件版本相同。修改 pin 或组件版本而不一致的计划会被拒绝。原来没有 pin 字段的冻结计划继续可用。

本轮基线为 Spec Kit 1.3.1。验收期间上游发布1.3.2，旧包与新默认计划的冲突被正确检出；使用显式1.3.1重新生成计划，不手改回执或升级官方文件来掩盖冲突。
