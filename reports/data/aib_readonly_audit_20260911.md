# AgentInjectionBench 固定版本只读审计

日期：2026-09-11。项目所有者已批准提案中的四文件下载与只读审计。源为 `ppradyoth/AgentInjectionBench`，revision `ef230359966c4d87b1c925aa56b8bf6e3f6ffed3`，Apache-2.0。批准配置、原文许可证与来源记录已保留。

## 结论

**可作为攻击场景候选，不能直接作为已具备恶意动作与独立 Alignment 的训练集。** 实际 182 条中，142 条原始 ground_truth 为 unsafe、40 条为 safe；只有一条显式 tool_call，位于正常用户新请求之后。执行约束是待检查的规则，不是执行证据。本阶段没有转换样本或应用标签，数据继续隔离。

## 下载与结构

四文件合计 351742 bytes，逐个验证长度和 Git blob OID，并生成 SHA-256。两个数据文件实际下载；README 下载重定向发生 TLS EOF 后，复用前阶段同 revision 的本地缓存，验证 blob OID 完全一致。LICENSE 同样使用已核验缓存，没有替换源版本。

| 文件 | bytes | SHA-256 |
|---|---:|---|
| data/agent_injection_bench.jsonl | 314335 | `606cb74f5ce874dba45d9cdf591af678d7c6bd8a92ff3189d0f522fb39fb941e` |
| data/taxonomy.json | 7773 | `050aff8736f36d1fecb852de4ce13a46c4da4ec8402858958940df8a9181848d` |
| README.md | 18928 | `5a094b3e440431038bfd52f190c97ea15f5376d3bf8bfc2b2666db41e4aba400` |
| LICENSE | 10706 | `0cbb6e1df4da7f103fe853bac30ae4e973332373418dfc01856cbbf2e94a9968` |

源分类计数：data_exfiltration 20、privilege_escalation 22、tool_shadowing 12、tool_output_injection 28、mcp_context_poisoning 22、goal_hijacking 21、multi_turn_stateful 17、benign 40。这是原始分类，不是本项目五类审核标签。原始 intent 又分别含 exfiltration 63、escalation 47、manipulation 20 等，说明 category 与风险机制不是同一维度。

conversation 共有 user 218、tool_result 208、assistant 199、tool_call 1。全部消息未含结构化 tool_calls 字段。唯一 tool_call 在 AIB-00139 第 4 个零基 turn，是用户要求保存笔记后的 file_write，没有实际执行回执；不能将其认定为恶意工具返回触发的动作。统计不排除自然语言中描述动作，亦不把这种描述提升为已观测执行。

## 有目的的 AI 语义抽查

一个 agent 完整读取 9 条，主审检查报告与全量字段统计。这不是全量标签审核或双独立审核。抽查 ID 为 AIB-00001/00002/00003、00076/00077/00078、00157/00158/00159。

- 外泄三例有系统信息/内部信息/运行上下文的外传诱导，助手文本则正常回答或识别可疑内容，不能把 unsafe 场景转成 malicious 动作。
- 越权三例包含修改权限、管理员入口、伪造 OAuth 批准。00076 的注入目标工具与禁止工具列表不同；00078 也有 target_tools 与可用工具不一致问题。
- tool_shadowing 中 00157、00159 主风险偏外泄，不能机械映射 tool_manipulation。00158 的付款目的地被改变，但执行约束的工具、参数和写入限制为空，不能声称约束已充分捕获该攻击。
- 9 条均无结构化动作调用，工具定义缺完整参数 schema。既未执行其中代码，也未核验示例攻击在真实接口上有效；工具约束、助手安全示范和实际动作必须分开记录。

## 重复与划分检查

对所有 user、tool_result 字符串执行 NFKC/casefold/空白规范化的跨案例精确比较，无重复组；字符 5-shingle Jaccard >=0.8 的跨案例文本对为 0。此结果不证明不同措辞下的模板、场景或攻击家族独立，也没有覆盖工具描述注入的全部语义重复。

以同一文本规则筛查 candidate 9 配置列出的 v1、candidate 8、candidate 9 v2/v3 calibration/Test A，以及 v1 Test B/C、BIPIA 所选背景测试与官方测试攻击。逐文件哈希保存在 audit_v2.json，没有打印保护文本或访问模型测试结果；指定路径无缺失，命中案例为 0。此筛查不覆盖完整 AgentDojo 场景/工具家族，也不证明跨来源语义隔离，`complete_source_clearance=false`。

上游 curate.py 的 70/15/15 按类别随机切分仍只是一种构造方法，当前固定源未发布分开的 split 文件。本阶段未执行该切分；不能把无文本重复解释为可直接随机拆分。后续先补场景家族与来源组，再决定派生角色，保留校准和最终测试锁。

## 证据、验证与下一步

原始文件和 source_manifest 位于 `data/raw/agent_injection_bench/`；机器审计为 `data/interim/aib_audit_20260911/audit_v2.json`。首轮 audit.json 保留为修正 lint 命名前的历史快照，当前以 v2 为准，SHA-256 为 `586e34cdeec7d94a3826a27a70a90b7a3a5073fbd42bcb6fa979d6a41bccf1b8`。审计脚本只读取数据；拒绝源哈希不符和重复 ID，拒绝覆盖既有报告。

新增 `scripts/audit_candidate_9_aib.py`、`tests/test_aib_audit.py`；fixture 验证 unsafe 不产生动作/Alignment 标签、动作边界与重复 ID 拒绝。Conda intentfence 下 Ruff、三项针对性测试、compileall 和 wheel 构建通过；完整 pytest 315 passed（61.64 秒），git diff --check 通过。

建议下一阶段在这个已授权来源内建立隔离场景清单：逐条提取用户目标、低信任载体、敏感资源、授权边界与工具能力，审核家族和候选风险；明确无法恢复动作的记录。形成多来源背景与离线动作策略的具体方案后，再申请构造阶段，避免直接用统一包装补齐动作。当前训练就绪仍为 false，不执行训练、源工具或数据发布。
