# Candidate 9 v3：Dolly 公开背景接入

日期：2026-09-09。状态：构造完成，独立 verifier 运行中；不代表训练就绪。

## 数据和来源

项目所有者明确批准了 Dolly 固定版本 `bdd27f4d94b9c1f951818a7da7fd7aeea5dbff1a` 的下载与 CC-BY-SA-3.0 范围使用。下载数据文件 13,085,339 bytes；README 8,199 bytes，均绑定 SHA-256。实际下载记录：`data/raw/dolly/source_manifest.json`。

Dolly 原始 15011 条中选取 4467 条带非空参考文本的 closed_qa、information_extraction、summarization 背景；其余 10544 条因类别不匹配排除。与 BIPIA 和已有 authored 背景合并后，排除 231 条锁定集合近重复、21 条 goal/content 重复。

| 划分 | 攻击配对 | 正常背景 | 初始 authored 困难负样本 | 合计 |
|---|---:|---:|---:|---:|
| train | 10929 | 3643 | 10 | 14582 |
| validation | 1548 | 516 | 1 | 2065 |
| calibration | 1533 | 511 | 0 | 2044 |
| internal Test A | 1500 | 500 | 0 | 2000 |
| 总计 | 15510 | 5170 | 11 | 20691 |

以上是配对后的样本数，独立背景/近重复组为 4579，攻击家族组为 14。每个公开背景最多配对 3 条同角色攻击，仍为 project-derived 插入，不等于 20691 个独立场景或真实攻击。分组使用 seed=42，目标比例为 70/10/10/10；组划分导致行数比例有偏差。

训练场景为：Dolly closed_qa 4824、information_extraction 4132、summarization 3196；BIPIA Table 2416、Email 4；authored 10。表格不再占据几乎全部训练内容，但尚未覆盖足够邮件、代码、实际工具执行场景。

## 证据绑定

- 构造 Git commit：`4d613c5dd362bb2654dab70d30ab993f7b3ccee8`；所有执行实现文件另外绑定 SHA-256。
- manifest：`data/interim/candidate_9_v3/manifest.json`，SHA-256 `dd3a37d9d151dffb22d54b8d52ffc1d38cb2a5456dad9603cb00863adb4d5ef8`。
- 构造时长：682.422 秒（manifest 记录值；仅本机 CPU 数据处理，无训练）。
- train SHA-256：`57294e964d5aec1306b813442c26834d1e318cf6dcba2b7b09570388275e4576`。
- validation SHA-256：`269efb4d15cfdeaccce67730937d918374163dfb7add7ab46aade83baecd44d0`。
- calibration SHA-256：`3543354112b9f19aa5b23ed6d539d5a6b990722975641116f3469071966f0261`。
- internal Test A SHA-256：`d27dbaa76b5a76492cc1a6268e621d2e486ed4f229fb8ae5ffe5e2d39030b52a`。
- train/validation 审核包 `label_review.jsonl`：211 条，reviewer/decision 均为空；未抽取校准/测试供调参。

v2 calibration/Test A 已加入保护集合；旧 v1/candidate 8 校准与测试以及 BIPIA 官方 test 继续受保护。构造器给出的最终跨 split 字符近重复组为 0，阈值为规范化字符 5-gram Jaccard >=0.8。独立验证还会重算这些检查，并逐条重建 Dolly 样本的原始任务、内容和归属。

## 复现

```powershell
conda activate intentfence
# 源已下载；仅从干净新源目录复现下载时运行下行。
python scripts/download_candidate_9_dolly.py
# 输出目录必须不存在；已有 v3 不得覆盖。
python scripts/build_candidate_9_v3.py --output data/interim/candidate_9_v3_reproduction
python scripts/verify_candidate_9_v3.py data/interim/candidate_9_v3_reproduction
```

上游文件、source manifest 和本地 authored 负样本必须按 manifest 保留。数据及派生文本不提交公开 Git，Dolly/Wikipedia 的 CC-BY-SA-3.0 归属不被项目 Apache-2.0 替代。

## 验证与限制

本轮全量 279 项测试、Ruff、compileall、wheel 构建通过；来源适配与独立重建的 fixture 覆盖标签误标、内容替换、归属丢失和错误任务。真实独立验证结果待本轮 verifier 完成后更新。

风险标签仍是暂定 benign/instruction_hijacking。四类 Alignment 未标注，拟执行动作缺失，human_verified=false、training_ready=false、formal_training_authorized=false。不能声称满足原五类 Risk 的 C 多任务训练门，也不能把数据增加当作模型泛化改善的实验证据。

原有 authored 困难负样本经旧 v2 校准/测试保护后仅保留 11 条，且仅在 train/validation。公开自然背景不自动等于困难负样本；目前不足以支持困难负样本消融或低误报结论。攻击表达仍主要来自 BIPIA，新增 Dolly 只扩充正常背景/任务。

internal Test A 全部来自 Dolly，但 Dolly 也出现在训练中，因此它是背景/攻击家族留出，不是未见来源外部评测。不能据此声称跨来源泛化。最终测试模型预测、校准、下一轮训练均未执行。
