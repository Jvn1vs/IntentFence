# C2b Base C Risk-only seed 42 工程训练结果（2026-09-05）

证据等级：`engineering_smoke_not_research_result`。本报告仅发布聚合指标与复现元数据。

## 结果与边界

- candidate 8，`B-ai-assisted-engineering` 路线；project-owned offline mock-tool scenarios。
- 5,000 条 train / 2,000 条 validation，完成 5 epochs；仅训练 Risk 五分类头，Alignment loss 为 0。
- 最佳 checkpoint 为 `best/`（epoch 4），验证集 Risk accuracy 0.9105、Macro-F1 0.905618926130284。
- 只使用 train/validation；未读取 calibration 或 Test A/B/C/D，校准和最终测试锁保持有效。
- 结果用于与 C multitask seed 42 对照，不能证明真实攻击防御、人工标签质量或最终测试性能。
- `inputs_unchanged=true`：训练前后 train、validation、calibration、test_a 及绑定证据哈希未变化。

## 每轮指标

| Epoch | Train loss | Validation accuracy | Validation Macro-F1 | 更新 best |
|---:|---:|---:|---:|:---:|
| 1 | 0.436825514793396 | 0.8745000000000001 | 0.8610765619467028 | 是 |
| 2 | 0.000323353910446167 | 0.8875 | 0.8778366914103923 | 是 |
| 3 | 0.000164667272567749 | 0.8985 | 0.8914242506649133 | 是 |
| 4 | 0.0001175483465194702 | 0.9105 | 0.9056189261302841 | 是 |
| 5 | 9.872992038726806e-05 | 0.9105 | 0.9056189261302841 | 否 |

## 运行记录

- 代码 commit：`0eaad896c4b40ee4c591c2f97f1d30971b13c9da`；实际执行者记录：`codex`。
- Backbone：`microsoft/deberta-v3-base`，revision `8ccc9b6f36199bec6961081d44eb72fb3f7353f3`；seed 42。
- Python 3.12.3；torch 2.6.0+cu124；transformers 4.57.6；numpy 2.1.3；sentencepiece 0.2.2。
- GPU：NVIDIA GeForce RTX 4090，CUDA 12.4。
- 开始 `2026-09-05T10:43:49.871957218Z`；结束 `2026-09-05T10:50:06.946960658Z`；训练脚本 manifest 时长 `377.068609` 秒。
- wrapper 退出状态：`0`；checkpoint reload 通过。
- 实际费用待账单补录；manifest 中的 0 USD 是脚本占位值。
- 训练时显存采样约 7,250 MiB；未连续记录硬件峰值。

## 可复现绑定

- 配置 SHA-256：`c34a6fb74f9da96ab56b895c88b65432f95e4ccf9bc360bf2158f67f2a9da5e9`
- train SHA-256：`dded160abb391972c7574829ad3443a900531485e99218d6c0bda545bd507c22`
- validation SHA-256：`37358a09843090a085e60a341ad33ef950c2934e5db32e8be0faed8b4ebec0d3`
- candidate manifest SHA-256：`8f874d7def0ac512b405bf1fc5ac30dba9d44b37000d64fc84629c3b3fee2016`
- 执行记录：`artifacts/c-risk-seed42-20260905-execution-v2/execution_record.json`（忽略，不提交）

## 提交与限制

- 本次提交只包含本 Markdown 和阶段进度文字；checkpoint、数据、原始日志、授权文件和依赖快照保留在本机。
- 没有多 seed、A/B 对照、校准参数、逐样本预测或正式显著性/效应量；C2b 正式研究出口仍未完成。
