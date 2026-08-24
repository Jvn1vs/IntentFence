# C1 数据与基线框架：数据执行手册

状态：框架已实现。2026-08-24 当前执行断点：Conda 数据依赖预检和固定来源哈希核验已通过；第 3 节 BIPIA、第 4 节 InjecAgent 和第 5 节 NotInject 转换均已完成；下一步是第 6 节合并训练池并生成标签审核样本。真实标签确认和划分尚未开始。框架代码与文档按阶段推送功能分支，真实数据及 JSON/CSV 质量证据继续留在本地且不得提交。
执行者：Codex 或项目所有者均可执行本页第 1～8 节的数据命令。Codex 可以生成并预审第 6 节审核表，但现有 schema 的 `human_verified=true` 必须由项目所有者完成人类确认后才能应用。Codex 不执行学习基线拟合、模型训练、tiny-overfit、模型/校准参数更新或提前读取正式测试模型结果的命令。

## 0. 执行边界

本页把“框架完成”和“实验完成”分开：仓库内的单元测试只使用合成 fixture，不能替代真实数据结果。每一步都必须保留终端输出、manifest、转换报告和哈希；失败后应先诊断，不得跳过失败继续。Codex 执行真实数据步骤时同样遵守拒绝覆盖、阶段复核和不提交数据产物的规则。

统一使用 Conda。首次创建 CPU/数据环境时使用 Anaconda 官方源，再从 PyPI 官方源安装项目依赖：

```powershell
conda create --name intentfence python=3.12 pip `
  --override-channels `
  --channel https://repo.anaconda.com/pkgs/main `
  --yes
conda run --name intentfence python -m pip install -e ".[data,dev]" `
  --index-url https://pypi.org/simple
```

2026-08-23 用户环境检查已通过：Conda `intentfence`、Python 3.12.13、`pip check` 无损坏依赖、全部数据依赖导入成功、固定 BIPIA email builder 导入成功。`transformers` 提示未安装 PyTorch/TensorFlow/Flax 在当前数据阶段属于正常警告；模型阶段再按对应环境配置安装。后续数据和训练环境也只使用 Conda，不使用项目 `.venv`。

每次打开新的 PowerShell 窗口，先在仓库根目录运行下面的预检块。它不依赖当前是否已执行 `conda activate`，也不要求 `conda` 命令已加入 PATH；它从 Conda 的用户环境登记表解析 `intentfence` 的真实 Python。后续本页命令都使用 `Invoke-IntentFencePython`；该包装函数会在任何 Python 命令返回非零退出码时立即停止：

```powershell
Set-Location -LiteralPath "E:\IntentFence"
if (-not (Test-Path -LiteralPath "pyproject.toml" -PathType Leaf)) {
  throw "当前不在 IntentFence 仓库根目录"
}

$CondaEnvironmentRegistry = Join-Path $env:USERPROFILE ".conda\environments.txt"
if (-not (Test-Path -LiteralPath $CondaEnvironmentRegistry -PathType Leaf)) {
  throw "找不到 Conda 环境登记表：$CondaEnvironmentRegistry"
}

$IntentFencePrefixes = @(Get-Content -LiteralPath $CondaEnvironmentRegistry |
  Where-Object {
    $prefix = $_.Trim()
    $prefix -and
      (Split-Path -Leaf $prefix) -eq "intentfence" -and
      (Test-Path -LiteralPath (Join-Path $prefix "python.exe") -PathType Leaf)
  } |
  ForEach-Object { $_.Trim() } |
  Sort-Object -Unique)
if ($IntentFencePrefixes.Count -eq 0) {
  throw "Conda 环境登记表中没有可用的 intentfence"
}
if ($IntentFencePrefixes.Count -gt 1) {
  throw "发现多个同名 intentfence 环境：$($IntentFencePrefixes -join ', ')"
}
$IntentFencePython = Join-Path $IntentFencePrefixes[0] "python.exe"
if (-not (Test-Path -LiteralPath $IntentFencePython -PathType Leaf)) {
  throw "intentfence Python 路径无效：$IntentFencePython"
}

function Invoke-IntentFencePython {
  & $IntentFencePython @args
  if ($LASTEXITCODE -ne 0) {
    throw "intentfence Python 命令失败，已停止：$($args -join ' ')"
  }
}
```

首次安装项目，或 `pyproject.toml` 的 `data` 依赖已更新时，使用刚解析出的解释器安装/同步数据依赖：

```powershell
Invoke-IntentFencePython -m pip install -e ".[data,dev]" `
  --index-url https://pypi.org/simple
```

安装或同步后执行依赖预检：

```powershell

Invoke-IntentFencePython -m pip check
Invoke-IntentFencePython -c "import sys, huggingface_hub, intentfence, jsonlines, nltk, pandas, pyarrow, transformers, yaml; print(sys.executable); print('data dependencies: OK')"
Invoke-IntentFencePython -B -c "import sys; from pathlib import Path; sys.path.insert(0, str(Path('data/raw/bipia').resolve())); from bipia.data import AutoPIABuilder; assert AutoPIABuilder.from_name('email'); print('BIPIA email builder import: OK')"
```

其中 `pandas`、`jsonlines`、`nltk` 和 `transformers` 是固定 BIPIA email builder 生成路径的最小导入依赖。不要执行 `pip install -e data/raw/bipia`：上游 BIPIA 的完整实验依赖还会引入 `deepspeed`、`vllm`、`torch` 等当前 CPU/数据阶段不需要的大型包。项目 wrapper 直接使用固定源码，不需要安装整个上游包。

预检最后必须显示 `data dependencies: OK` 和 `BIPIA email builder import: OK`。BIPIA 导入检查使用 `-B` 禁止在固定上游源码目录生成 `.pyc` 缓存。如果关闭了 PowerShell，新窗口中要先重新运行“环境定位块 + 依赖预检块”；只有首次安装或依赖变更时才需重新运行 pip 同步块。

## 1. 先预览，不下载

下面的默认命令只打印来源、固定 revision、许可证发现和目标路径，不创建数据目录：

```powershell
Invoke-IntentFencePython scripts/download_sources.py bipia injecagent notinject
```

将输出与 `configs/upstream_sources.yaml` 对照。BIPIA 的代码是 MIT，但部分任务数据仍受各自来源条款约束；没有取得相应数据时，不运行 WebQA/Summarization 子任务。

## 2. 下载固定版本

项目所有者确认条款后，Codex 或项目所有者执行：

```powershell
Invoke-IntentFencePython scripts/download_sources.py bipia injecagent notinject `
  --execute `
  --acknowledge-source-terms
```

预期产物是被 `.gitignore` 排除的 `data/raw/<source>/`，以及 `data/raw/source_manifest.json`。Manifest 必须包含完整 revision、每个文件的大小和 SHA-256。不要提交原始数据。

如果多来源下载在中途中断，且已有部分来源目录，不要删除或覆盖它们。使用显式恢复模式重跑完整来源列表：

```powershell
Invoke-IntentFencePython scripts/download_sources.py bipia injecagent notinject `
  --execute `
  --acknowledge-source-terms `
  --resume
```

`--resume` 会在复用 Git 来源前核对固定 commit 并要求工作区干净；已存在的 Hugging Face snapshot 只有在旧 manifest 的 revision 和全部文件哈希均一致时才会复用。它只下载缺失来源，最后原子替换完整 manifest。默认模式仍拒绝任何已存在目录。

## 3. BIPIA：使用官方 builder 生成攻击上下文

先预览一项任务。以下 email 路径是固定 BIPIA 仓库中的公开示例；其他任务按官方条款分别处理：

```powershell
Invoke-IntentFencePython scripts/export_bipia_builder.py `
  --bipia-root data/raw/bipia `
  --task email `
  --contexts data/raw/bipia/benchmark/email/train.jsonl `
  --attacks data/raw/bipia/benchmark/text_attack_train.json `
  --output data/interim/bipia_email_attack_train.jsonl `
  --seed 42
```

确认预览后，依次运行以下三条完整命令：生成 attack export、严格转换 attack export、严格转换 clean context。任何一条报错都立即停止，不继续执行后一条：

```powershell
Invoke-IntentFencePython scripts/export_bipia_builder.py `
  --bipia-root data/raw/bipia `
  --task email `
  --contexts data/raw/bipia/benchmark/email/train.jsonl `
  --attacks data/raw/bipia/benchmark/text_attack_train.json `
  --output data/interim/bipia_email_attack_train.jsonl `
  --source-manifest data/raw/source_manifest.json `
  --report data/interim/bipia_email_attack_train.builder.json `
  --seed 42 `
  --execute

Invoke-IntentFencePython scripts/prepare_bipia.py `
  --kind generated `
  --input data/interim/bipia_email_attack_train.jsonl `
  --output data/interim/bipia_email_attack_train.canonical.jsonl

Invoke-IntentFencePython scripts/prepare_bipia.py `
  --kind clean `
  --task-name email `
  --input data/raw/bipia/benchmark/email/train.jsonl `
  --output data/interim/bipia_email_clean.canonical.jsonl
```

BIPIA 官方 builder 产生 `question/context/attack_name/attack_str/task_name/position`。它不提供真实拟执行动作，因此转换后 `action_provenance=missing`；在你补充并审计动作之前，这些行只能支持 A/B，不能支持动作模型 C。

上述 clean 命令已显式使用 `--kind clean --task-name email`。`train` 与 `test` 上游文件、`text_attack_train.json` 与 `text_attack_test.json` 必须保持角色隔离；本节的训练池命令只使用两个 `train` 上游文件。

如果 attack export 是在 builder sidecar 功能加入前已经生成的（当前 2026-08-23 的执行状态正是如此），不删除、不覆盖现有输出，也不用现在打断第 4～7 节。在执行第 8 节前，由 Codex 或项目所有者运行下面的复现验证：它会用相同固定 revision、task、seed 和两个已登记原始输入重建到临时文件，只有行数和字节 SHA-256 都与既有输出完全一致时，才原子生成 `status=reproduced_verified` 的 builder 报告：

```powershell
Invoke-IntentFencePython scripts/export_bipia_builder.py `
  --bipia-root data/raw/bipia `
  --task email `
  --contexts data/raw/bipia/benchmark/email/train.jsonl `
  --attacks data/raw/bipia/benchmark/text_attack_train.json `
  --output data/interim/bipia_email_attack_train.jsonl `
  --source-manifest data/raw/source_manifest.json `
  --report data/interim/bipia_email_attack_train.builder.json `
  --seed 42 `
  --verify-existing
```

该验证不会改写现有 export；如果重建哈希不一致会失败且不生成 passed 报告。不要使用人工声明替代复现验证。

## 4. InjecAgent：建立 Test B

当前 direct-harm 和 data-stealing 均已完成且覆盖保护已启用，**不要重跑本节命令**。data-stealing 报告记录 544/544 条成功转换、`skipped=0`、`split=test_b`、`action_provenance=benchmark_target`；输入和输出 SHA-256 已与现存文件复核一致。下面只保留已执行命令作为版本记录：

```powershell
Invoke-IntentFencePython scripts/prepare_injecagent.py `
  --attack-kind data-stealing `
  --input data/raw/injecagent/data/test_cases_ds_base.json `
  --output data/interim/injecagent_ds_test_b.jsonl
```

将来如果在新的版本目录从零重建，才先用相同脚本和 `--attack-kind direct-harm` 转换 `data/raw/injecagent/data/test_cases_dh_base.json`，再执行上述 data-stealing 命令；当前两组输出及 conversion report 已封存，不得覆盖。

适配器把 `Tool Response` 当作不可信内容，把 `Attacker Tools + Attacker Instruction` 记录为 `benchmark_target`。这不是被测 Agent 的真实输出动作，报告时不得写成 observed tool call。

## 5. NotInject：建立 Test C

本节已完成，**不要重跑下列命令**。三个官方子集各读取并转换 113 条，共 339 条；均为 `skipped=0`、`split=test_c`、`risk_label=benign`、`action_provenance=protocol_wrapper`。三份输入/输出 SHA-256 已与 conversion report 逐一复核，canonical schema 校验通过，跨子集重复 `sample_id=0`。下列命令仅作为版本记录：

```powershell
Invoke-IntentFencePython scripts/prepare_notinject.py `
  --input data/raw/notinject/data/NotInject_one-00000-of-00001.parquet `
  --output data/interim/notinject_one_test_c.jsonl

Invoke-IntentFencePython scripts/prepare_notinject.py `
  --input data/raw/notinject/data/NotInject_two-00000-of-00001.parquet `
  --output data/interim/notinject_two_test_c.jsonl

Invoke-IntentFencePython scripts/prepare_notinject.py `
  --input data/raw/notinject/data/NotInject_three-00000-of-00001.parquet `
  --output data/interim/notinject_three_test_c.jsonl
```

输出 SHA-256 分别为：one `ae0bfa1a1c945cf5efca365e3ab35a65567028d4b87c8cfe4fa33527b46cde03`、two `ae2b993b8c20e7c3245fd7bd26eee64514ecea040f949e1569c8a80ce129f763`、three `d349d441adf039f3420dacdb492ed565834bd43ee84c9ea1d201e7bea1304f93`。NotInject 没有 Agent 任务或动作，适配器使用公开、固定的良性 `protocol_wrapper`；它只用于过度防御压力测试，不能证明真实 Agent 效用。

## 6. 合并、标签审核与应用修订

用显式输入列表合并；脚本拒绝覆盖和重复 `sample_id`：

```powershell
Invoke-IntentFencePython scripts/merge_canonical.py `
  --input data/interim/bipia_email_clean.canonical.jsonl `
  --input data/interim/bipia_email_attack_train.canonical.jsonl `
  --output data/interim/bipia_train_pool.unverified.jsonl `
  --report data/interim/bipia_train_pool.unverified.merge.json
```

生成至少 200 条分层标签审核。抽样按来源、风险标签和动作 provenance 轮转；Codex 可以填写预审建议，但项目所有者必须逐条确认最终审核字段：

```powershell
Invoke-IntentFencePython scripts/audit_labels.py `
  --input data/interim/bipia_train_pool.unverified.jsonl `
  --output reports/data_quality/label_audit.csv `
  --size 200 `
  --seed 42
```

该命令还会生成 `label_audit.audit_key.json`，且只要 CSV 或 key 已存在就拒绝覆盖。Key 会封存固定 seed、分层抽样算法、有序样本 ID，以及每行不可编辑字段的摘要；生成后不要重跑并覆盖已有审核内容。CSV 中只有 `audit_status`、`new_risk_label`、`new_alignment_label`、`new_severity`、`notes`、`reviewer`、`reviewed_at` 可以填写或修改；不要改动样本 ID、来源、场景、原标签、原严重度、目标、不可信内容或动作字段，否则 summary 会拒绝该审计表。AI 预审建议不能直接作为正式 CSV 的独立人类审核记录；项目所有者确认后，正式 `reviewer` 和 `reviewed_at` 必须如实记录最终人类审核者及时间。Codex 随后可以执行 summary 和 apply 命令。

`audit_status` 只能填写 `correct`、`incorrect` 或 `ambiguous`。所有完成行必须填写列 `reviewer` 和 `reviewed_at`；`incorrect` 和 `ambiguous` 行必须在 `notes` 中说明理由。`incorrect` 行还必须满足：

- `new_risk_label`：`benign`、`instruction_hijacking`、`data_exfiltration`、`privilege_escalation` 或 `tool_manipulation`；
- `new_alignment_label`：只能是 `0` 或 `1`；`benign` 必须是 `0`，其他标签必须是 `1`；
- `new_severity`：`0`～`4` 的整数；`benign` 不得高于 `1`。

填写完成后先验证，再应用：

```powershell
Invoke-IntentFencePython scripts/summarize_label_audit.py `
  --input reports/data_quality/label_audit.csv `
  --audit-key reports/data_quality/label_audit.audit_key.json `
  --output reports/data_quality/label_audit_summary.json `
  --minimum-rows 200

Invoke-IntentFencePython scripts/apply_label_audit.py `
  --input data/interim/bipia_train_pool.unverified.jsonl `
  --audit reports/data_quality/label_audit.csv `
  --audit-key reports/data_quality/label_audit.audit_key.json `
  --output data/interim/bipia_train_pool.audited.jsonl `
  --report reports/data_quality/label_audit_application.json `
  --minimum-rows 200
```

如果 summary 校验失败，脚本只在终端打印错误，不会占用正式的 `label_audit_summary.json` 路径；修正 CSV 后可以原样重跑。只有 `status=passed` 才会写正式 summary。已通过的 summary、应用输出和报告都拒绝覆盖，不要通过删除后重跑来改写既有证据；如确需重建数据版本，应使用新的版本目录并重新生成整条哈希链。

`ambiguous` 行会从输出排除；未抽中的行保留 `human_verified=false`。未经项目所有者独立人类确认的 Codex 预审不能进入会设置 `human_verified=true` 的 apply 步骤，也不能误称为全量人工标注。

## 7. 去重、隔离划分与完整性校验

```powershell
Invoke-IntentFencePython scripts/build_splits.py `
  --input data/interim/bipia_train_pool.audited.jsonl `
  --fixed-input test_b=data/interim/injecagent_dh_test_b.jsonl `
  --fixed-input test_b=data/interim/injecagent_ds_test_b.jsonl `
  --fixed-input test_c=data/interim/notinject_one_test_c.jsonl `
  --fixed-input test_c=data/interim/notinject_two_test_c.jsonl `
  --fixed-input test_c=data/interim/notinject_three_test_c.jsonl `
  --output-dir data/processed/v1 `
  --seed 42 `
  --near-threshold 0.92
```

五个 `--fixed-input` 会把 InjecAgent 两部分固定合并为 `test_b.jsonl`，把 NotInject 三部分固定合并为 `test_c.jsonl`。正式 C1 build 会 fail-closed：`test_b` 或 `test_c` 缺少、出现额外角色、任一角色为空，或 manifest counts 与文件行数不一致时，在写入前失败。输出 manifest 的自哈希覆盖最终 counts、去重报告、固定外部输入列表和六个 split 文件的 SHA-256。校验时六个 `--input` 还必须逐角色指向 manifest 登记的同一文件；不能拿一份合法 manifest 校验另一组数据。然后运行全角色 context 完整性检查：

```powershell
Invoke-IntentFencePython scripts/validate_dataset.py `
  --manifest data/processed/v1/split_manifest.json `
  --input train=data/processed/v1/train.jsonl `
  --input validation=data/processed/v1/validation.jsonl `
  --input calibration=data/processed/v1/calibration.jsonl `
  --input test_a=data/processed/v1/test_a.jsonl `
  --input test_b=data/processed/v1/test_b.jsonl `
  --input test_c=data/processed/v1/test_c.jsonl `
  --input-mode context `
  --output reports/data_quality/context_integrity.json
```

Test B/C 含非空动作代理字段：InjecAgent 使用 `benchmark_target`，NotInject 使用固定 `protocol_wrapper`。可以另行验证字段非空且来源、角色与 provenance 策略一致：

```powershell
Invoke-IntentFencePython scripts/validate_dataset.py `
  --manifest data/processed/v1/split_manifest.json `
  --input test_b=data/processed/v1/test_b.jsonl `
  --input test_c=data/processed/v1/test_c.jsonl `
  --input-mode action `
  --output reports/data_quality/external_action_integrity.json
```

该外部 action 检查通过，只证明代理字段存在且其来源类型与角色策略一致；不证明 observed Agent action、真实工具调用、动作真实性或真实 Agent 效用。当前 BIPIA 官方数据没有拟执行动作，且仓库尚没有“补充并独立审计 BIPIA 动作”的已批准流程。因此本手册第 3～8 节可以完成 A/B 输入、Test B/C 代理证据和训练前数据报告，但不能让 train/validation/calibration/test_a 通过 `--input-mode action`，也不能支持模型 C 结论。仅有 `external_action_integrity` passed 不能解除这个阻塞；不得复制 target/wrapper 或随意填充 `proposed_action` 来绕过质量门。两份完整性报告通过后继续执行第 8 节；生成并提交训练前数据报告后再暂停，由项目所有者批准后续协议与动作构造/审计路线。

近重复检查会先用无损前缀过滤缩小候选集，再对候选执行精确 Jaccard 比较；数据很大时仍可能较慢。正式质量门不得使用 `--skip-near-duplicates`，该选项仅用于定位其他错误。
完整性校验失败时只打印失败报告并返回非零退出码，不写正式 `context_integrity.json` 或 `external_action_integrity.json`；修正问题后可原样重跑。成功报告一经写入即拒绝覆盖，避免不同 manifest 或参数静默改写证据。

## 8. 生成训练前数据报告

第 7 节两份完整性报告通过后，先补齐当前既有 BIPIA export 的复现 sidecar。即使你是从第 4 节当前断点一路向下执行，也不能跳过这一条：

```powershell
Invoke-IntentFencePython scripts/export_bipia_builder.py `
  --bipia-root data/raw/bipia `
  --task email `
  --contexts data/raw/bipia/benchmark/email/train.jsonl `
  --attacks data/raw/bipia/benchmark/text_attack_train.json `
  --output data/interim/bipia_email_attack_train.jsonl `
  --source-manifest data/raw/source_manifest.json `
  --report data/interim/bipia_email_attack_train.builder.json `
  --seed 42 `
  --verify-existing
```

成功后必须看到 `status=reproduced_verified`。然后生成机器可读统计、标签质量报告和数据卡。下面的命令不仅核对路径与哈希，还会重放七份原始输入到 canonical 的固定适配器、BIPIA merge、固定分层抽样及人工审计应用、去重和固定 seed 的六角色划分；同时验证来源 inventory、builder 复现报告与两份完整性报告。任何内容不一致、证据陈旧或证据缺失都会拒绝生成报告：

```powershell
Invoke-IntentFencePython scripts/build_dataset_reports.py `
  --manifest data/processed/v1/split_manifest.json `
  --input train=data/processed/v1/train.jsonl `
  --input validation=data/processed/v1/validation.jsonl `
  --input calibration=data/processed/v1/calibration.jsonl `
  --input test_a=data/processed/v1/test_a.jsonl `
  --input test_b=data/processed/v1/test_b.jsonl `
  --input test_c=data/processed/v1/test_c.jsonl `
  --source-manifest data/raw/source_manifest.json `
  --builder-report data/interim/bipia_email_attack_train.builder.json `
  --conversion-report data/interim/bipia_email_attack_train.canonical.conversion.json `
  --conversion-report data/interim/bipia_email_clean.canonical.conversion.json `
  --conversion-report data/interim/injecagent_dh_test_b.conversion.json `
  --conversion-report data/interim/injecagent_ds_test_b.conversion.json `
  --conversion-report data/interim/notinject_one_test_c.conversion.json `
  --conversion-report data/interim/notinject_two_test_c.conversion.json `
  --conversion-report data/interim/notinject_three_test_c.conversion.json `
  --merge-report data/interim/bipia_train_pool.unverified.merge.json `
  --audit-key reports/data_quality/label_audit.audit_key.json `
  --audit-summary reports/data_quality/label_audit_summary.json `
  --audit-application reports/data_quality/label_audit_application.json `
  --context-integrity reports/data_quality/context_integrity.json `
  --external-action-integrity reports/data_quality/external_action_integrity.json `
  --statistics-output reports/data_quality/dataset_statistics.json `
  --label-report-output reports/data_quality/label_quality_report.md `
  --data-card-output reports/data_quality/data_card.md
```

`dataset_statistics.json` 的 Risk × Alignment 列联表、条件概率和互信息只使用 `train`，不使用最终测试标签作协议决策。报告还会显式给出五类训练覆盖、Alignment 标签独立性和 Model C action readiness。`training_readiness` 中出现 `false` 是研究阻塞证据，不得通过改写报告或填充占位 action 消除。

三个报告生成并由 Codex 复核后，在这里暂停。项目所有者必须先根据 `docs/training_entry_decision.md` 批准协议处置和后续动作构造/独立审计路线；在该决定完成、C1 研究出口通过前，不进入正式模型训练，也不运行第 9 节所禁止的最终测试性能命令。

## 9. 基线框架已准备，但现在不要运行最终测试

规则基线不拟合参数，TF-IDF 会拟合参数，ProtectAI/PIGuard 还会下载大型权重。冻结协议规定 Test A/B/C 只在模型、校准器和运行矩阵全部冻结后执行一次。因此在进入模型训练前，**不要运行任何读取 `test_a.jsonl`、`test_b.jsonl` 或 `test_c.jsonl` 并产生性能分数的基线命令**；旧版手册中提前运行 TF-IDF Test A 的命令已撤回。

C1 只验证基线接口、固定 external revision、连续分数格式和 calibration-only 阈值逻辑；这些已经由合成 fixture 测试覆盖。正式阶段由项目所有者在 C3 使用统一矩阵运行 rules、word/char TF-IDF、ProtectAI、PIGuard 和冻结的 A/B/C 模型。PIGuard 的 pinned remote code 必须先由项目所有者审阅；外部权重下载也要在对应阶段单独确认。`baselines/run_all.py` 会直接汇总给定 test，只能用于合成 smoke，不能作为正式结果入口。

## 10. C1 用户出口清单

- `source_manifest.json` 中 revision 与冻结注册表一致，文件 SHA-256 完整；
- 每个转换报告 `status=converted_unverified`、`skipped=0`；
- 至少 200 条审计完成并通过 summary；
- ambiguous 已隔离，修订可追溯；
- split manifest 自哈希有效，每个 split 文件有 SHA-256；
- duplicate ID、精确重复、跨 split 模板组和近重复泄漏均为 0；
- `dataset_statistics.json`、`label_quality_report.md` 和 `data_card.md` 已生成，Risk × Alignment 关系、类别覆盖和训练阻塞均有记录；
- 正式 Test A/B/C 基线尚未提前运行；其接口和固定 revision 已通过合成验证，结果表留到 C3 单次正式评测；
- 动作实验的 train/validation/calibration/test_a 均没有 missing action；当前 BIPIA 路线尚未满足，因此该 C1 动作门仍为阻塞状态；
- 上述 manifest、报告和终端日志经 Codex 复核后，C1 研究出口才能标记完成。
