# Candidate 9 公开数据构造结果

状态：`integrity_verified_not_training_ready`。执行者 Codex，2026-09-08。

## 已执行结果

有效产物目录：`data/interim/candidate_9_v2/`。原始来源核验沿用 source manifest 与上游固定 revision。候选 manifest SHA-256：`4ac5fcca810c652596334b203cc1d097cddb76c6c6bae9a476716fcd71bf13dc`。

| 角色 | 攻击配对 | 原始正常背景 | AI 编写困难负样本 | 总数 |
|---|---:|---:|---:|---:|
| train | 1905 | 635 | 10 | 2550 |
| validation | 267 | 89 | 1 | 357 |
| calibration | 261 | 87 | 3 | 351 |
| internal Test A | 270 | 90 | 2 | 362 |
| 合计 | 2703 | 901 | 16 | 3620 |

这不是 3620 个独立场景：共有 634 个正常背景/困难负样本的近重复连通组、14 个攻击家族组。近重复定义为 NFKC/casefold/空白归一化后的字符 5-gram Jaccard >= 0.8。算法使用前缀索引加精确集合核对，fixture 对比穷举结果；没有拟合统计模型或学习参数。

背景和攻击家族分别在构造前按固定 seed=42 分配至 70/10/10/10 的目标角色，比例针对组而非行，因此实际样本比例不同。同族攻击之间的近重复也会连通整个家族。随后每条公开背景最多配对 3 条同角色攻击，交替首尾插入，明确标记为 project-derived，不声称由官方 builder 导出。官方 test 同名家族被排除（包含 Language Translation）。

锁定的旧 v1 calibration/Test A/B/C、candidate 8 calibration/Test A 以及 BIPIA 官方 Email/Table test 和官方 text test attacks 仅用于输入隔离检查，未运行模型或使用模型预测。49 条公开训练背景因锁定集合近重复被剔除。最终生成文本的跨 split 近重复组为 0；独立 verifier 重新检查锁定集合近重复、文件哈希、样本编号、schema 和角色成员关系。

## 重要限制

- 50 条 Email 中仅 1 条在锁定集合隔离后保留。训练角色有 2536 条 Table 衍生样本、4 条 Email 衍生样本、10 条 authored 困难负样本，仍显著偏向 Table。不能声称已解决多来源泛化问题。
- 16 条困难负样本分别采用代码测试、会议记录、文档、日志、表格、小说评论等表达，不使用单一填槽模板；均如实标记 Codex-authored、未审核。规模偏小，validation 仅 1 条，不能支持可靠的困难负样本误报结论。
- 风险标签为暂定 benign/instruction_hijacking，后者表示插入的偏离任务指令，不声称涵盖所有风险细分类。未完成五类 Risk 覆盖、独立四类 Alignment 标注或动作构造。legacy 二元 alignment_label 仅为 schema 兼容字段；task_alignment_label=null，human_verified=false。
- calibration 只有 90 个正常样本，且背景成组相关，不足以有力证明 1% FPR。未拟合温度、阈值，未运行最终评测。
- InjecAgent 训练排除；CodeQA 专用适配和上游条款尚待落实。Stack Overflow 官方说明其用户贡献按发表时间适用 CC BY-SA 2.5/3.0/4.0，具体版本需看帖子修订时间；现有 CodeQA 字段有问题/作者链接，但不足以证明每条回答修订的许可证版本。来源：[Stack Overflow licensing](https://stackoverflow.com/help/licensing)（2026-09-08 查阅）。本报告不将仓库 MIT 视为上游内容的替代许可证。
- 字符近重复检查不能证明语义独立；仍需要标签审核和场景审核。

## 审核与复现

生成 `label_review.jsonl`，共 91 条 train/validation 分层样本，保留空审核人和决定，不抽取 calibration/Test A 作调参审核。公开仓库不包含真实数据或本地 authored 训练素材；复现需保留 `data/owned/candidate_9_hard_negatives.jsonl`，其 SHA-256 绑定在 manifest 中。

```powershell
conda activate intentfence
# 构造输出必须使用新目录；v2 已存在时不要覆盖。
python scripts/build_candidate_9.py --output data/interim/candidate_9_reproduction
python scripts/verify_candidate_9.py data/interim/candidate_9_reproduction
```

v1 在独立校验中发现样本 ID 使用了 schema 清理前的首尾空白，已经弃用但未删除；修复后 v2 验证通过，并增加对应回归测试。v2 的 manifest 绑定实际实现文件哈希，生成时 Git HEAD 不包含尚未提交的新实现，因此重放应同时核对实现哈希，不能只看生成时 Git commit。

本次也使 `configs/execution_policy.yaml` 与当前 AGENTS.md 的项目所有者独占训练规则一致：移除 Codex 执行训练的允许项，恢复明确训练禁止项。此前 C1 契约测试失败随之消除；未改变历史训练记录或授予新训练权限。

验证结果：Ruff、compileall、wheel 构建通过；全量测试 269 passed，随后新增的 2 项 manifest/输出篡改测试单独运行 2 passed。实际 v2 独立完整性检查通过。测试包含前缀索引与穷举 Jaccard 对照、传递分组、角色不足拒绝、攻击家族隔离、锁定背景排除、顺序不变性，以及首尾空白处理的 sample ID 回归。

## 后续工作

当前完成的是可追溯的候选构造和完整性验证，尚未达到多来源、足量困难负样本、五分类/动作感知训练就绪的最终目标。下一步应解决来源多样性与对应条款、完善任务和标签覆盖、扩大困难负样本审核；不能通过放松测试隔离或重复组合人为增加可用数量。
