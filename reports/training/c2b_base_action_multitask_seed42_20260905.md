# C2b Base C multitask seed 42 工程训练结果（2026-09-05）

证据等级：`engineering_smoke_not_research_result`。本报告仅发布聚合指标与复现元数据。
用户授权提交本次结果；原始数据、审核明细、授权文件、日志、run manifest 和模型文件保留在服务器。

## 结果与边界

- candidate 8，`B-ai-assisted-engineering` 路线；project-owned offline mock-tool scenarios。
- 5,000 条 train / 2,000 条 validation，完成 5 epochs；预检计划 1,565 optimizer steps。
- 指标是验证集 **Risk 五分类** accuracy/Macro-F1；不是 Alignment 指标、最终测试指标或 TPR@1% FPR。
- `best/` 对应 `epoch-004/`；epoch 5 同分，未替换 best。两目录文件哈希已逐项复核一致。
- 日志记录 `training_completed`、`checkpoint_reload_passed`、`run_manifest_written` 和脚本完成标记。
  训练和重载命令成功返回（脚本对非零状态立即退出）；未单独持久化整条 shell 命令的数字退出码。
- Codex 修复环境并在 tmux pane `%3` 准备命令，用户按 Enter 启动；manifest 的 executor 为 `project_owner`。
- 只使用 train/validation 进行本次拟合与模型选择；没有启动校准或最终测试流程。
  `human_verified=false`、`formal_training_authorized=false` 与校准/最终测试锁保持有效。
- 双 AI 审核的失败质量门仍保留，见 [候选工程证据卡](../data_quality/route_b_candidate_8_ai_engineering_card.md)。
  接近满分不能证明真实攻击防御、独立人类标签质量、Alignment 收益或跨数据集泛化。
- 没有多 seed、A/B/C 消融、置信区间或逐样本预测产物；当前训练验证函数只保存聚合指标，
  无法凭这份报告重建逐样本统计检验。C2b 正式研究出口仍未通过。

## 每轮指标

| Epoch | Train loss | Validation Risk accuracy | Validation Risk Macro-F1 | 更新 best |
|---|---:|---:|---:|---|
| 1 | 0.7682337824583053 | 0.9 | 0.8933333333333333 | 是 |
| 2 | 0.002338209640979767 | 0.945 | 0.9439401178531612 | 是 |
| 3 | 0.001206825876235962 | 0.982 | 0.9819634760389789 | 是 |
| 4 | 0.0008558916091918945 | 0.9995000000000001 | 0.9994999992187488 | 是 |
| 5 | 0.0007358351469039917 | 0.9995000000000001 | 0.9994999992187488 | 否 |

## 运行记录

- 训练代码 commit：`6f2c51b1309dcc1ec3a6193002d03f610cf7982e`（本次结果提交的父版本）。
- manifest 记录 `git.dirty=true`；结果整理前 `git status --short` 只列出未跟踪的 `logs/`，
  没有跟踪文件修改。未将原始记录改写为 clean，也不能用事后状态补造完整的运行时工作区快照。
- Backbone：`microsoft/deberta-v3-base`，revision `8ccc9b6f36199bec6961081d44eb72fb3f7353f3`。
- 固定配置：[deberta_base_action_multitask.yaml](../../configs/deberta_base_action_multitask.yaml)，seed 42。
- max length 384，train/eval batch 8/16，梯度累积 2，learning rate 2e-5，weight decay 0.01，
  warmup ratio 0.10，max grad norm 1.0，fp16，alignment loss weight 0.5，target `task_alignment`；
  gradient checkpointing 与 early stopping 均关闭。
- Conda 环境 `intentfence`，Python 3.12.3；torch 2.6.0+cu124、
  torchvision 0.21.0+cu124、transformers 4.57.6、numpy 2.1.3、sentencepiece 0.2.2。
  torchvision 来自修复后的环境核验，其余版本来自运行 manifest；未保存完整依赖锁快照。
- NVIDIA GeForce RTX 4090，24 GB；CUDA 12.4，cuDNN 90100。
- UTC 开始：`2026-09-05T07:07:50.060676774Z`；结束：`2026-09-05T07:14:11.012379725Z`。
- manifest 时长：380.946923 秒，脚本计时覆盖训练及 checkpoint reload，
  不包含此前安装、下载与失败尝试的全部时间。checkpoint 目录约 4.2 GiB。
- 显存：会话监控曾观察到 7,250 MiB；没有连续采样或峰值计数器产物，**峰值未知**。
  此处更正此前口头汇报中的“峰值”措辞。
- 实际费用：**未提供，待账单补录**。manifest 的 `cost_usd=0.0` 来自启动脚本固定占位值，
  不表示 GPU 免费，也不能按本次成功运行时长代替整机实际计费。
- 环境修复：从官方 PyTorch CUDA 12.4 源升级 torch 至 2.6.0+cu124，匹配 torchvision 0.21.0+cu124；
  `pip check` 通过。此前失败尝试保留在本地；成功重试使用独立目录和已有模型缓存离线运行。

## 已执行命令（历史记录，不是启动下一轮的指令）

在已激活 `intentfence` 的训练 pane 中执行以下命令。原输出目录已存在，启动脚本会拒绝覆盖；
数据与缓存未随本报告上传，因此仅克隆 Git 仓库不足以重跑。

```bash
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 && \
cd /root/autodl-tmp/IntentFence && \
bash scripts/run_c2b_base.sh \
  --config-path configs/deberta_base_action_multitask.yaml \
  --train-path data/interim/route_b_v2_candidate_8/train.jsonl \
  --validation-path data/interim/route_b_v2_candidate_8/validation.jsonl \
  --output-directory checkpoints/base-action-multitask-seed42-owner-20260905-retry2 \
  --authorization-file data/interim/route_b_v2_candidate_8/ai_training_authorization.json \
  --candidate-manifest-path data/interim/route_b_v2_candidate_8/manifest.json \
  --readiness-report-path data/interim/route_b_v2_candidate_8/ai_engineering_readiness.json \
  --protocol-lock-path configs/route_b_ai_training_protocol_lock.json \
  --policy-path configs/route_b_ai_training_protocol.yaml \
  --protocol-document-path docs/route_b_ai_training_protocol.md \
  --integrity-report-path data/interim/route_b_v2_candidate_8/integrity_v2_data_protocol.json \
  --integrity-policy-path configs/route_b_data_protocol.yaml \
  --ai-review-policy-path configs/route_b_ai_review_protocol.yaml \
  --ai-review-manifest-path data/interim/route_b_v2_candidate_8_human_audit_v2_ai_pair/ai_review_manifest.json \
  --audit-analysis-path data/interim/route_b_v2_candidate_8_human_audit_v2_ai_pair/ai_review_analysis.json \
  --audit-manifest-path data/interim/route_b_v2_candidate_8_ai_pair_audit/audit_manifest.json \
  --public-report-path reports/data_quality/route_b_candidate_8_ai_engineering_card.md \
  --conda-executable /root/miniconda3/bin/conda \
  --require-cuda
```

## 本地产物与 SHA-256

以下为仓库相对路径，文件本体不在本次提交内。完整目录前缀是
`checkpoints/base-action-multitask-seed42-owner-20260905-retry2/`。
成功日志位于该目录旁的同名 `.log` 文件；此前给出的 `logs/base-action-multitask-seed42-train-retry2.log`
属于旧失败尝试，不是本次成功日志。

| 文件（目录内相对路径，除非另有说明） | SHA-256 |
|---|---|
| `run_manifest.json` | `5286d9ccd7cf0cbe98b59b0d14c1d07f5cf6e10915fd64736fb92f0c946b1549` |
| `training_log.json` | `de8897f8c4d3c9a19aa7566ac65cb73e8ad69898ad38d7c752bfe313c02be15a` |
| `resolved_config.json` | `65a29b811d202d4b7e244593eb4e408b0e304bd9586594347370d8d524ddf972` |
| `目录旁的同名 .log` | `347b6efe9e458cb44b69806ee02b303f72489d15f5078ff022a79332f1a47425` |
| `best/encoder/config.json` | `99630390681ac0d487502b127958005075d947936bf8681432a7b9717b19e64b` |
| `best/encoder/model.safetensors` | `10a7916decd2e2b285d079d64942b5dc185642cfdc66cb51b52f79cb260f3faa` |
| `best/heads.pt` | `4ca152215cd56d3a296da2604540769d0ebf10fd8d39a8c32f20dfddb7e48c94` |
| `best/metadata.json` | `605862ca5439793fb72b93ae59798190be998c141b5e159915d3da366ad72da9` |
| `best/tokenizer/added_tokens.json` | `dc046d04c9b0ada7ae6f1dc89c465801799acdf0c9a6aab8c15a1b2d5ca4e91f` |
| `best/tokenizer/special_tokens_map.json` | `9463f61e1b109a8eb4688b829260d7c6b1e6dff04c98ff7269bb89e2b92369b9` |
| `best/tokenizer/spm.model` | `c679fbf93643d19aab7ee10c0b99e460bdbc02fedf34b92b05af343b4af586fd` |
| `best/tokenizer/tokenizer.json` | `d36161599bf5cd59cc85e37e201e29dc21b40fb3c403f2d4eb00b7b1a7cc0fcb` |
| `best/tokenizer/tokenizer_config.json` | `e6c4c771911c211618a2d46488dc7e9e499f051773cd4ff4faeca6fe55fdf569` |

数据与配置绑定（仅哈希，不含样本内容）：

| 文件 | SHA-256 |
|---|---|
| `configs/deberta_base_action_multitask.yaml` | `8160f9e56884f22768c20ca5bce286559f59cc99747b71f89123b0bce4f1165a` |
| `data/interim/route_b_v2_candidate_8/train.jsonl` | `dded160abb391972c7574829ad3443a900531485e99218d6c0bda545bd507c22` |
| `data/interim/route_b_v2_candidate_8/validation.jsonl` | `37358a09843090a085e60a341ad33ef950c2934e5db32e8be0faed8b4ebec0d3` |
| `data/interim/route_b_v2_candidate_8/ai_training_authorization.json` | `fe2ca1f50cd1ae197a43f41694c991b2ccea2e5048878f315263d55b071d95f7` |
| `data/interim/route_b_v2_candidate_8/manifest.json`（文件字节哈希） | `8f874d7def0ac512b405bf1fc5ac30dba9d44b37000d64fc84629c3b3fee2016` |

## 本次提交验证与停止点

- 核对五轮结构化指标和 console log 一致，并确认完成、重载和 manifest 标记。
- `best/` 所有文件、`epoch-004/` 对应文件及配置/train/validation 哈希与原 manifest 一致。
- Conda `intentfence` 的 `python -m pip check` 通过。
- 仅编辑公开聚合 Markdown、阶段进度和 `.gitignore`；没有重跑训练、加载模型或修改原始产物。
- 本次在结果提交处停止；后续变体/seed 或校准/评测仍需对应阶段确认与授权。
