# IntentFence 任务推进与实验计划

## Material Passport

- Origin Skill: academic-research-suite / experiment-agent
- Origin Mode: plan
- Origin Date: 2026-08-20
- Verification Status: UNVERIFIED
- Version Label: code_plan_v1
- Project Goal: 论文级实验质量，最终用于公开 GitHub 与简历展示

## 1. 推进规则

本项目采用阶段门（stage gate）推进。**每完成一个阶段立即暂停**，向用户汇报：

1. 本阶段完成了什么；
2. 修改或生成了哪些文件；
3. 执行了哪些测试，哪些通过或失败；
4. 尚存风险和未完成事项；
5. 下一阶段计划与预计资源；
6. 等待用户提问或明确确认后再继续。

未经用户确认，不自动进入下一阶段，不自动租用 GPU，不启动付费 API 实验。

从 2026-08-24 起，每个阶段在通过该阶段的静态、合成或用户执行验证后，还必须：

1. 只提交代码、配置、测试和允许公开的文档，不提交 raw/interim/processed 数据、JSON/CSV 质量报告、模型权重、凭据或缓存；
2. 在独立功能分支创建阶段提交并显式推送到远程同名分支，不使用可能误推 `main` 的裸 `git push`；
3. 在阶段汇报中记录远程分支、提交 SHA、验证结果和研究证据状态。

用户已于 2026-08-24 更新执行授权：Codex 可以连续执行 C1 真实数据下载、转换、合并、去重、划分、标签审核抽样/预审和训练前报告，并更新文档、完成阶段提交；`human_verified=true` 仍需项目所有者完成独立人类确认。所有学习参数拟合、tiny-overfit、Small/Base 训练及模型/校准参数更新仍只由项目所有者执行。该授权不允许自动开始 C2 模型训练，也不解除最终测试锁。

## 2. 状态定义

| 标记 | 含义 |
|---|---|
| ✅ 已实现并验证 | 代码已存在，并通过当前阶段要求的测试 |
| 🟡 已实现，待真实验证 | 代码或文档存在，只在单元测试/合成数据验证，不能支持论文结论 |
| 🔵 进行中 | 当前阶段正在执行 |
| ⬜ 未开始 | 尚未实现或执行 |
| ⛔ 等待资源/确认 | 需要用户确认、GPU、外部数据或付费资源 |

状态必须分别描述“工程实现”和“研究证据”。例如，训练代码写完不等于模型训练完成；ONNX 导出脚本写完不等于完成量化安全评测。

## 3. 冻结的研究目标

### 3.1 总目标

研究一个轻量、可监督训练、可独立校准、动作感知的间接提示注入检测器，判断它能否在低误报约束下，以低于在线 LLM 裁判的推理成本实现有竞争力的安全性和正常任务效用。

### 3.2 核心研究问题

| ID | 研究问题 | 主要比较 | 主要指标 |
|---|---|---|---|
| H1 | 用户任务上下文能否降低误报？ | 单文本 A vs 上下文 B | TPR@1% FPR、NotInject FPR |
| H2 | 拟执行动作能否提高攻击识别？ | 上下文 B vs 动作模型 C | TPR@1% FPR、逐类 Recall |
| H3 | 困难负样本能否改善泛化？ | 无困难负样本 vs 加入困难负样本 | NotInject FPR、攻击 TPR |
| H4 | 多任务头是否有独立收益？ | 仅 Risk Head vs Risk + Alignment | 跨数据集 TPR、Macro-F1 |
| H5 | 独立校准是否支持稳定分级？ | 校准前 vs Temperature Scaling | ECE、Brier、NLL、阈值稳定性 |
| H6（可选） | 轻量模型是否有系统成本优势？ | IntentFence vs LLM 一致性裁判 | 安全/效用、P95、成本 |

H1～H5 属于核心论文级实验。H6 只有在核心实验完成且用户批准付费/API或本地 LLM 实验后执行。

## 4. 总体阶段路线

| 阶段 | 目标 | 主要工具/方法 | 当前工程状态 | 当前研究证据 | 阶段出口 |
|---|---|---|---|---|---|
| P0 | 冻结推进计划与协作规则 | Markdown、Git 状态审查 | ✅ | 不适用 | 用户确认本计划 |
| C0 | 冻结研究协议与文献定位 | 论文原文、官方文档、实验注册表 | ✅ 已冻结 | ✅ 文献证据已核验；实验结果尚未产生 | 用户已批准协议 1.0.0 |
| C1 | 数据质量与必要基线框架 | 严格适配器、manifest、审计、泄漏检查、基线接口 | ✅ 框架与真实执行闭环完成 | ✅ 证据 validated；⛔ 训练就绪失败 | 真实 manifest、审核和报告已生成；按训练入口决策补数据/修订协议前停止 |
| C1B | Route B 训练前数据扩充（双 AI 工程路线） | 五分类训练来源、独立 Alignment、动作构造与双 AI 审核、v2 manifest | ✅ 双 AI 包、metadata 与分析器完成 | ⛔ 两次 AI B 运行均未通过预注册质量门；已接受为工程负结果 | 负结果已记录；正式训练与最终测试继续锁定 |
| C2a | Small 模型流水线与输入消融 | PyTorch、Transformers、DeBERTa-v3-small | 🟡 | ⬜ | CPU 冒烟通过，A/B/C 可重复训练和加载 |
| C2b | Base 主实验与困难负样本 | 云 GPU、DeBERTa-v3-base、3 seeds | 🟡 | ⛔ | H1～H4 主实验完成，结果可追溯 |
| C2c | 独立校准与阈值冻结 | Temperature Scaling、校准集 | 🟡 | ⬜ | H5 完成，温度和阈值冻结 |
| C3a | 跨数据集与过度防御评测 | Test A/B/C、Bootstrap CI、错误分析 | 🟡 | ⬜ | 最终测试只执行一次，报告完成 |
| C3b | ONNX INT8 与 CPU 部署 | ONNX Runtime、FastAPI、延迟基准 | 🟡 | ⬜ | 量化前后安全与 P50/P95 实测完成 |
| C4 | 论文式报告与简历包装 | 报告、模型卡、数据卡、演示 | 🟡 | ⬜ | 所有公开数字可由结果文件追溯 |
| G1 | 完善并发布 GitHub Release | Git、GitHub、CI、Release | 🟡 | 不适用 | `Jvn1vs/IntentFence` 公开可访问、CI 通过且材料完整 |
| B1/B2 | 最多选择 1～2 个加分项 | 鲁棒增强、AgentDojo 双门系统 | ⬜ | ⬜ | 核心完成后另行批准 |

## 5. 分阶段任务、工具与测试

### P0：计划冻结（已完成）

#### 要做什么

- 将论文级目标和简历交付目标统一到同一条核心路线；
- 定义阶段门、状态语义、汇报格式和停止点；
- 记录 GPU、数据下载和 GitHub 发布条件；
- 对已有工程代码进行诚实状态标注。

#### 用什么做

- `docs/task_progress_plan.md`：唯一任务进度主文档；
- Git：P0 当时只查看状态；从 2026-08-24 起按第 1 节的新阶段检查点规则提交并推送后续阶段；
- Academic Research Suite experiment plan：约束实验可验证性和状态声明。

#### 当前状态

- ✅ 本计划已创建；
- ✅ 用户已确认目标为论文级实验，最终用于简历；
- ✅ 用户允许下载公开数据，允许后续租用 GPU；
- ✅ GitHub 目标确定为公开 `Jvn1vs/IntentFence`；
- ✅ GitHub 远程仓库 `Jvn1vs/IntentFence` 已存在；阶段成果先推送独立功能分支，正式合并或 Release 仍需单独批准。

#### 要测试什么

- 文档是否同时包含任务、工具、状态、测试和出口条件；
- 每个阶段是否有明确停止点；
- 是否区分工程实现与研究证据；
- 是否存在提前宣称模型指标或论文结论的内容。

#### 出口条件

- 用户审阅并确认本计划后，才进入 C0。

---

### C0：研究协议与文献定位冻结

#### 要做什么

- 核对 Task Shield、BIPIA、InjecAgent、InjecGuard/NotInject、AgentDojo、ProtectAI 的论文、仓库、许可证和版本；
- 建立相关工作矩阵，明确 IntentFence 与现有任务一致性防御的差异；
- 冻结 H1～H5、输入 A/B/C、主指标和失败判据；
- 冻结 train/validation/calibration/test A～D 的用途；
- 冻结随机种子、模型选择规则、阈值规则、硬件/预算记录格式；
- 建立实验注册表，最终测试结果出现后不得修改主假设或指标。

#### 用什么做

- 论文原文、官方 GitHub/模型卡/官方文档；
- `docs/baseline_protocol.md`、`docs/threat_model.md`、`docs/experiment_log.md`；
- Markdown 文献矩阵与实验注册 JSON/YAML；
- Git commit 与文件 SHA-256 追踪协议版本。

#### 当前状态

- ✅ 已用论文原文、官方仓库、模型卡和数据卡完成核心来源核验；
- ✅ 已建立相关工作矩阵，并明确 Task Shield 是最接近的概念先例；
- ✅ 已生成 H1～H5、A/B/C、互斥数据角色、三随机种子、模型选择、校准阈值、统计和失败判据的预注册候选；
- ✅ 已建立机器可读实验注册表、上游 revision/许可证清单和 SHA-256 冻结候选；
- ✅ 已记录外部模型污染风险、NotInject 小样本限制和非商业许可证隔离规则；
- ✅ 用户已于 2026-08-20 批准冻结，协议状态为 `frozen`，并已另行批准开展 C1 框架工作。
- ✅ 用户明确由自己执行所有真实模型训练；Codex 可执行 C1 数据流程、搭建和验证框架，并分析训练日志。

#### 要测试什么

- 每个研究问题是否对应唯一主要比较和主要指标；
- 验证集、校准集和最终测试是否角色互斥；
- 外部基线是否记录潜在训练数据污染；
- Task Shield 结果是否严格标记为 `paper-reported`、`reproduced` 或 `Task-Shield-inspired approximation`；
- 是否提前定义负结果处理方式；
- 所有引用、版本和技术事实是否来自可核验的一手来源。

#### 出口条件

- 用户批准冻结后的研究协议；
- C0 文档检查全部通过；
- 在 C1 开始后，最终测试指标与边界不再随结果修改。

---

### C1：数据获取、审计、隔离划分与基线

#### 要做什么

1. 下载 BIPIA、InjecAgent、InjecGuard/NotInject，并记录 commit、许可证和文件哈希；
2. 检查真实字段结构，修正各数据适配器；
3. 转换为统一 JSONL schema；
4. 精确去重、近重复检测、模板分组；
5. 分层人工审计至少 200 条；
6. 输出 Risk × Alignment 列联表、条件概率和互信息；
7. 建立互斥 train/validation/calibration/test split；
8. 完成规则、word TF-IDF、char TF-IDF、ProtectAI、PIGuard/InjecGuard 的可重复运行框架和合成 smoke；正式 Test A/B/C 基线与冻结模型一起留到 C3 单次评测；
9. 生成数据卡、标签质量报告和训练就绪/阻塞报告；正式基线表在 C3 由同一批冻结预测统一生成。

#### 用什么做

- `scripts/download_sources.py`、`prepare_*.py`、`deduplicate.py`、`build_splits.py`、`audit_labels.py`；
- Pydantic、scikit-learn、字符 n-gram/Jaccard；
- 规则检测器、TF-IDF + Logistic Regression；
- Hugging Face Transformers 运行冻结 revision 的外部检测器；
- CSV/JSON/Markdown 报告。

#### 当前状态

- ✅ 固定 revision 下载器已实现，默认只预览；项目所有者确认来源条款后，Codex 或项目所有者可显式下载；多来源中断后可用 `--resume` 验证并复用已有来源、补齐缺失来源和原子生成完整 manifest；
- ✅ BIPIA、InjecAgent、NotInject 严格字段 profile 已实现并通过合成 fixture 测试，不再猜测字段或标签；
- ✅ 每行记录 adapter、label、action provenance；BIPIA 缺失动作、InjecAgent 基准目标动作和 NotInject 协议包装被明确隔离；
- ✅ 转换报告记录输入/输出 SHA-256、跳过数、标签与动作 provenance；严格模式 `skipped` 必须为 0；
- ✅ 人工审计抽样、审计汇总、修订应用、模糊样本排除框架已实现；抽样 seed、算法、分层字段和不可编辑行摘要均可从 canonical 输入重放验证；
- ✅ 精确/近重复、模板组跨 split、动作缺失检查和最终 split manifest 自哈希已实现；训练前报告会重放转换、merge、审计应用、去重和固定 seed 划分，而不是只相信 sidecar 声明；
- ✅ 规则、TF-IDF、ProtectAI、PIGuard 的统一连续分数接口、calibration/test backend+revision 绑定、calibration-only 阈值评估和完整矩阵聚合框架已实现；真实最终测试基线不会在模型冻结前提前运行；
- ✅ 执行权已更新：Codex 可运行 C1 真实数据处理、标签审核抽样和 AI 预审；只有项目所有者独立确认后才能设置 `human_verified=true`。学习基线拟合、模型/校准参数更新与所有训练仍只由项目所有者执行；
- ✅ 用户已完成 Conda `intentfence` 环境准备：Python 3.12.13；`pip check` 无损坏依赖；`huggingface_hub`、`jsonlines`、`nltk`、`pandas`、`pyarrow`、`transformers`、`yaml` 和项目包导入通过；固定 BIPIA email builder 导入预检通过；
- ✅ 用户已完成 BIPIA、InjecAgent、NotInject 固定来源预览；URL、revision、许可证发现和目标路径与冻结注册表一致，预览后 Git 工作区干净；
- ✅ 用户已使用 `--resume` 完成 BIPIA、InjecAgent 与 NotInject 固定来源下载；`source_manifest.json` 的 3 个 revision 与冻结注册表一致，131 个登记文件的存在性、大小和实际 SHA-256 已逐项复核且错误为 0；
- ✅ 已用 `intentfence` Conda 解释器完成 BIPIA email builder 无副作用预览；冻结 revision、train context/attack 路径和计划输出路径均正确，未生成数据文件；
- ✅ C1 手册命令已统一为从 Conda 环境登记表唯一解析解释器并 fail-fast；BIPIA builder 最小依赖已纳入 `data` extra；正式 split build 必须恰好生成六角色，manifest 会绑定每个角色的路径、行数和 SHA-256；动作校验按 split/source/provenance 白名单 fail-closed，Test B/C 的代理证据不会被误称为 observed action；
- ✅ 训练前报告生成器已实现：在用户完成第 7 节后会复核全部来源/转换/审计/manifest 证据，并生成 train-only Risk × Alignment 列联/条件概率/互信息、类别覆盖、动作就绪状态、标签质量报告和数据卡；
- 🟡 项目所有者已完成第 3 节的 email attack export、generated 严格转换和 clean 严格转换；转换报告分别记录 11,250 条攻击样本和 50 条 clean 样本，均为 `skipped=0`，报告中的输入/输出 SHA-256 已与现存文件复核一致。由于 export 产生在 builder sidecar 功能加入前，第 8 节前还须由项目所有者用 `--verify-existing` 重建到临时文件并生成 `reproduced_verified` 报告，现有数据无需覆盖；
- ✅ 项目所有者已完成第 4 节 InjecAgent 转换：direct-harm 报告记录 510 条，data-stealing 报告记录 544 条；两者均为 `skipped=0`、`split=test_b`、`action_provenance=benchmark_target`，且各自输入/输出 SHA-256 与现存文件一致；
- ⛔ BIPIA 不提供拟执行动作，且当前尚无已批准的动作构造与独立审计流程；第 3～8 节只能关闭 A/B 数据证据路线并生成训练前报告，模型 C 数据门仍阻塞，不得伪造动作；
- ⛔ 当前 BIPIA 构造只直接提供 `benign` 与 `instruction_hijacking`，且 schema 令 Alignment 成为 Risk 的确定性二值映射；正式训练前必须依据真实报告，由项目所有者决定是修订为二元 risk-only 主目标，还是增加经许可/审计的训练类与独立 Alignment 标注。冻结协议尚未被擅自修改；
- ✅ 已新增 `docs/training_entry_decision.md`，把二元 risk-only、保留五分类扩充数据、仅 A/B 工程冒烟三条路线及其证据/批准边界写清；当前状态仍为项目所有者待决，不构成协议修改；
- ✅ 第 5 节三个 NotInject 子集已完成：one/two/three 各 113 条，共 339 条；均为 `skipped=0`、`split=test_c`、`risk_label=benign`、`action_provenance=protocol_wrapper`，三份输入/输出 SHA-256 与报告一致，canonical schema 通过且跨子集重复 `sample_id=0`；
- ✅ 第 6 节 BIPIA 训练池合并完成：11,300 条（50 `benign`、11,250 `instruction_hijacking`），输出 SHA-256 `3fc10575e89e2304e2894629489a876b8e7c935a87e1aaea627be57386be725a`；固定 seed=42 的审核表抽取 200 条（50 clean、150 attack）；
- ✅ 项目所有者已检查全部 200 条 AI 预审建议并确认均为 `correct`；正式审核汇总 `status=passed`、`reviewer=project_owner`，应用只改变 200 行的 `human_verified`，11,100 条未抽样记录保留。正式审核 CSV SHA-256 为 `2e2990f0a62af8a163bae66e857debd8203d5a16f37e20f2f58c8abe2a717624`，审核后训练池 SHA-256 为 `1fd5559c18dd358a0e0184154af2e4a859cd0f5d13caff4f07f0b9125e397a99`；
- ✅ 第 7 节完成：BIPIA 11,300 条经 163 个精确重复对和 8,450 个近重复对去重后保留 2,687 条；加 Test B/C 后六角色共 4,080 条。manifest 文件 SHA-256 `e04a16f4b23b9811dc68c4a98cc6fe4152da582d90c0fbbfd6eb225efae1b545`、封存自哈希 `bdd9fe80de528083591652bc743d878777adb55bb082bf4d5df6fc5f7d1f0063`；context/external-action 完整性报告均 passed，模板组和近重复跨 split 泄漏为 0；
- ✅ 第 8 节完成：BIPIA builder 为 `reproduced_verified`；训练前报告重放整条证据链并给出 `evidence_status=validated`、总计 4,080 条。统计 JSON SHA-256 `f9008ff67c7f307ae2544695091625a861f22d78950238802c08946cf4f4f81f`，允许公开的标签报告与数据卡已生成；
- ⛔ 训练就绪失败：train 为 39 benign/1,176 instruction_hijacking，但 validation 493、calibration 493、test_a 486 均没有 benign；train 缺少 data_exfiltration/privilege_escalation/tool_manipulation；Alignment 为 Risk 的确定性映射；Model C 的四个内部角色都缺少获批 action。`formal_training_authorized=false`，真实 Test A/B/C 基线仍受单次测试锁保护；
- ✅ C1 工程框架与真实数据执行出口均已完成并形成 validated 证据；⛔ 研究训练出口因类别覆盖、Alignment 独立性和 action provenance 不足而关闭，不能进入真实训练结论阶段。

#### 要测试什么

- Schema：必填字段、标签映射、严重度、重复 `sample_id`；
- Adapter：每个来源至少建立固定 fixture 与字段映射测试；
- 去重：精确重复、近重复阈值、误删人工抽样；
- Split：任何 `template_group`/来源簇不得跨 split；
- 校准集：每类数量与正负比例，少数类不足标为 `insufficient evidence`；
- 审计：正确/错误/模糊比例，第二标注者或间隔盲审一致性；
- 基线：统一预测格式、默认阈值、1% FPR 阈值、P50/P95、异常样本；
- 数据污染：记录外部模型可能见过的数据，不虚假声称完成其训练成员去重。

#### 出口条件

- 工程出口：C1 框架校验、单元测试、lint、构建和用户手册通过；
- C1 数据执行出口：按 `docs/c1_user_runbook.md` 生成并复核以下证据；
- 标签质量报告完成；
- 所有 split 无模板/近重复泄漏；
- 本地和外部必要基线的接口、固定 revision 和合成 smoke 可重复；真实 Test A/B/C 基线结果按 test lock 延后到 C3 单次正式评测；
- 数据版本、哈希、许可证和结果均可追溯；
- 未达到出口条件不得租 GPU 训练 Base。

---

### C1B：Route B 五分类、独立 Alignment 与动作数据扩充（当前为双 AI 工程路线）

#### 要做什么

1. 在不改变旧 Test B/C 锁的前提下，保留 `2.0.0` 人类审核草案并创建 `2.1.0-ai-draft.1`；
2. 将五分类 `risk_label` 与四分类 `task_alignment_label` 分离；
3. 用离线 mock runtime 捕获候选动作、参数来源和不可变 observation ID；
4. 构造 Risk/Alignment 反事实配对，避免 Alignment 再次成为 Risk 的确定函数；
5. 根据 1% FPR、cluster 结构和主端点冻结精度/功效目标；
6. 当前 active route 完成两条相互盲的双 AI 审核流；原人工审核流保留为历史；
7. 重新构造互斥 v2 train/validation/calibration/untouched tests、manifest 与聚合报告；
8. AI-only 路线只生成工程证据，保持 `human_verified=false` 与
   `formal_training_authorized=false`；不移交论文级训练授权。

#### 当前状态

- ✅ 项目所有者已于 2026-08-24 选择 Route B，并于 2026-08-26 选择双 AI 工程/简历
  演示路线；选择不等于当前 v1 或论文级可训练；
- ✅ 新增 `2.1.0-ai-draft.1` AI-only 协议、双 AI prompt、metadata example 和分析 CLI；
  原 `2.0.0` 人类审核协议仍保留作历史，不被伪装为 AI 证据；
- ✅ `docs/route_b_data_protocol.md` 与 machine-readable 人类审核草案保留作历史；当前
  active machine-readable 协议为 `configs/route_b_ai_review_protocol.yaml`，状态明确为
  `AI_REVIEW_DIRECTION_APPROVED_CONSTRUCTION_AUTHORIZED_NOT_TRAINING_AUTHORIZED`；
- ✅ 官方来源复核完成：BIPIA 代码为 MIT，但 Email/Table/Code 等数据保留 MIT 或
  CC BY-SA 等各自条款；WebQA/Summarization 仍需另行取得源数据；
- ✅ InjecAgent、NotInject、AgentDojo 继续锁为 Test B/C/D，验证器会拒绝把它们放入
  train/validation/calibration；
- ✅ canonical schema 已增加 `task_alignment_label` 四分类和
  `sandbox_policy_output` action provenance；旧二值 `alignment_label` 仅作 v1 兼容；
- ✅ Route B 结构验证器已实现：拦截动作证据缺失、测试集挪用、模板/动作签名跨角色
  泄漏、动作配对破坏和 Risk/Alignment 确定性混淆；
- ✅ 离线 mock capture 只记录候选动作，trace 固定为 `executed=false`、
  `external_side_effects=false`；10 条五分类 fixture 通过结构验证；
- ✅ Wilson 精度规划脚本已实现，结果明确标为 planning-only，并警告行级二项精度
  不能替代 cluster-aware 功效分析；
- ✅ Route B 操作命令已写入 `docs/route_b_user_runbook.md`，不依赖旧 PowerShell 会话
  中的自定义函数；
- ✅ 项目所有者已批准 `2.0.0` 方向、默认排除未单独批准的 CC BY-SA/非商业来源，
  并授权 project-owned 离线 mock-tool 正式候选语料构造；
- ✅ candidate 4 已生成 27,000 条：train 5,000、validation 2,000、calibration 10,000、
  Test A2 10,000；五类 Risk 和四类 Alignment 在每个角色中均衡；
- ✅ manifest 自哈希、配置/生成器/runtime/trace/split 哈希可重放，27,000 条 trace 全部
  `executed=false`、`external_side_effects=false`；
- ✅ exact、template group、action signature 检查通过；5,400 个模板代表在阈值 0.92 下
  完成 69,452 次跨角色 Jaccard 比较，near-duplicate 为 0；
- ✅ 已生成两套不同顺序的 AI reviewer 输入包；每个 AI 各完成 400 条 Risk 和 400 条
  Alignment 的工程审核目标，不暴露 seed labels；AI 分析器和预注册质量门已实现；
- ✅ readiness 聚合与协议锁框架已实现：会重放 candidate manifest、结构/near-duplicate
  报告和双人审核分析；integrity v3 绑定四个 split 与当前 policy 哈希；聚合器同时绑定
  公开报告，并在任一证据缺失或漂移时保持
  `formal_training_authorized=false`；
- ✅ DeepSeek V4 Pro、Kimi K3 和 DeepSeek V4 Flash 的结构化审核结果、metadata、Prompt
  与输出哈希均已登记；每套审核均完成 400 条 Risk 和 400 条 Alignment；
- ⛔ `2.1.0-ai-draft.1` 分析已完成，但 Kimi K3 与 DeepSeek V4 Flash 两次 AI B 运行均未
  通过预注册质量门；失败结果已接受并记录为工程负证据，仍保持
  `human_verified=false` 与 `formal_training_authorized=false`；
- ⛔ `formal_training_authorized=false`，没有运行任何学习参数拟合。

#### 出口条件

- `docs/route_b_ai_review_protocol.md` 的双 AI metadata、哈希和质量门全部通过；
- 若质量门未通过，必须保留失败报告并在 `docs/route_b_ai_review_results.md` 如实记录，
  不得修改阈值或手工调整标签；本阶段不得进入训练；
- 真实数据、审核明细、JSON/CSV 报告继续被忽略，不提交仓库；
- 只提交框架、配置、文档和允许公开的聚合 Markdown 证据；
- 阶段退出后仍停在正式模型训练授权之前；如需工程训练，须另行形成项目所有者明确
  的非论文级实验决定。

---

### C2a：Small 模型流水线与输入消融

#### 要做什么

- 安装并冻结 PyTorch/Transformers/CUDA 兼容环境；
- 为用户生成 200～500 条样本、20～50 step 的 CPU 冒烟配置和一键命令；
- 用静态检查、fixture 和 mock 验证接口、形状、配置、保存/加载路径；
- 由用户亲自运行 DeBERTa-v3-small 的 A（文本）、B（上下文）、C（动作）训练；
- Codex 只读取用户提供的日志并生成 H1/H2 分析，不启动训练命令。

#### 用什么做

- `src/intentfence/modeling.py`、`train.py`、`evaluate.py`；
- PyTorch、Hugging Face Transformers、DeBERTa-v3-small；
- TensorBoard 或 JSON 训练日志；
- 固定 seed 42 与相同 split。

#### 当前状态

- 🟡 双头模型、训练循环、输入 A/B/C、类别权重、早停和 checkpoint 代码已实现；
- ✅ 训练入口已增加模型加载前的 split/benign-attack/action preflight、确定性分层
  smoke 样本限额和无 ML 依赖的 `--dry-run`；CPU AMP 路径改为按实际 device 选择；
- ✅ 核心 Python 代码通过静态检查和编译；
- ✅ 新增训练契约 fixture 测试，覆盖角色错配、覆盖不足、action 缺失和 seed 可重复性；
- ✅ Small/Base Hugging Face 模型已锁定完整 40 位 revision，并贯穿 tokenizer、encoder 与
  checkpoint metadata；
- ✅ 新增 200 train + 100 validation、25 optimizer step 的 CPU smoke 配置和项目所有者一键
  脚本，预检会在加载 ML 依赖前强制样本数与 20～50 step 窗口；
- ✅ Small A/B/C 配置已拆分，fixture 测试约束除 `run_name`/`input_mode` 外其他条件相同；
- ✅ 双头 `[B,5]`/`[B,2]`、token-type 路由、固定 revision 传递和 checkpoint 保存/加载已由
  无 PyTorch mock 测试覆盖；
- ✅ CPU 一键脚本会自动记录 Git commit/dirty 状态、配置与数据 SHA-256、环境版本、耗时、
  成本和 checkpoint 逐文件哈希；manifest 生成器已通过 fixture 测试；
- ✅ 本轮完整框架验证通过：Ruff、137 个 pytest、compileall、wheel 构建、PowerShell 脚本
  语法检查和无模型 CLI dry-run；
- ⬜ `ml` 依赖和 DeBERTa 权重尚未安装/下载；
- ⬜ 未执行真实 forward/backward、tiny overfit 或 checkpoint reload；
- ⬜ 未生成 A/B/C 训练结果。

#### 要测试什么

- 形状：Risk logits `[B,5]`、Alignment logits `[B,2]`；
- 梯度：两个头和共享 encoder 均有有效梯度；
- Tiny overfit：小样本上 loss 可明显下降；
- Checkpoint：保存后预测可重复加载；
- 标签映射：所有脚本一致；
- 截断：用户任务和拟执行动作不会被错误完全丢弃；
- 可复现：相同 seed/config/data 产生允许范围内的一致结果；
- A/B/C：只改变输入信息，其他条件保持一致。

#### 出口条件

- 框架侧静态、fixture、mock 和命令 dry-run 全部通过；
- 用户运行 CPU 冒烟与 checkpoint reload，并提供成功日志；
- 用户运行 Small A/B/C 至少 seed 42；
- 若上下文/动作没有增益，先检查数据构造，不直接扩大模型。

---

### C2b：Base 主模型、困难负样本与多任务消融

#### 要做什么

- 为用户准备 24GB GPU 环境清单、预算表、停止条件和恢复方案；
- 由用户租用 GPU 并运行 DeBERTa-v3-base A/B/C；
- 比较无/有困难负样本；
- 比较 Risk-only 与 Risk + Alignment；
- 最佳配置优先运行 seeds 42/52/62；
- Codex 不租用或操作训练 GPU，只分析用户提供的训练日志；
- 记录训练时间、显存、GPU 型号和实际费用。

#### 用什么做

- RTX 3090/4090 24GB 云 GPU；
- PyTorch AMP、梯度累积、早停；
- YAML 配置、JSON 日志、不可变数据 manifest；
- 分层 bootstrap 置信区间与配对样本比较。

#### 当前状态

- 🟡 Base 配置和训练代码已存在；
- ⬜ 未租 GPU；
- ⬜ 未执行任何 Base 训练；
- ⬜ Bootstrap CI、跨 seed 汇总和显著性/效应量报告尚未实现。

#### 要测试什么

- H1：B 相对 A 在固定 FPR 下的差异与置信区间；
- H2：C 相对 B 在动作相关攻击上的逐类差异；
- H3：困难负样本对 NotInject FPR 与攻击 TPR 的双向影响；
- H4：多任务头的独立收益及标签冗余；
- 多 seed 均值、标准差和异常波动；
- 训练曲线、过拟合、高损失样本和标签噪声；
- 不允许用突破 1% FPR 换取表面召回提升。

#### 出口条件

- H1～H4 的预注册比较均完成或明确报告负结果；
- 最佳模型权重冻结；
- 所有运行能由 commit、config、manifest、seed 和日志追溯。

---

### C2c：独立校准与策略阈值冻结

#### 要做什么

- 用冻结模型导出 calibration split logits；
- 分别拟合 Risk 与 Alignment 的 Temperature；
- 比较校准前后 ECE、Brier、NLL、reliability diagram；
- 只在 calibration split 选择 1% FPR 和 Allow/Confirm/Block 阈值；
- 冻结模型、校准器和策略版本。

#### 用什么做

- `scripts/export_logits.py`、`scripts/calibrate.py`；
- SciPy optimization、scikit-learn metrics；
- `configs/policy.yaml`、版本化 calibration JSON。

#### 当前状态

- ✅ Temperature Scaling、ECE/Brier/NLL 和低 FPR 阈值函数有单元测试；
- 🟡 logits 导出和校准 CLI 已实现，但没有真实 checkpoint；
- ⬜ reliability diagram 和 classwise ECE 尚未实现；
- ⬜ 真实温度和阈值尚未拟合。

#### 要测试什么

- 校准集与训练/验证/测试完全互斥；
- 温度为正，NLL 优化正确；
- 校准不改变 logits 排序，却改善至少一个可靠性指标且不损害安全运行点；
- Classwise ECE 样本不足时明确标记；
- 跨数据集失准单独报告；
- 长文档聚合分数不被称为攻击概率。

#### 出口条件

- 温度、阈值和策略版本冻结；
- H5 报告完成；
- 最终测试开始后不再修改校准参数。

---

### C3a：最终跨数据集、过度防御与错误分析

#### 要做什么

- 在冻结条件下运行 Test A（未见模板）、Test B（InjecAgent）、Test C（NotInject）；
- 与规则、TF-IDF、ProtectAI、PIGuard 和单文本内部基线公平比较；
- 生成 bootstrap CI、逐场景/类别/长度/工具分组结果；
- 输出最危险假阴性、最常见假阳性和模型差异案例；
- 只执行一次正式最终测试，后续修订建立新版本。

#### 用什么做

- `intentfence-evaluate`、评测脚本、Pandas/scikit-learn（需要时）；
- 固定 predictions JSONL、metrics JSON、Markdown/图表；
- 统计 bootstrap、配对差异分析、错误样本审计。

#### 当前状态

- 🟡 统一评测与预测文件代码已实现；
- 🟡 基础 metrics 已实现；
- ⬜ 真实 Test A/B/C 尚未运行；
- ⬜ Bootstrap CI、完整错误分析和论文图表尚未实现。

#### 要测试什么

- 主指标 TPR@1% FPR；
- Macro-F1、逐类 P/R/F1、AUROC/AUPRC；
- NotInject FPR；
- 跨域 ECE/Brier/NLL；
- 置信区间与多重比较说明；
- 截断、关键词捷径、场景偏差和潜在数据污染；
- 所有主张是否能由原始 predictions 重算。

#### 出口条件

- 核心结果表、校准表、错误分析和限制说明完成；
- 结果支持或否定 H1～H5 的证据链完整；
- 不选择性隐藏负结果。

---

### C3b：ONNX INT8、FastAPI 与本机 CPU 实测

#### 要做什么

- 导出冻结模型为 ONNX；
- 执行动态 INT8 量化；
- 量化前后重跑相同安全测试；
- 测量模型大小、峰值内存、P50/P95 和吞吐；
- 验证 `/health`、`/v1/evaluate`、版本信息和故障策略；
- 使用 mock 工具演示，不执行真实发送、上传、删除或支付。

#### 用什么做

- `deployment/export_onnx.py`、ONNX Runtime；
- FastAPI/Uvicorn；
- `benchmarks/latency.py`；
- Pytest/TestClient、PowerShell/API smoke test、Docker（可选运行验证）。

#### 当前状态

- ✅ 规则后端 API、策略和故障模式已通过单元/API 测试；
- ✅ 规则后端本机延迟脚本已运行，仅证明基准工具可用；
- 🟡 PyTorch/ONNX 后端和导出/INT8 代码已实现；
- ⬜ 没有真实 checkpoint，尚未导出 ONNX 或 INT8；
- ⬜ 未测量真实模型安全变化、内存和 P50/P95；
- ⬜ Docker 镜像尚未实际构建/启动测试。

#### 要测试什么

- PyTorch 与 ONNX logits/概率在容差内一致；
- INT8 相对 FP32 的主安全指标变化；
- 冷启动与预热后单请求 P50/P95；
- 不同输入长度和并发下延迟；
- 模型/校准/策略版本正确返回；
- 超时、缺模型、坏校准文件时按工具等级 fail-open/fail-closed；
- 高风险动作低分时仍至少人工确认。

#### 出口条件

- 普通 CPU 可运行量化模型；
- 安全指标和延迟均为真实实测值；
- API、演示和故障策略可重复验证。

---

### C4：论文式报告、简历材料与公开发布准备

#### 要做什么

- 完成摘要、方法、实验设置、结果、消融、错误分析、限制与伦理说明；
- 更新 README、数据卡、模型卡、威胁模型和复现命令；
- 制作可追溯结果表与简历描述；
- 如有模型权重，使用 Release 或模型平台，不提交大文件；
- 清理密钥、个人数据、缓存、原始数据和 checkpoint。

#### 用什么做

- Markdown/LaTeX（论文式报告）；
- Git/GitHub Actions；
- 模型卡、数据卡、实验日志与 raw predictions；
- 演示截图或短视频（用户批准后）。

#### 当前状态

- 🟡 README、模型卡、数据卡、威胁模型和可靠性策略已有初稿；
- ⬜ 没有真实实验结果，不能形成论文结论或简历数字；
- ⬜ 未完成论文式实验报告和最终简历表述。

#### 要测试什么

- 每个数字是否链接到结果文件和实验配置；
- 文档命令能否从干净环境运行；
- 不包含真实数据、密钥、checkpoint 或许可证不允许的内容；
- 不把工程目标写成已达到结果；
- 不把 Task Shield 思想表述为本项目首次提出；
- 负结果和局限是否完整披露。

#### 出口条件

- 简历中的每一条量化表述都可追溯；
- 论文式报告通过方法、统计和复现自查；
- 用户批准公开内容。

---

### G1：完善公开仓库并发布首个 Release

#### 要做什么

- 复核公开仓库 `Jvn1vs/IntentFence` 的最终内容；
- 检查初始化文件及后续新增文件；
- 分阶段维护提交并合并到 `main`；
- 运行 GitHub Actions；
- 配置仓库描述、Topics、License 和首个 Release（需要时）。

#### 用什么做

- Git、GitHub 连接或浏览器；
- `.gitignore`、GitHub Actions；
- 功能分支和受审查的 `main` 历史。

#### 当前状态

- ✅ 本地 Git 已初始化；
- ✅ 当前工作分支为 `feat/intentfence-core`；
- ✅ 公开仓库已由用户创建；
- 🔵 首次代码推送属于独立的仓库初始化检查点；
- ⬜ G1 的最终材料复核、Release 和简历包装尚未开始。

#### 要测试什么

- 提交范围不包含 `.venv`、原始数据、结果缓存、模型权重或密钥；
- GitHub Actions 在干净 Linux 环境通过；
- README 链接和安装命令有效；
- 仓库可见性确认为 public；
- 推送后的 commit 与本地验证 commit 一致。

#### 出口条件

- 用户明确授权 G1 的最终合并与 Release；
- `Jvn1vs/IntentFence` 可公开访问；
- 默认分支 CI 通过。

## 6. GPU 与费用计划

| 时点 | 资源 | 预计用途 | 启动条件 |
|---|---|---|---|
| C0 | 当前 CPU 电脑 | 文献、协议与框架检查 | 无需付费 |
| C1 | 当前 CPU | Codex 执行真实数据转换、审核抽样/预审、隔离划分和报告；项目所有者确认正式人类审核；不拟合 TF-IDF 或任何学习参数 | 当前已授权 |
| C2a | 用户操作当前 CPU/可选 GPU | 用户运行 Small 冒烟；Codex 提供框架和命令 | C1 出口通过 |
| C2b | 用户租用 RTX 3090/4090 24GB | 用户运行 Base A/B/C、消融、多 seed | Small 流水线通过且用户自行批准预算 |
| C3b | 当前 CPU 电脑 | ONNX INT8 和真实延迟 | 冻结 checkpoint 可用 |
| H6/B2 | 本地小 LLM 或付费 API | 可选系统比较 | 核心完成、单独预算批准 |

租 GPU 前由 Codex 提供平台、显卡、单价、预计小时数、预算上限、停止条件和数据上传范围清单；用户自行决定并执行租用。Codex 不操作租用或付费训练。

## 7. 论文级统计与复现要求

- 最佳核心配置优先使用 seeds `42/52/62`，只有一个 seed 时明确标注；
- 主比较使用相同冻结样本上的配对结果，并报告 bootstrap 置信区间；
- 同时报告效应大小/绝对差值，不只报告显著性；
- 对多个次要指标说明多重比较策略，不用挑选最有利结果；
- 预先冻结主指标 `TPR@1% FPR` 和 NotInject FPR 硬约束；
- 所有 stochastic 复现实验记录允许差异范围，异常波动必须分析；
- 每个运行保存 commit、数据 manifest、config、seed、依赖、硬件、时长、费用、原始预测和日志；
- 最终验证报告只有在成功重跑后才能标记 `VERIFIED`，否则保持 `UNVERIFIED` 或 `ANALYZED`。

## 8. 当前已验证事实

截至 2026-08-25：

- Ruff 静态检查通过；
- 128 个单元/API/协议/数据框架测试通过；另有 1 条来自 FastAPI/Starlette 测试依赖的非阻塞弃用警告；
- Python 编译检查通过；
- wheel 构建通过；
- C0 协议校验和 C1 框架校验通过；
- 合成 fixture 已覆盖来源/转换 replay、人工审计 key、merge、去重、六角色划分、manifest、完整性报告、规则与 word/char TF-IDF 接口及正式测试锁；
- 上述结果属于静态与合成验证，只证明工程框架按当前契约工作，**不证明 IntentFence 在真实数据或公开基准上有效**；
- 尚无训练 checkpoint、真实校准结果、跨数据集结果或 ONNX INT8 模型。

## 9. 每阶段汇报模板

```text
阶段：<阶段编号和名称>
状态：通过 / 有条件通过 / 未通过

完成内容：
- ...

文件改动：
- ...

测试：
- <命令> → <结果>

研究证据：
- 已得到：...
- 尚不能声称：...

风险/问题：
- ...

下一阶段：
- 要做什么：...
- 使用什么：...
- 需要资源/费用：...

暂停，等待用户提问或确认。
```

## 10. 当前停止点与 Route B 新阶段

C1 数据执行闭环已完成，`evidence_status=validated` 且 `formal_training_authorized=false`。项目所有者已将 C1B 选择为 AI-only 工程/简历演示路线：原 `2.0.0` 人类审核草案保留为历史，新增 `2.1.0-ai-draft.1` 双 AI 审核协议。candidate 4 已生成 27,000 条并通过 manifest、五类/四类覆盖、动作 provenance、exact/template/action-signature 与 0.92 模板代表 near-duplicate 检查；双 AI 输入包、AI 分析器、readiness 聚合器和协议锁框架均已生成。Kimi K3 与 DeepSeek V4 Flash 两次独立 AI B 运行均完成各自 400 条 Risk 与 400 条 Alignment 审核，但分别在 Alignment `malicious` 和 Risk `instruction_hijacking` 的逐类 seed agreement 质量门失败；负结果已记录并接受为工程证据。AI 证据只能支持工程演示，`human_verified=false`，不开放正式训练或最终测试。v1、Test B/C/D 和最终测试锁保持不变，所有学习参数拟合继续禁止。
