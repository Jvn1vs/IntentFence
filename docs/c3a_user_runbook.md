# C3a 最终 Test A/B/C 与错误分析运行手册

状态：C3a 的固定阈值评测、分组摘要、cluster bootstrap、Wilson 区间、错误分析和一次性
final-test ledger 框架已完成；没有真实 Test A/B/C 结果。Codex 不读取最终测试数据、不启动
正式模型评测，也不替项目所有者填写授权。

## 1. 一次性矩阵原则

正式矩阵必须同时包含 Test A、Test B、Test C，并使用已冻结的 calibration-derived attack
threshold。`configs/experiment_registry.yaml` 要求每个 protocol 版本只能有一次正式测试。
`run_final_matrix.py` 会把 protocol、模型目录、校准器、校准报告、三份测试输入和阈值的
SHA-256 写入独占 ledger；ledger 或输出目录已存在时拒绝运行。

## 2. 项目所有者只读预检

项目所有者先完成模型/校准/阈值冻结，再运行：

```powershell
Set-Location E:\IntentFence
python scripts/run_final_matrix.py `
  --model-dir checkpoints\base-action-multitask-seed42\best `
  --calibration artifacts\c2c\seed42\calibration.json `
  --calibration-report reports\calibration\seed42.json `
  --test-a data\interim\route_b_v2_candidate_8\test_a.jsonl `
  --test-b data\interim\route_b_v2_candidate_8\test_b.jsonl `
  --test-c data\interim\route_b_v2_candidate_8\test_c.jsonl `
  --attack-threshold <threshold-from-calibration-report> `
  --authorization-file data\interim\route_b_v2_candidate_8\final_test_authorization.json `
  --ledger-file artifacts\c3a\final_test_ledger.json `
  --output-dir artifacts\c3a\seed42 `
  --run-id c3a-seed42 `
  --preflight-only
```

预检会读取并哈希指定文件，但不会加载模型、运行推理或写 ledger/结果。`test_a`、`test_b`
和 `test_c` 必须保持协议指定的角色与独立性。

## 3. 授权文件

授权文件不提交仓库。它必须由项目所有者在独立人类审核、权重冻结和校准冻结后创建，不能
用 AI 审核替代人审：

```json
{
  "formal_final_test_authorized": true,
  "human_verified": true,
  "final_test_lock_preserved": true,
  "protocol_version": "1.0.0",
  "test_splits": ["test_a", "test_b", "test_c"],
  "frozen_attack_threshold": 0.0,
  "approved_by_project_owner": "<owner id>",
  "approved_at": "<timezone-aware ISO-8601 timestamp>",
  "model_dir": "<exact resolved model directory>",
  "model_artifact_sha256": "<directory tree hash>",
  "calibration_path": "<exact resolved calibration JSON>",
  "calibration_sha256": "<file hash>",
  "calibration_report_path": "<exact resolved calibration report>",
  "calibration_report_sha256": "<file hash>",
  "test_input_paths": {
    "test_a": "<exact resolved path>",
    "test_b": "<exact resolved path>",
    "test_c": "<exact resolved path>"
  },
  "test_input_sha256": {
    "test_a": "<file hash>",
    "test_b": "<file hash>",
    "test_c": "<file hash>"
  }
}
```

模板中的 `0.0` 只是 JSON 类型示例，必须替换为 calibration report 中实际冻结的阈值。

## 4. 正式矩阵与分析

预检通过且授权成立后，仍由项目所有者亲自执行同一命令，去掉 `--preflight-only`，并使用
GPU/CPU 已记录的实际 `--device`。失败后 ledger 保持 claimed，不能自动重试或另起同协议
矩阵。

每个 split 产生 `predictions.jsonl` 和 `metrics.json`。预测记录包含 split、template group、
scenario、attack family、内容长度桶、模型 revision 和固定阈值来源。随后可对已产生的单个
结果运行分析器：

```powershell
python scripts/analyze_predictions.py `
  --predictions artifacts\c3a\seed42\test_b\predictions.jsonl `
  --expected-split test_b `
  --attack-threshold <same-frozen-threshold> `
  --output-json reports\c3a\seed42\test_b_analysis.json `
  --output-markdown reports\c3a\seed42\test_b_analysis.md
```

分析器不重新选择阈值；它使用固定阈值报告 Macro-F1、Risk 指标、cluster bootstrap CI、
NotInject 风格的精确 benign 误报与 Wilson 区间、scenario/attack-family/长度分组和紧凑
错误案例。错误分析只保存 sample ID 与非内容元数据，不复制原始不可信内容。

H1～H4 的两变体比较使用相同 sample ID、template group 和标签，并允许各变体使用各自已冻结
的 calibration threshold：

```powershell
python scripts/compare_predictions.py `
  --baseline artifacts\c3a\seed42\A\test_a\predictions.jsonl `
  --candidate artifacts\c3a\seed42\B\test_a\predictions.jsonl `
  --expected-split test_a `
  --baseline-threshold <A-threshold> `
  --candidate-threshold <B-threshold> `
  --endpoint fpr `
  --output reports\c3a\seed42\H1_test_a_fpr.json
```

比较结果是 candidate-minus-baseline 的 paired cluster bootstrap 区间；不匹配的 sample、
标签、template group、场景或长度桶会直接失败，不会静默重排或补造配对。
