# Route B 训练前数据扩充手册

状态：框架和正式 candidate 4 已生成；协议仍未冻结，双人盲审与模型训练尚未完成。

本手册覆盖静态校验、精度规划、framework fixture、获批的项目自有离线 candidate
构造、完整性验证和双人盲审。它不会下载外部数据、调用在线工具、拟合参数或生成
模型权重。

## 0. 从哪里执行

在新的 PowerShell 窗口中，先切到仓库根目录并定位 Conda `intentfence` 的 Python：

```powershell
Set-Location -LiteralPath "E:\IntentFence"
if (-not (Test-Path -LiteralPath "pyproject.toml" -PathType Leaf)) {
  throw "当前不在 IntentFence 仓库根目录"
}

$CondaEnvironmentRegistry = Join-Path $env:USERPROFILE ".conda\environments.txt"
$IntentFencePrefixes = @(Get-Content -LiteralPath $CondaEnvironmentRegistry |
  Where-Object {
    $prefix = $_.Trim()
    $prefix -and
      (Split-Path -Leaf $prefix) -eq "intentfence" -and
      (Test-Path -LiteralPath (Join-Path $prefix "python.exe") -PathType Leaf)
  } |
  ForEach-Object { $_.Trim() } |
  Sort-Object -Unique)
if ($IntentFencePrefixes.Count -ne 1) {
  throw "需要且只能找到一个可用的 intentfence Conda 环境，实际：$($IntentFencePrefixes -join ', ')"
}
$IntentFencePython = Join-Path $IntentFencePrefixes[0] "python.exe"
```

后续命令直接使用 `& $IntentFencePython`，不依赖只在旧 PowerShell 会话中存在的
`Invoke-IntentFencePython` 函数。

## 1. 校验 Route B 框架

```powershell
& $IntentFencePython scripts/validate_route_b_framework.py
if ($LASTEXITCODE -ne 0) { throw "Route B 框架校验失败" }
```

预期输出：

```text
Route B framework validation passed (construction authorized; training blocked)
```

这里的 `passed` 只表示框架一致；括号明确说明训练仍被阻塞。

## 2. 查看 1% FPR 的样本精度候选

```powershell
& $IntentFencePython scripts/plan_route_b_precision.py
if ($LASTEXITCODE -ne 0) { throw "Route B 精度规划失败" }
```

也可以显式比较候选 benign 数量：

```powershell
& $IntentFencePython scripts/plan_route_b_precision.py `
  --target-rate 0.01 `
  --sample-size 1000 `
  --sample-size 2000 `
  --sample-size 5000
if ($LASTEXITCODE -ne 0) { throw "Route B 精度规划失败" }
```

该表是规划证据，不会修改 YAML，也不会自动冻结样本量。

## 3. 构造无副作用的 framework fixture

输出放入被 `.gitignore` 排除的 `artifacts/route_b_fixture/`。命令默认拒绝覆盖；若目录
已经存在，不要删除或覆盖，改用新的目录名。

```powershell
$RouteBFixtureDirectory = "artifacts\route_b_fixture_20260824"
if (Test-Path -LiteralPath $RouteBFixtureDirectory) {
  throw "fixture 目录已存在，请改用新的目录名：$RouteBFixtureDirectory"
}

& $IntentFencePython scripts/build_route_b_mock_fixture.py `
  --catalog tests/fixtures/route_b_mock_catalog.yaml `
  --output "$RouteBFixtureDirectory\samples.jsonl" `
  --trace-output "$RouteBFixtureDirectory\traces.jsonl"
if ($LASTEXITCODE -ne 0) { throw "Route B fixture 构造失败" }
```

预期 `records=10`、`traces=10`、`external_side_effects=false`。trace 中每条都必须是
`executed=false`；它只是捕获候选动作，不执行邮件、文件、权限或其他真实工具。

## 4. 运行结构校验

```powershell
& $IntentFencePython scripts/validate_route_b_dataset.py `
  --input "$RouteBFixtureDirectory\samples.jsonl"
if ($LASTEXITCODE -ne 0) { throw "Route B fixture 结构校验失败" }
```

预期 `errors=[]`，状态为 `structure_passed_readiness_blocked`，并保留三个 blocker：

- Route B 协议尚未冻结；
- 样本量精度/功效目标尚未冻结；
- `formal_training_authorized=false`。

不要对当前 fixture 使用 `--require-ready`，因为它故意不是训练数据。正式 v2 数据只有
在协议、来源、双人盲审、split、manifest 和质量报告全部完成后才允许通过该选项。

## 5. 正式 candidate 4（已由 Codex 完成）

当前不可覆盖目录：

```text
data\interim\route_b_v2_candidate_4
```

其中有 train 5,000、validation 2,000、calibration 10,000、Test A2 10,000，
合计 27,000 条。每个 base case 有完整 `5 Risk × 4 Alignment` 反事实矩阵；四角色
共有 270 个互斥 template group。不要重跑或删除当前目录。

复核 manifest：

```powershell
& $IntentFencePython scripts/validate_route_b_manifest.py `
  --manifest data/interim/route_b_v2_candidate_4/manifest.json
if ($LASTEXITCODE -ne 0) { throw "Route B manifest 复核失败" }
```

复核四角色结构、exact 和 0.92 template-representative near-duplicate：

```powershell
& $IntentFencePython scripts/validate_route_b_dataset.py `
  --input data/interim/route_b_v2_candidate_4/train.jsonl `
  --input data/interim/route_b_v2_candidate_4/validation.jsonl `
  --input data/interim/route_b_v2_candidate_4/calibration.jsonl `
  --input data/interim/route_b_v2_candidate_4/test_a.jsonl
if ($LASTEXITCODE -ne 0) { throw "Route B candidate 完整性复核失败" }
```

预期 `errors=[]`，同时仍显示协议、审核和训练授权 blocker。

## 6. 双人盲审包（已由 Codex 生成）

审核目录：

```text
data\interim\route_b_v2_candidate_4_audit_v2
```

`audit_manifest.json` 的密封 SHA-256 应为
`05eaf499f3666f096a4a2f9a189e40da95b96e8fd37ff4f6f012896f6049e612`；分析器会在读取审核结果时再次验证该清单及密封 seed 文件。

项目所有者先阅读 `docs/route_b_audit_rubric.md`。将下面两份只交给 reviewer A：

```text
reviewer_a_risk.csv
reviewer_a_alignment.csv
```

将下面两份只交给 reviewer B：

```text
reviewer_b_risk.csv
reviewer_b_alignment.csv
```

不要把 `sealed_seed_labels.json` 交给任何 reviewer。两人各自需要审核 400 条 Risk 和
400 条 Alignment；两套顺序不同，但抽样集合相同。AI 不能充当第二名人类审核者。

四份表完成并保存原始副本后，运行：

```powershell
& $IntentFencePython scripts/analyze_route_b_blind_audits.py `
  --reviewer-a-risk data/interim/route_b_v2_candidate_4_audit_v2/reviewer_a_risk.csv `
  --reviewer-b-risk data/interim/route_b_v2_candidate_4_audit_v2/reviewer_b_risk.csv `
  --reviewer-a-alignment data/interim/route_b_v2_candidate_4_audit_v2/reviewer_a_alignment.csv `
  --reviewer-b-alignment data/interim/route_b_v2_candidate_4_audit_v2/reviewer_b_alignment.csv `
  --sealed-seed-labels data/interim/route_b_v2_candidate_4_audit_v2/sealed_seed_labels.json `
  --audit-manifest data/interim/route_b_v2_candidate_4_audit_v2/audit_manifest.json `
  --output data/interim/route_b_v2_candidate_4_audit_v2/audit_analysis.json
if ($LASTEXITCODE -ne 0) { throw "Route B 双人盲审分析失败" }
```

分析器会拒绝修改过的题目列、相同 reviewer ID、缺少时区的时间、非法标签或未说明的
`unable_to_determine`，并计算原始一致率、Cohen's kappa、逐类 seed agreement 和动作
realism。即使全部通过，报告仍保持 `formal_training_authorized=false`，直到协议冻结。

## 7. Readiness 聚合与协议封存

readiness 工具会重放 candidate manifest、核对完整性报告与候选 split、重放双人盲审
分析，并验证协议锁和公开聚合报告。任何输入缺失、哈希漂移、审核门失败或协议未冻结，
都只会生成 `formal_training_authorized=false` 并以非零状态退出。

在审核尚未完成的当前状态，可运行一次 fail-closed 预检（预期退出码为 1）：

```powershell
& $IntentFencePython scripts/build_route_b_readiness.py `
  --candidate-manifest data/interim/route_b_v2_candidate_4/manifest.json `
  --integrity-report data/interim/route_b_v2_candidate_4/route_b_integrity_report_v3.json `
  --public-report reports/data_quality/route_b_candidate_4_card.md `
  --output data/interim/route_b_v2_candidate_4/readiness_preflight.json
if ($LASTEXITCODE -ne 1) { throw "未完成审核时 readiness 必须 fail-closed" }
```

只有四份审核表完成、分析通过且无需分歧裁决后，项目所有者才能：

1. 更新公开聚合卡，保留原始审核文件和哈希；
2. 将 YAML/Markdown 协议批准为精确版本 `2.0.0`，记录带时区的 `approved_at`，冻结
   样本量目标，并显式设置两项 readiness 布尔值；
3. 亲自确认并执行协议锁命令：

```powershell
& $IntentFencePython scripts/freeze_route_b_protocol.py `
  --confirm-project-owner-approval `
  --output configs/route_b_protocol_lock.json
if ($LASTEXITCODE -ne 0) { throw "Route B 协议封存失败" }
```

随后生成最终 readiness 报告：

```powershell
& $IntentFencePython scripts/build_route_b_readiness.py `
  --protocol-lock configs/route_b_protocol_lock.json `
  --candidate-manifest data/interim/route_b_v2_candidate_4/manifest.json `
  --integrity-report data/interim/route_b_v2_candidate_4/route_b_integrity_report_v3.json `
  --audit-analysis data/interim/route_b_v2_candidate_4_audit_v2/audit_analysis.json `
  --audit-manifest data/interim/route_b_v2_candidate_4_audit_v2/audit_manifest.json `
  --public-report reports/data_quality/route_b_candidate_4_card.md `
  --output data/interim/route_b_v2_candidate_4/readiness.json
if ($LASTEXITCODE -ne 0) { throw "Route B readiness 未通过，禁止训练" }
```

若审核报告为 `quality_gates_passed_adjudication_required`，当前工具会继续阻塞；必须先
保留两份原始意见并完成可追溯裁决，不能用命令行开关绕过。即使 readiness 通过，
训练执行者仍固定为项目所有者，最终测试锁继续生效。

## 8. 完整本地验证

```powershell
& $IntentFencePython -m ruff check .
if ($LASTEXITCODE -ne 0) { throw "Ruff 失败" }

& $IntentFencePython -m pytest -q
if ($LASTEXITCODE -ne 0) { throw "pytest 失败" }

& $IntentFencePython -m compileall -q src baselines benchmarks scripts deployment
if ($LASTEXITCODE -ne 0) { throw "compileall 失败" }

& $IntentFencePython -m build --wheel
if ($LASTEXITCODE -ne 0) { throw "wheel 构建失败" }
```

## 9. 当前禁止执行

- 不把 fixture 复制到 `data/processed` 并称为真实训练数据；
- 不从 InjecAgent、NotInject、AgentDojo 或已冻结 Test A/B/C/D 抽取训练样本；
- 不下载 WebQA/XSum、SecAlign/StruQ 或其他新来源；
- 不把 AI 预审写成第二名独立人类审核；
- 不运行 `intentfence-train`、TF-IDF 拟合、tiny-overfit、温度或阈值拟合。

readiness 聚合和协议封存框架现已具备。当前仍缺人类双盲审核、可能的分歧裁决、协议
最终冻结和真实 v2 readiness 报告；审核通过前不得把 candidate 4 复制为训练就绪版本。
