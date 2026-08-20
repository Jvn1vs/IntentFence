# C1 数据与基线框架：用户执行手册

状态：框架已实现，真实数据尚未执行。
执行者：仅项目所有者（用户）。Codex 不执行本页的下载、转换、合并、去重、划分、人工审计、基线拟合或训练命令。

## 0. 执行边界

本页把“框架完成”和“实验完成”分开：仓库内的单元测试只使用合成 fixture，不能替代真实数据结果。你运行每一步后，应保留终端输出、manifest、转换报告和哈希；如果失败，把日志发给 Codex 分析，不要跳过失败继续训练。

安装数据工具依赖：

```powershell
python -m pip install -e ".[data,dev]"
```

## 1. 先预览，不下载

下面的默认命令只打印来源、固定 revision、许可证发现和目标路径，不创建数据目录：

```powershell
python scripts/download_sources.py bipia injecagent notinject
```

将输出与 `configs/upstream_sources.yaml` 对照。BIPIA 的代码是 MIT，但部分任务数据仍受各自来源条款约束；没有取得相应数据时，不运行 WebQA/Summarization 子任务。

## 2. 由你下载固定版本

确认条款后，由你亲自执行：

```powershell
python scripts/download_sources.py bipia injecagent notinject `
  --execute `
  --acknowledge-source-terms
```

预期产物是被 `.gitignore` 排除的 `data/raw/<source>/`，以及 `data/raw/source_manifest.json`。Manifest 必须包含完整 revision、每个文件的大小和 SHA-256。不要提交原始数据。

## 3. BIPIA：使用官方 builder 生成攻击上下文

先预览一项任务。以下 email 路径是固定 BIPIA 仓库中的公开示例；其他任务按官方条款分别处理：

```powershell
python scripts/export_bipia_builder.py `
  --bipia-root data/raw/bipia `
  --task email `
  --contexts data/raw/bipia/benchmark/email/train.jsonl `
  --attacks data/raw/bipia/benchmark/text_attack_train.json `
  --output data/interim/bipia_email_attack_train.jsonl `
  --seed 42
```

确认预览后，加 `--execute` 由你生成，再严格转换：

```powershell
python scripts/export_bipia_builder.py `
  --bipia-root data/raw/bipia `
  --task email `
  --contexts data/raw/bipia/benchmark/email/train.jsonl `
  --attacks data/raw/bipia/benchmark/text_attack_train.json `
  --output data/interim/bipia_email_attack_train.jsonl `
  --seed 42 `
  --execute

python scripts/prepare_bipia.py `
  --kind generated `
  --input data/interim/bipia_email_attack_train.jsonl `
  --output data/interim/bipia_email_attack_train.canonical.jsonl
```

BIPIA 官方 builder 产生 `question/context/attack_name/attack_str/task_name/position`。它不提供真实拟执行动作，因此转换后 `action_provenance=missing`；在你补充并审计动作之前，这些行只能支持 A/B，不能支持动作模型 C。

清洁上下文使用 `--kind clean --task-name email` 转换。`train` 与 `test` 上游文件、`text_attack_train.json` 与 `text_attack_test.json` 必须保持角色隔离。

## 4. InjecAgent：建立 Test B

分别转换 direct-harm 与 data-stealing 的 base 文件：

```powershell
python scripts/prepare_injecagent.py `
  --attack-kind direct-harm `
  --input data/raw/injecagent/data/test_cases_dh_base.json `
  --output data/interim/injecagent_dh_test_b.jsonl

python scripts/prepare_injecagent.py `
  --attack-kind data-stealing `
  --input data/raw/injecagent/data/test_cases_ds_base.json `
  --output data/interim/injecagent_ds_test_b.jsonl
```

适配器把 `Tool Response` 当作不可信内容，把 `Attacker Tools + Attacker Instruction` 记录为 `benchmark_target`。这不是被测 Agent 的真实输出动作，报告时不得写成 observed tool call。

## 5. NotInject：建立 Test C

NotInject 固定 revision 包含 Parquet 文件。对三个官方子集分别运行转换，例如：

```powershell
python scripts/prepare_notinject.py `
  --input data/raw/notinject/data/NotInject_one-00000-of-00001.parquet `
  --output data/interim/notinject_one_test_c.jsonl
```

重复处理 `NotInject_two` 和 `NotInject_three`。NotInject 没有 Agent 任务或动作，适配器使用公开、固定的良性 `protocol_wrapper`；它只用于过度防御压力测试，不能证明真实 Agent 效用。

## 6. 合并、人工审计与应用修订

用显式输入列表合并；脚本拒绝覆盖和重复 `sample_id`：

```powershell
python scripts/merge_canonical.py `
  --input data/interim/bipia_email_clean.canonical.jsonl `
  --input data/interim/bipia_email_attack_train.canonical.jsonl `
  --output data/interim/bipia_train_pool.unverified.jsonl
```

由你生成并完成至少 200 条分层审计。抽样按来源、风险标签和动作 provenance 轮转：

```powershell
python scripts/audit_labels.py `
  --input data/interim/bipia_train_pool.unverified.jsonl `
  --output reports/data_quality/label_audit.csv `
  --size 200 `
  --seed 42
```

`audit_status` 只能填写 `correct`、`incorrect` 或 `ambiguous`。`incorrect` 必须填写新风险标签、新 alignment 和新 severity；所有完成行必须填写 reviewer/date。先验证，再应用：

```powershell
python scripts/summarize_label_audit.py `
  --input reports/data_quality/label_audit.csv `
  --output reports/data_quality/label_audit_summary.json `
  --minimum-rows 200

python scripts/apply_label_audit.py `
  --input data/interim/bipia_train_pool.unverified.jsonl `
  --audit reports/data_quality/label_audit.csv `
  --output data/interim/bipia_train_pool.audited.jsonl `
  --report reports/data_quality/label_audit_application.json `
  --minimum-rows 200
```

`ambiguous` 行会从输出排除；未抽中的行保留 `human_verified=false`，不能误称为全量人工标注。

## 7. 去重、隔离划分与完整性校验

```powershell
python scripts/build_splits.py `
  --input data/interim/bipia_train_pool.audited.jsonl `
  --output-dir data/processed/v1 `
  --seed 42 `
  --near-threshold 0.92
```

输出 manifest 的哈希覆盖最终 counts、去重报告和每个 split 文件的 SHA-256。然后由你运行：

```powershell
python scripts/validate_dataset.py `
  --input train=data/processed/v1/train.jsonl `
  --input validation=data/processed/v1/validation.jsonl `
  --input calibration=data/processed/v1/calibration.jsonl `
  --input test_a=data/processed/v1/test_a.jsonl `
  --input-mode context `
  --output reports/data_quality/context_integrity.json
```

动作模式必须改为 `--input-mode action`，并且 train/validation/calibration 中不能有缺失动作。近重复检查是精确的全对比较，数据很大时可能较慢；正式质量门不得使用 `--skip-near-duplicates`，该选项仅用于定位其他错误。

## 8. 基线与训练仍由你运行

规则基线不拟合参数；TF-IDF 会拟合参数。为遵守执行边界，Codex 不运行任何真实数据基线。正式结果不要使用旧式“训练后直接在测试集汇总”的快捷方式；由你先训练，再分别保存 calibration/test 连续分数：

```powershell
python baselines/tfidf.py `
  --train data/processed/v1/train.jsonl `
  --analyzer word `
  --output artifacts/tfidf_word.joblib

python -m baselines.predict `
  --backend tfidf `
  --model artifacts/tfidf_word.joblib `
  --input data/processed/v1/calibration.jsonl `
  --output artifacts/tfidf_word_calibration.jsonl

python -m baselines.predict `
  --backend tfidf `
  --model artifacts/tfidf_word.joblib `
  --input data/processed/v1/test_a.jsonl `
  --output artifacts/tfidf_word_test_a.jsonl

python -m baselines.evaluate_scores `
  --calibration artifacts/tfidf_word_calibration.jsonl `
  --test artifacts/tfidf_word_test_a.jsonl `
  --output reports/tables/tfidf_word_test_a.json
```

字符 TF-IDF 将 `--analyzer` 改为 `char`。规则、ProtectAI 和 PIGuard 使用 `python -m baselines.predict` 的对应 backend；外部模型 ID/revision 必须照抄 `configs/baseline_sources.yaml`。PIGuard 使用固定 revision 的 Hugging Face remote code，你必须先审阅该 revision 再运行。阈值评估脚本只从 calibration 分数选阈值，测试分数即使出现更优阈值也不得回调。

## 9. C1 用户出口清单

- `source_manifest.json` 中 revision 与冻结注册表一致，文件 SHA-256 完整；
- 每个转换报告 `status=converted_unverified`、`skipped=0`；
- 至少 200 条审计完成并通过 summary；
- ambiguous 已隔离，修订可追溯；
- split manifest 自哈希有效，每个 split 文件有 SHA-256；
- duplicate ID、精确重复、跨 split 模板组和近重复泄漏均为 0；
- 动作实验的训练/验证/校准行没有 missing action；
- 你把上述 manifest、报告和终端日志提供给 Codex 复核后，C1 研究出口才能标记完成。
