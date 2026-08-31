# C2a Small 模型用户运行手册

状态：C2a CPU 工程 smoke 已由项目所有者完成；Codex 只核验 checkpoint、manifest 和框架，
不运行 forward/backward、tiny overfit 或任何参数更新。当前 `formal_training_authorized=false`；
smoke 指标不能写成论文结果。

## 1. 已锁定的模型与环境边界

- Small：[`microsoft/deberta-v3-small`](https://huggingface.co/microsoft/deberta-v3-small/commit/a36c739020e01763fe789b4b85e2df55d6180012)
  revision `a36c739020e01763fe789b4b85e2df55d6180012`；
- Base：[`microsoft/deberta-v3-base`](https://huggingface.co/microsoft/deberta-v3-base/commit/8ccc9b6f36199bec6961081d44eb72fb3f7353f3)
  revision `8ccc9b6f36199bec6961081d44eb72fb3f7353f3`；
- 当前 Conda 环境：`intentfence`，Python 3.12；
- 当前已验证：Transformers 4.57.6、PyTorch 2.13.0+cpu、Accelerate 1.14.0、Datasets 4.8.5、
  SentencePiece 0.2.2、Protobuf 6.33.6；固定 revision tokenizer、模型权重和 smoke checkpoint
  均已成功加载。

模型卡显示 Small 的 PyTorch 权重约 286 MB；安装和首次加载会产生较大的外部下载，所以仍由
项目所有者在本阶段单独决定并执行。只使用 PyTorch、Anaconda 和 PyPI 官方端点。

## 2. 无模型下载预检

下面的命令只读取 train/validation，验证角色、benign/attack 覆盖、动作来源、固定样本数和
optimizer step 计划，不加载 tokenizer 或模型：

```powershell
conda run -n intentfence intentfence-train `
  --config configs/deberta_small_cpu_smoke.yaml `
  --train data/processed/AUTHORIZED_VERSION/train.jsonl `
  --validation data/processed/AUTHORIZED_VERSION/validation.jsonl `
  --dry-run
```

成功输出必须含 `train_count=200`、`validation_count=100` 和
`planned_optimizer_steps=25`。不足 200/100 条或超出 20–50 step 时入口会在 ML 依赖加载前
拒绝运行。

也可以使用一键脚本的只预检模式：

```powershell
.\scripts\run_c2a_cpu_smoke.ps1 `
  -TrainPath data\processed\AUTHORIZED_VERSION\train.jsonl `
  -ValidationPath data\processed\AUTHORIZED_VERSION\validation.jsonl `
  -PreflightOnly
```

脚本会先解析并打印唯一的 `intentfence` Conda Python 路径，再在同一个解释器中验证
PyTorch 和 Protobuf。若输出的 Python 不是预期环境，脚本会在训练前停止。

## 3. 由项目所有者安装 CPU 训练依赖

本机 `intentfence` 环境已完成 CPU 训练依赖安装。重新构建环境时，从 PyPI 官方端点安装
项目 ML 依赖；安装后把实际版本写入运行 manifest，不能只记录范围版本。

```powershell
conda activate intentfence
python -m pip install -e ".[ml,dev]" --index-url https://pypi.org/simple
python -m pip check
python -c "import google.protobuf, torch, transformers; print(torch.__version__); print(transformers.__version__); print(google.protobuf.__version__)"
```

不要改用第三方镜像。

## 4. 由项目所有者运行 CPU smoke

一键脚本依次执行：无模型预检、25-step Action smoke、最佳 checkpoint 双重 reload 与完全
一致的 logits 检查，并生成含 Git、配置、数据、环境、耗时、成本和 checkpoint 逐文件哈希的
`run_manifest.json`。

```powershell
.\scripts\run_c2a_cpu_smoke.ps1 `
  -TrainPath data\processed\AUTHORIZED_VERSION\train.jsonl `
  -ValidationPath data\processed\AUTHORIZED_VERSION\validation.jsonl
```

必须保留三段输出：`preflight_passed`、训练 JSON 日志和
`checkpoint_reload_passed`，并确认 `run_manifest_written`。它们只证明代码路径可运行，不证明
模型有效。

当前运行已完成：200 train、100 validation、25 optimizer steps，耗时 158.24 秒、成本 0，
checkpoint reload 通过；`run_manifest.json` 中登记的 checkpoint 文件大小和 SHA-256 已全部
复核一致。运行时指标只作为工程日志保留，不构成有效性证据。

## 5. Small A/B/C

项目所有者已于 2026-08-27 明确选择继续 A/B/C 工程训练；该授权只覆盖由项目所有者本人执行
的工程/简历演示运行，不改变 `human_verified=false` 与 `formal_training_authorized=false`，结果不得
作为论文证据。三份配置共享模型 revision、seed、batch、学习率、epoch、max length 与损失权重，
测试只允许运行名和输入模式不同：

从 2026-08-28 起，本阶段及后续所有模型训练均采用“冻结配置、版本化启动脚本、独立输出目录、
checkpoint 验证和 run manifest”的科研执行形式；不再把临时手敲的长命令作为正式运行入口。
当前先完成并核验 A，B/C 启动脚本在进入对应运行前按同一模板生成和验证。

| 变体 | 配置 | 输入 |
|---|---|---|
| A risk-only | `configs/deberta_small_c6_text_risk.yaml` | 外部内容 |
| B risk-only | `configs/deberta_small_c6_context_risk.yaml` | 用户任务 + 外部内容 |
| C risk-only | `configs/deberta_small_c6_action_risk.yaml` | 用户任务 + 外部内容 + 拟执行动作 |
| C multitask | `configs/deberta_small_c6_action_multitask.yaml` | 同 C，增加四分类 Task Shield loss |

candidate 6 的四组配置 dry-run 已通过：每组均为 5,000 train、2,000 validation、五个 Risk
类别分别 1,000/400 条、四个 Task Shield Alignment 类别分别 1,250/500 条，计划 939 个
optimizer steps。A/B/C risk-only 的 alignment loss 固定为 0；C multitask 才启用四分类
alignment loss，以分别支持 H1/H2/H4。

candidate 4 的 A 已完成并得到三轮 validation 100%，但随后确认存在归一化语义模板泄漏。
该 checkpoint、日志和 `scripts/run_c2a_small_a.ps1` 仅用于复现这条工程负证据，不得继续据此
运行 B/C，也不得把 100% 指标写成模型有效性结果。

当前停止点是 candidate 8 的独立人类双盲审核及后续授权判断。此前 candidate 6 的重新审核已作为
失败 AI 工程证据封存，不能作为训练入口。即使 candidate 8 的 AI 审核数值门通过，仍不得生成或
运行 candidate 8 的训练启动脚本；现在不要运行训练命令。

candidate 4 的历史只读预检仍可复现为：

```powershell
Set-Location E:\IntentFence
.\scripts\run_c2a_small_a.ps1 -PreflightOnly
```

不要再次执行不带 `-PreflightOnly` 的 candidate 4 脚本。

每次使用独立输出目录，不能覆盖 checkpoint。运行前后记录 Git commit、配置 SHA-256、数据
manifest/SHA-256、seed、OS、CPU/GPU、RAM/VRAM、Python、PyTorch、Transformers、CUDA、
开始/结束时间和成本。Codex 只在用户提供这些日志后分析 H1/H2，不执行训练。
