# Guided workflow 验收

发布组合：installer 0.4.0、reverse-skill 1.8.0、project-continuity 1.2.0。下面分别记录机械契约、宿主生命周期和模型动作抽样；这些结果不构成任意真实目标的行为等价保证。

| 验证层 | 结果 | 边界 |
|---|---|---|
| 原路由与结构 | PowerShell/Bash 各192例；完整 smoke/coherence、兼容指纹、文档和安全边界检查通过 | 保留原 routing.json 和既有路由优先级 |
| 授权面闭合 | 25项测试通过 | 固定清单分母，1/7、遗漏组件、身份/哈希不符、过期/失败回归、相邻组件重开、路径越界等反例；不证明人为提供的清单与证据语义真实 |
| Reconstruction | 31项原交接测试通过 | 原 case/Evidence/Spec Kit 边界保留，L0–L6 明确区分 |
| Installer | 116项 Python 测试通过 | 包括显式官方版本 pin、旧冻结计划、实际版本不符拒绝及配置/事务保护 |
| Grilling wrappers | Windows107项：105通过、2项 POSIX FIFO 跳过；公开 Linux/Windows CI 验证 | 所有官方输入保持原字节；输出所有权、链接和手改冲突受检 |
| Wrapper 宿主发现 | Pi Web SDK1.5.0 读取两个新技能，无诊断 | 静态资源发现，不代表所有访谈行为已验证 |
| Continuity | 107项插件测试通过；真实 SDK与 bundled CLI/RPC 344项断言通过 | 包含候选隔离、指针新鲜度、case/target、取消、缺失case墓碑、reload/resume/tree、开关与 schema；模拟模型只用于生命周期验收 |
| 真实模型动作抽样 | `magpie / gpt/gpt-6-astra`、`max`：7个代表场景动作门通过 | 使用惰性事件工具，无真实目标执行；12个离线错误变体被断言拒绝，不能称为其他弱模型实测 |

模型场景覆盖：静态失败后的范围内转场、仅静态范围、单个授权面成功、回归失败、复制当前卡、过期别名和行为证据不足。初轮四项在115秒上限超时；改用300秒推理上限，并收紧过期别名的最小澄清规则后，受影响五项重新实跑通过。两个无关场景沿用已审查适用性的旧快照，不冒充一次全新整批实跑。

请求均设置 `max_output_tokens=6000`，但一次 provider 用量报告为7794。因此动作门通过，**服务端 token 上限执行仍未验证**；不能把发出上限参数当成上限已强制执行。未运行真实加壳样本、真实设备、完整源码复刻或所有 provider 的业务验收。

官方 REA6.8.0 与 Spec Kit1.3.1 的实际树摘要与基线回执一致。验收期间 PyPI 默认变为 Spec Kit1.3.2，原有1.3.1包与新计划的冲突被正确拒绝；新增 [显式版本 pin](version-pins.md) 从官方发行元数据选择1.3.1，保持现有包不变，不修改生成计划或回执伪造通过。

四个 Grilling 文件保持原字节。旧 `grill-me` / `grill-with-docs` 已有历史 adapter 标记，单独报告为 legacy drift；新 wrapper 读取未改写的 `grilling` / `domain-modeling`。保持字节不等于认证上游来源。

本机 Bash bootstrap-manifest 测试因 Windows Store 的 python3 占位程序退出49，未计为本地通过；公开 Linux CI 覆盖该套件。Windows CI 中 WSL占位入口和8.3临时路径比较问题已修正，未删除隔离断言。

每次实际部署仍须记录公共 tag解析出的 commit/tree hash，运行 `verify`、`accept`，并在当前宿主重载或新会话检查。`accept` 不执行 continuity扩展事件，相关回执字段保持未验证，独立 SDK/UI记录不能伪造该字段。JADX可选桥接器缺口沿用既有报告；缺少调用方提供的 JAR 时不得声明其深度分析能力就绪。历史1.1.0验收见 [原记录](project-continuity-verification.md)。
