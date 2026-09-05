param(
    [string]$TrainPath = "data/interim/route_b_v2_candidate_4/train.jsonl",
    [string]$ValidationPath = "data/interim/route_b_v2_candidate_4/validation.jsonl",
    [string]$OutputDirectory = "checkpoints/small-text-seed42",
    [string]$CondaExecutable = "conda",
    [switch]$PreflightOnly
)

$ErrorActionPreference = "Stop"
$RepositoryRoot = Split-Path -Parent $PSScriptRoot
$ConfigPath = Join-Path $RepositoryRoot "configs/deberta_small_text.yaml"

function Resolve-RepositoryPath {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path,
        [Parameter(Mandatory = $true)]
        [string]$RepositoryRoot
    )

    if ([System.IO.Path]::IsPathRooted($Path)) {
        return $Path
    }
    return Join-Path $RepositoryRoot $Path
}

$CandidateTrainPath = Resolve-RepositoryPath -Path $TrainPath -RepositoryRoot $RepositoryRoot
$CandidateValidationPath = Resolve-RepositoryPath -Path $ValidationPath -RepositoryRoot $RepositoryRoot
$ResolvedTrainPath = (Resolve-Path -LiteralPath $CandidateTrainPath).Path
$ResolvedValidationPath = (Resolve-Path -LiteralPath $CandidateValidationPath).Path
$ResolvedOutputDirectory = Resolve-RepositoryPath `
    -Path $OutputDirectory `
    -RepositoryRoot $RepositoryRoot

$CondaEnvironmentOutput = @(& $CondaExecutable run -n intentfence python -c "import sys; print(sys.executable)")
if ($LASTEXITCODE -ne 0) {
    throw "Unable to resolve the intentfence Conda Python. Open an Anaconda PowerShell prompt and retry."
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
Write-Host "Variant: Small A (text-only)"
Write-Host "Output: $ResolvedOutputDirectory"
& $IntentFencePython -c "import google.protobuf, torch; print(f'torch={torch.__version__}; protobuf={google.protobuf.__version__}')"
if ($LASTEXITCODE -ne 0) {
    throw "Small A training dependency preflight failed in: $IntentFencePython"
}

& $IntentFencePython -m intentfence.train `
    --config $ConfigPath `
    --train $ResolvedTrainPath `
    --validation $ResolvedValidationPath `
    --dry-run
if ($LASTEXITCODE -ne 0) {
    throw "Small A data preflight failed."
}

if ($PreflightOnly) {
    Write-Host "Small A preflight passed; training was not started."
    exit 0
}

if (Test-Path -LiteralPath $ResolvedOutputDirectory) {
    throw "Refusing to overwrite existing output directory: $ResolvedOutputDirectory"
}

$StartedAt = (Get-Date).ToUniversalTime()
$Stopwatch = [System.Diagnostics.Stopwatch]::StartNew()
& $IntentFencePython -m intentfence.train `
    --config $ConfigPath `
    --train $ResolvedTrainPath `
    --validation $ResolvedValidationPath `
    --output-dir $ResolvedOutputDirectory
if ($LASTEXITCODE -ne 0) {
    throw "Small A training failed."
}

& $IntentFencePython (Join-Path $RepositoryRoot "scripts/verify_checkpoint.py") `
    --model-dir (Join-Path $ResolvedOutputDirectory "best")
if ($LASTEXITCODE -ne 0) {
    throw "Small A checkpoint reload verification failed."
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
    throw "Small A run manifest generation failed."
}

Write-Host "Small A completed. Stop here and provide the output to Codex before running Small B."
