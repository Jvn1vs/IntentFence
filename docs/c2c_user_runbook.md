# C2c 独立校准与阈值冻结运行手册

状态：C2c 工程框架已准备；Codex 不导出真实模型 logits、不拟合温度或阈值，也不访问最终测试结果。
真实校准只能由项目所有者在模型权重冻结、独立人类审核完成并形成单独授权后亲自执行。

## 1. 只读 calibration 输入预检

`export_logits.py --preflight-only` 只读取 JSONL，要求每条样本显式标记
`split="calibration"`，不加载 tokenizer/模型、不创建输出文件：

```powershell
Set-Location E:\IntentFence
python scripts/export_logits.py `
  --input data\interim\route_b_v2_candidate_8\calibration.jsonl `
  --output artifacts\c2c\seed42\calibration_logits.npz `
  --preflight-only
```

通过后，项目所有者才能在冻结的 `best/` checkpoint 上执行真正的 logits 导出：

```powershell
python scripts/export_logits.py `
  --model-dir checkpoints\base-action-multitask-seed42\best `
  --input data\interim\route_b_v2_candidate_8\calibration.jsonl `
  --output artifacts\c2c\seed42\calibration_logits.npz `
  --device cuda
```

脚本会同时写入同名 `.json` sidecar，记录 calibration split、输入文件 SHA-256、样本数、
模型目录、输入模式和 logits 形状；NPZ 或 sidecar 已存在时拒绝覆盖。

## 2. 校准输入预检

导出完成后，先运行不拟合、不写文件的校准预检：

```powershell
python scripts/calibrate.py `
  --logits artifacts\c2c\seed42\calibration_logits.npz `
  --output artifacts\c2c\seed42\calibration.json `
  --report reports\calibration\seed42.json `
  --preflight-only
```

它会验证四个数组、Risk `[N,5]`、Alignment `[N,2]` 或 `[N,4]`、有限 logits、benign/attack
覆盖、输入 sidecar 的 calibration split 和输入文件哈希。输出与报告路径必须为空。

## 3. 项目所有者授权与正式校准

项目所有者在独立人类审核和权重冻结后，创建不提交仓库的授权文件。下面只是字段模板，不能
由 Codex 填写，也不能用 AI 预审替代 `human_verified=true`：

```json
{
  "calibration_authorized": true,
  "human_verified": true,
  "final_test_lock_preserved": true,
  "approved_by_project_owner": "<owner id>",
  "approved_at": "<timezone-aware ISO-8601 timestamp>",
  "model_dir": "<exact model_dir from calibration_logits.json>",
  "logits_sha256": "<sha256 of calibration_logits.npz>",
  "input_sha256": "<input_sha256 from calibration_logits.json>"
}
```

正式命令只由项目所有者执行：

```powershell
python scripts/calibrate.py `
  --logits artifacts\c2c\seed42\calibration_logits.npz `
  --output artifacts\c2c\seed42\calibration.json `
  --report reports\calibration\seed42.json `
  --authorization-file data\interim\route_b_v2_candidate_8\calibration_authorization.json `
  --target-fpr 0.01
```

命令会拒绝缺失/不匹配授权、非时区时间戳、sidecar 哈希不一致和已有输出。报告将分别记录
Risk 与 Alignment 的校准前后 ECE、Brier、NLL、reliability diagram 分箱、classwise ECE、
冻结阈值及其 calibration-only 来源；类别支持不足时对应 classwise ECE 标记为
`insufficient_class_support`，不会伪造数值。

校准完成后才可进入最终测试冻结流程。不得读取 Test A/B/C 结果来回调温度、阈值或策略。
