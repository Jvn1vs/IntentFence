# C2b A text Risk-only seed 42 工程训练结果（2026-09-05）

证据等级：`engineering_smoke_not_research_result`。本报告只发布聚合指标与复现元数据。

## 结果与边界

- candidate 8，`B-ai-assisted-engineering`；project-owned offline mock-tool scenarios。
- 5,000 train / 2,000 validation；5 epochs；只训练 Risk 五分类头，Alignment loss 为 0。
- 最佳 checkpoint 为 `epoch-001`，验证集 Risk accuracy 0.994、Macro-F1 0.9939986496961817。
- 只使用 train/validation；未读取 calibration 或 Test A/B/C/D。
- 结果仅用于 seed 42 的 Base 输入变体工程比较，不能证明真实攻击防御或最终测试性能。

## 每轮指标

| Epoch | Train loss | Validation accuracy | Validation Macro-F1 | 更新 best |
|---:|---:|---:|---:|:---:|
| 1 | 0.3467900221586228 | 0.994 | 0.9939986496961817 | 是 |
| 2 | 0.0002852944850921631 | 0.956 | 0.9554610790565846 | 否 |
| 3 | 0.0001482417345046997 | 0.954 | 0.9533834967444452 | 否 |
| 4 | 0.0001070674896240234 | 0.948 | 0.9471060929712134 | 否 |
| 5 | 8.951199054718017e-05 | 0.946 | 0.9449975809121234 | 否 |

## 运行记录

- 代码 commit：`546d779573bf9e9655e943b317f9dbfdf9f5c3fa`；模型：`microsoft/deberta-v3-base` revision `8ccc9b6f36199bec6961081d44eb72fb3f7353f3`；seed 42。
- Python 3.12.3；torch 2.6.0+cu124；transformers 4.57.6。
- GPU：NVIDIA GeForce RTX 4090；CUDA 12.4。
- 开始 `2026-09-05T10:59:55.548130447Z`；结束 `2026-09-05T11:06:10.599470523Z`；时长 `375.045052` 秒；checkpoint reload 通过。
- 实际费用待账单补录；manifest 中 cost_usd=0.0 是占位值。
- 训练时显存约 7,250 MiB；没有连续峰值记录。

## 哈希绑定

- 配置：`30d4239d79de201371db03cb2760a00ff7b766891e2b69ad35f667cfb2491246`
- train：`dded160abb391972c7574829ad3443a900531485e99218d6c0bda545bd507c22`
- validation：`37358a09843090a085e60a341ad33ef950c2934e5db32e8be0faed8b4ebec0d3`

## 提交限制

- checkpoint、数据、原始日志、授权文件和完整 run manifest 保留本机，不提交 Git。
- 未进行多 seed、校准、最终测试、逐样本预测或正式显著性检验；C2b 正式研究出口仍未完成。
