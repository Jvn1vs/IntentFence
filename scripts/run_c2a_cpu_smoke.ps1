param(
    [Parameter(Mandatory = $true)]
    [string]$TrainPath,
    [Parameter(Mandatory = $true)]
    [string]$ValidationPath,
    [string]$OutputDirectory = "checkpoints/small-action-cpu-smoke-seed42",
    [switch]$PreflightOnly
)

$ErrorActionPreference = "Stop"
$RepositoryRoot = Split-Path -Parent $PSScriptRoot
$ConfigPath = Join-Path $RepositoryRoot "configs/deberta_small_cpu_smoke.yaml"
$ResolvedTrainPath = (Resolve-Path -LiteralPath $TrainPath).Path
$ResolvedValidationPath = (Resolve-Path -LiteralPath $ValidationPath).Path
if ([System.IO.Path]::IsPathRooted($OutputDirectory)) {
    $ResolvedOutputDirectory = $OutputDirectory
} else {
    $ResolvedOutputDirectory = Join-Path $RepositoryRoot $OutputDirectory
}

conda run -n intentfence intentfence-train `
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
conda run -n intentfence intentfence-train `
    --config $ConfigPath `
    --train $ResolvedTrainPath `
    --validation $ResolvedValidationPath `
    --output-dir $ResolvedOutputDirectory
if ($LASTEXITCODE -ne 0) {
    throw "C2a CPU smoke training failed."
}

conda run -n intentfence python (Join-Path $RepositoryRoot "scripts/verify_checkpoint.py") `
    --model-dir (Join-Path $ResolvedOutputDirectory "best")
if ($LASTEXITCODE -ne 0) {
    throw "C2a checkpoint reload verification failed."
}

$Stopwatch.Stop()
$EndedAt = (Get-Date).ToUniversalTime()
$StartedAtText = $StartedAt.ToString("o")
$EndedAtText = $EndedAt.ToString("o")
conda run -n intentfence python (Join-Path $RepositoryRoot "scripts/write_run_manifest.py") `
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
