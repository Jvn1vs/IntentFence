# C2a Small 模型用户运行手册

状态：框架准备中。Codex 只实现配置、静态/fixture/mock 测试和命令，不安装大型 PyTorch/
模型权重，不运行 forward/backward、tiny overfit 或任何参数更新。当前 Route B 数据质量门未
通过，`formal_training_authorized=false`；下面的训练命令只能在项目所有者另行明确批准某个
工程 fixture 或训练版本后执行，不能把 smoke 指标写成论文结果。

## 1. 已锁定的模型与环境边界

- Small：[`microsoft/deberta-v3-small`](https://huggingface.co/microsoft/deberta-v3-small/commit/a36c739020e01763fe789b4b85e2df55d6180012)
  revision `a36c739020e01763fe789b4b85e2df55d6180012`；
- Base：[`microsoft/deberta-v3-base`](https://huggingface.co/microsoft/deberta-v3-base/commit/8ccc9b6f36199bec6961081d44eb72fb3f7353f3)
  revision `8ccc9b6f36199bec6961081d44eb72fb3f7353f3`；
- 当前 Conda 环境：`intentfence`，Python 3.12；
- 当前已验证的 Transformers：4.57.6；PyTorch、SentencePiece 和模型权重尚未安装。

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

## 3. 由项目所有者安装 CPU 训练依赖

项目所有者批准约 300 MB 以上依赖下载后，在 `intentfence` Conda 环境执行。先根据
[PyTorch 官方安装选择器](https://pytorch.org/get-started/locally/)确认 Windows + Pip + CPU
命令，再从 PyPI 官方端点安装项目 ML 依赖；安装后
把实际版本写入运行 manifest，不能只记录范围版本。

```powershell
conda activate intentfence
python -m pip install torch --index-url https://download.pytorch.org/whl/cpu
python -m pip install -e ".[ml,dev]" --index-url https://pypi.org/simple
python -m pip check
python -c "import torch, transformers; print(torch.__version__); print(transformers.__version__)"
```

如果 PyTorch 官方选择器给出的 CPU 命令与上面不同，以选择器为准，并把完整命令和版本记录到
运行日志。不要改用第三方镜像。

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

## 5. Small A/B/C

只有数据质量门和项目所有者训练授权通过后才运行。三份配置共享模型 revision、seed、batch、
学习率、epoch、max length 与损失权重，测试只允许运行名和输入模式不同：

| 变体 | 配置 | 输入 |
|---|---|---|
| A | `configs/deberta_small_text.yaml` | 外部内容 |
| B | `configs/deberta_small_context.yaml` | 用户任务 + 外部内容 |
| C | `configs/deberta_small.yaml` | 用户任务 + 外部内容 + 拟执行动作 |

每次使用独立输出目录，不能覆盖 checkpoint。运行前后记录 Git commit、配置 SHA-256、数据
manifest/SHA-256、seed、OS、CPU/GPU、RAM/VRAM、Python、PyTorch、Transformers、CUDA、
开始/结束时间和成本。Codex 只在用户提供这些日志后分析 H1/H2，不执行训练。
