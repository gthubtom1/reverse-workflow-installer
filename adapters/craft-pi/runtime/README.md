# Craft Pi runtime：源码、身份与发行导航

本目录保存 installer 自有 bridge/executor 的完整源码与测试、固定上游的有序 policy patches、许可材料和独立官方 Pi 的获取输入。这里的文件是构建输入，不是已安装 runtime；本次仍按 candidate 资格逐项核验，不能从目录存在推断联合 source freeze、原生包、发布、模型/业务或宿主加载已经完成。

先读[上游维护手册](../../../docs/craft-upstream-maintenance.md)、[升级提示词](../../../docs/craft-upgrade-prompt.md)、[打包合同](../../../docs/craft-packaging.md)与[安装合同](../../../docs/craft-install.md)。公开资产获取见[精确 pin acquisition](../../../docs/craft-acquisition.md)；原 R46/Spec 的生产交接见[execution reference](../references/execution.md)。

## 从实物读取本轮身份

- `bridge/` 与 `executor/` 各自的 `FROZEN-SOURCE-MANIFEST.json` 记录原来源库存；`snapshot-origin.json` 区分原字节和 portable 非生产转换，`packaged-source-manifest.json` 记录实际分发源码库存。核当前文件和摘要，不把旧 revision/hash/测试数写成永久输入。生产 Rust/Cargo 保真要求与保留测试/fixtures 的规则见打包合同；fixture 源码是维护输入，不是生产可执行文件。
- `patches/series.json` 冻结 Craft 完整上游 commit/tree、Cargo.lock、patch 顺序与源码摘要；本次上游基线仍为 `0326b4de8051f85a0f3139cd82f88f76911e6a35`，不追浮动 latest。保留完整上游依赖，薄补丁重放和语义回归分别验证。
- 联合 `source-manifest.json` 和 `entry-protocol.md` 仅在正式 freeze 产生后使用；缺失、不匹配或来源尚未接受应明确报阻断。联合身份须覆盖 recipe/imported readers、资源、owned 源码、patch、许可和正式协议；修改这些输入后重新审阅并冻结，不能自动刷新摘要掩盖漂移。
- 运行时按实际 receipt 定位 bundle，再读 bundle manifest 的正式 entry protocol 和真实 owner `--inspect`；本目录 executor 的旧协议不自动代表候选或所装版本。validate/prepare/run、typed return 等能力由该版本的实际协议、schema、审查和验证结果判定，不用开发进度代替接受资格。production prepare-contract 按 bundle manifest 定位，不假设旧快照已经包含。

## 目录与构建布局

当前源码目录为 `bridge/`、`executor/`、`patches/`、`notices/`、`pi/`。两个 owned crate 保留 Cargo、src、测试/fixtures、examples/helpers 及身份文件；helper 保留不表示真实 provider/native 验证已执行。根联合 manifest/protocol 属 freeze 输出，不为补目录示意而制造。

构建使用独立 sibling layout：`craft-anything-adapted`、`craft-pi-bridge`、`craft-pi-executor`。完整上游从 fixed ref 获取并按实际 series 顺序应用，不回指开发机目录、不裁剪后端，不在本目录猜 Cargo 路径直接构建。生产二进制不启 fixtures feature；测试 helper 可单独编译，源码随包保留，编译产物不冒充 runtime bin。按打包合同显式提供工具、cache、许可和协议，不能把源码复制当作原生包已经就绪。

## 官方依赖、交接与资格

`pi/package-lock.json` 和官方 Node pin 是独立获取输入，不来自个人 Pi Web 树。新机器按 `acquire-pi` 获取完整官方 Pi/Node 及 npm 依赖并校验 lock/checksum；我方不重分发 Pi ZIP、不裁剪官方依赖。许可 unknown 阻止对应发布资格；个人 auth/settings/MCP/provider 资源、凭据值和 sessions 不进入本目录或公共包，本机凭据只用显式环境引用。

普通 implementation-worker 默认沿用，Craft 为原 R46/Spec 逐批明确 opt-in；单切片 A/B 不证明收益。原 PRIMARY/REA 先在 scope 内接收目标行为与派生来源/限制，Spec 冻结任务后才交 Builder；缺证回原链，不以猜测或扩大权限继续。prepare 不自动研究或生成 UI oracle，真正执行须保留单 owner、完整 implement/converge、typed 返回、required checks、cleanup 与独立验收门。

代码/包、安装注册和项目数据分层回滚；保留旧 source/history/receipt。候选源码、构建资产、正式 release、安装事务、宿主实际加载和业务接受分别记录，任何一项通过都不替其他层证明。
