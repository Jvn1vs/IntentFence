param(
    [Parameter(Mandatory = $true)]
    [string]$TrainPath,
    [Parameter(Mandatory = $true)]
    [string]$ValidationPath,
    [string]$OutputDirectory = "checkpoints/small-action-cpu-smoke-seed42",
    [string]$CondaExecutable = "conda",
    [switch]$PreflightOnly
)

$ErrorActionPreference = "Stop"
$RepositoryRoot = Split-Path -Parent $PSScriptRoot
$ConfigPath = Join-Path $RepositoryRoot "configs/deberta_small_cpu_smoke.yaml"
$ResolvedTrainPath = (Resolve-Path -LiteralPath $TrainPath).Path
$ResolvedValidationPath = (Resolve-Path -LiteralPath $ValidationPath).Path
$CondaEnvironmentOutput = @(& $CondaExecutable run -n intentfence python -c "import sys; print(sys.executable)")
if ($LASTEXITCODE -ne 0) {
    throw "Unable to resolve the intentfence Conda Python."
}
$IntentFencePythonCandidates = @(
    $CondaEnvironmentOutput |
        ForEach-Object { $_.Trim() } |
        Where-Object { $_ -match "(?i)python\.exe$" }
)
if ($IntentFencePythonCandidates.Count -ne 1) {
    throw "Expected exactly one intentfence Python path; received: $($CondaEnvironmentOutput -join ', ')"
}
$IntentFencePython = $IntentFencePythonCandidates[0]
if (-not (Test-Path -LiteralPath $IntentFencePython -PathType Leaf)) {
    throw "Resolved intentfence Python does not exist: $IntentFencePython"
}
Write-Host "Using intentfence Python: $IntentFencePython"
& $IntentFencePython -c "import google.protobuf, torch; print(f'torch={torch.__version__}; protobuf={google.protobuf.__version__}')"
if ($LASTEXITCODE -ne 0) {
    throw "C2a training dependency preflight failed in: $IntentFencePython"
}
if ([System.IO.Path]::IsPathRooted($OutputDirectory)) {
    $ResolvedOutputDirectory = $OutputDirectory
} else {
    $ResolvedOutputDirectory = Join-Path $RepositoryRoot $OutputDirectory
}

& $IntentFencePython -m intentfence.train `
    --config $ConfigPath `
    --train $ResolvedTrainPath `
    --validation $ResolvedValidationPath `
    --dry-run
if ($LASTEXITCODE -ne 0) {
    throw "C2a CPU smoke preflight failed."
}

if ($PreflightOnly) {
    Write-Host "Preflight passed; training was not started."
    exit 0
}

$StartedAt = (Get-Date).ToUniversalTime()
$Stopwatch = [System.Diagnostics.Stopwatch]::StartNew()
& $IntentFencePython -m intentfence.train `
    --config $ConfigPath `
    --train $ResolvedTrainPath `
    --validation $ResolvedValidationPath `
    --output-dir $ResolvedOutputDirectory
if ($LASTEXITCODE -ne 0) {
    throw "C2a CPU smoke training failed."
}

& $IntentFencePython (Join-Path $RepositoryRoot "scripts/verify_checkpoint.py") `
    --model-dir (Join-Path $ResolvedOutputDirectory "best")
if ($LASTEXITCODE -ne 0) {
    throw "C2a checkpoint reload verification failed."
}

$Stopwatch.Stop()
$EndedAt = (Get-Date).ToUniversalTime()
$StartedAtText = $StartedAt.ToString("o")
$EndedAtText = $EndedAt.ToString("o")
& $IntentFencePython (Join-Path $RepositoryRoot "scripts/write_run_manifest.py") `
    --repository-root $RepositoryRoot `
    --config $ConfigPath `
    --train $ResolvedTrainPath `
    --validation $ResolvedValidationPath `
    --checkpoint-dir (Join-Path $ResolvedOutputDirectory "best") `
    --output (Join-Path $ResolvedOutputDirectory "run_manifest.json") `
    --started-at $StartedAtText `
    --ended-at $EndedAtText `
    --duration-seconds $Stopwatch.Elapsed.TotalSeconds `
    --cost-usd 0
if ($LASTEXITCODE -ne 0) {
    throw "C2a run manifest generation failed."
}
