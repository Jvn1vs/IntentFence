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
| C0 | 冻结研究协议与文献定位 | 论文原文、官方文档、实验注册表 | 🟡 | ⬜ | RQ、数据边界、指标、基线、预算全部冻结 |
| C1 | 数据质量与必要基线 | BIPIA、InjecAgent、NotInject、规则、TF-IDF | 🟡 | ⬜ | 数据审计、无泄漏 split、统一基线表完成 |
| C2a | Small 模型流水线与输入消融 | PyTorch、Transformers、DeBERTa-v3-small | 🟡 | ⬜ | CPU 冒烟通过，A/B/C 可重复训练和加载 |
| C2b | Base 主实验与困难负样本 | 云 GPU、DeBERTa-v3-base、3 seeds | 🟡 | ⛔ | H1～H4 主实验完成，结果可追溯 |
| C2c | 独立校准与阈值冻结 | Temperature Scaling、校准集 | 🟡 | ⬜ | H5 完成，温度和阈值冻结 |
| C3a | 跨数据集与过度防御评测 | Test A/B/C、Bootstrap CI、错误分析 | 🟡 | ⬜ | 最终测试只执行一次，报告完成 |
| C3b | ONNX INT8 与 CPU 部署 | ONNX Runtime、FastAPI、延迟基准 | 🟡 | ⬜ | 量化前后安全与 P50/P95 实测完成 |
| C4 | 论文式报告与简历包装 | 报告、模型卡、数据卡、演示 | 🟡 | ⬜ | 所有公开数字可由结果文件追溯 |
| G1 | 完善并发布 GitHub Release | Git、GitHub、CI、Release | 🟡 | 不适用 | `Jvn1vs/IntentFence` 公开可访问、CI 通过且材料完整 |
| B1/B2 | 最多选择 1～2 个加分项 | 鲁棒增强、AgentDojo 双门系统 | ⬜ | ⬜ | 核心完成后另行批准 |

## 5. 分阶段任务、工具与测试

### P0：计划冻结（当前阶段）

#### 要做什么

- 将论文级目标和简历交付目标统一到同一条核心路线；
- 定义阶段门、状态语义、汇报格式和停止点；
- 记录 GPU、数据下载和 GitHub 发布条件；
- 对已有工程代码进行诚实状态标注。

#### 用什么做

- `docs/task_progress_plan.md`：唯一任务进度主文档；
- Git：查看文件状态，但本阶段不提交、不推送；
- Academic Research Suite experiment plan：约束实验可验证性和状态声明。

#### 当前状态

- ✅ 本计划已创建；
- ✅ 用户已确认目标为论文级实验，最终用于简历；
- ✅ 用户允许下载公开数据，允许后续租用 GPU；
- ✅ GitHub 目标确定为公开 `Jvn1vs/IntentFence`；
- ⛔ GitHub 仓库尚未创建，本阶段不执行发布。

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

- 🟡 威胁模型、基线协议和实验日志模板已经存在；
- 🟡 项目方案已定义 H1～H6 和 C0～C3；
- ⬜ 尚未完成逐项文献核验与相关工作矩阵；
- ⬜ 尚未生成正式实验注册表及冻结哈希；
- ⬜ 尚未核对所有上游许可证和不可变 revision。

#### 要测试什么

- 每个研究问题是否对应唯一主要比较和主要指标；
- 验证集、校准集和最终测试是否角色互斥；
- 外部基线是否记录潜在训练数据污染；
- Task Shield 结果是否严格标记为 `paper-reported`、`reproduced` 或 `inspired approximation`；
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
8. 运行规则、word TF-IDF、char TF-IDF、ProtectAI、PIGuard/InjecGuard 基线；
9. 生成数据卡、标签质量报告和基线表。

#### 用什么做

- `scripts/download_sources.py`、`prepare_*.py`、`deduplicate.py`、`build_splits.py`、`audit_labels.py`；
- Pydantic、scikit-learn、字符 n-gram/Jaccard；
- 规则检测器、TF-IDF + Logistic Regression；
- Hugging Face Transformers 运行冻结 revision 的外部检测器；
- CSV/JSON/Markdown 报告。

#### 当前状态

- ✅ 统一 schema、标签一致性校验、去重和模板组划分代码已实现；
- ✅ 规则与两种 TF-IDF 基线已在 20 条合成 smoke 数据上运行；
- ✅ 数据层单元测试已通过；
- 🟡 三个公开数据适配器已实现，但尚未用真实上游版本验证；
- 🟡 ProtectAI/PIGuard 适配器已实现，但尚未下载权重或运行；
- ⬜ 公开数据尚未下载；
- ⬜ 200 条人工标签审计尚未执行；
- ⬜ 真实数据泄漏、类别分布和少数类校准充分性尚未验证。

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

- 标签质量报告完成；
- 所有 split 无模板/近重复泄漏；
- 本地和外部必要基线可重复运行；
- 数据版本、哈希、许可证和结果均可追溯；
- 未达到出口条件不得租 GPU 训练 Base。

---

### C2a：Small 模型流水线与输入消融

#### 要做什么

- 安装并冻结 PyTorch/Transformers/CUDA 兼容环境；
- 用 200～500 条样本执行 20～50 step CPU 冒烟；
- 验证 forward、backward、loss、保存和重新加载；
- 训练 DeBERTa-v3-small 的 A（文本）、B（上下文）、C（动作）三个版本；
- 验证 H1/H2 是否值得进入 Base 主实验。

#### 用什么做

- `src/intentfence/modeling.py`、`train.py`、`evaluate.py`；
- PyTorch、Hugging Face Transformers、DeBERTa-v3-small；
- TensorBoard 或 JSON 训练日志；
- 固定 seed 42 与相同 split。

#### 当前状态

- 🟡 双头模型、训练循环、输入 A/B/C、类别权重、早停和 checkpoint 代码已实现；
- ✅ 核心 Python 代码通过静态检查和编译；
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

- CPU 冒烟和 checkpoint reload 全部通过；
- Small A/B/C 至少完成 seed 42；
- 若上下文/动作没有增益，先检查数据构造，不直接扩大模型。

---

### C2b：Base 主模型、困难负样本与多任务消融

#### 要做什么

- 根据 Small 结果租用 24GB GPU；
- 训练 DeBERTa-v3-base A/B/C；
- 比较无/有困难负样本；
- 比较 Risk-only 与 Risk + Alignment；
- 最佳配置优先运行 seeds 42/52/62；
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
| C0～C1 | 当前 CPU 电脑 | 文献、数据、审计、规则/TF-IDF | 无需付费 |
| C2a | 当前 CPU + 可选短时 GPU | Small 冒烟与流水线 | C1 出口通过 |
| C2b | RTX 3090/4090 24GB | Base A/B/C、消融、多 seed | Small 流水线通过且用户批准 |
| C3b | 当前 CPU 电脑 | ONNX INT8 和真实延迟 | 冻结 checkpoint 可用 |
| H6/B2 | 本地小 LLM 或付费 API | 可选系统比较 | 核心完成、单独预算批准 |

租 GPU 前必须提供：平台、显卡、单价、预计小时数、预算上限、停止条件和数据上传范围，等待用户确认。

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

截至 2026-08-20：

- Ruff 静态检查通过；
- 12 个单元/API 测试通过；
- Python 编译检查通过；
- wheel 构建通过；
- 合成 smoke 数据的划分、规则、word TF-IDF、char TF-IDF 和延迟脚本可运行；
- 上述验证只证明工程骨架工作，**不证明 IntentFence 在公开基准上有效**；
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

## 10. 下一步（需用户确认）

本阶段结束后暂停。用户确认本计划后，下一阶段为 **C0：研究协议与文献定位冻结**。C0 不训练模型、不租 GPU；只做一手资料核验、相关工作矩阵、实验注册和协议冻结。
