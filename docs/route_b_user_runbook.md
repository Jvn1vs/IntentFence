# Route B 训练前数据扩充手册

状态：框架已实现；协议仍为草案，真实 v2 数据构造和模型训练均未开放。

本手册只运行静态校验、精度规划和明确标记为 `framework_fixture_not_training_data`
的合成 fixture。它不会下载新数据、调用在线工具、拟合参数或生成模型权重。

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
Route B framework validation passed (draft remains training-blocked)
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

## 5. 完整本地验证

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

## 6. 当前禁止执行

- 不把 fixture 复制到 `data/processed` 并称为真实训练数据；
- 不从 InjecAgent、NotInject、AgentDojo 或已冻结 Test A/B/C/D 抽取训练样本；
- 不下载 WebQA/XSum、SecAlign/StruQ 或其他新来源；
- 不把 AI 预审写成第二名独立人类审核；
- 不运行 `intentfence-train`、TF-IDF 拟合、tiny-overfit、温度或阈值拟合。

下一阶段开始前，需要项目所有者批准 `docs/route_b_data_protocol.md` 的具体协议修订，
确认是否继续默认排除 CC BY-SA 来源，并登记第二名独立人工审核者。
