param(
    [Parameter(Mandatory = $true)]
    [string]$ConfigPath,
    [Parameter(Mandatory = $true)]
    [string]$TrainPath,
    [Parameter(Mandatory = $true)]
    [string]$ValidationPath,
    [Parameter(Mandatory = $true)]
    [string]$OutputDirectory,
    [string]$AuthorizationFile = "data/interim/route_b_v2_candidate_8/training_authorization.json",
    [string]$ExpectedCandidate = "route_b_v2_candidate_8",
    [double]$CostCny = -1,
    [switch]$RequireCuda,
    [switch]$PreflightOnly
)

$ErrorActionPreference = "Stop"
$RepositoryRoot = Split-Path -Parent $PSScriptRoot

function Resolve-RepositoryPath {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path,
        [Parameter(Mandatory = $true)]
        [string]$Root
    )

    if ([System.IO.Path]::IsPathRooted($Path)) {
        return $Path
    }
    return Join-Path $Root $Path
}

$ResolvedConfigPath = (Resolve-Path -LiteralPath (Resolve-RepositoryPath $ConfigPath $RepositoryRoot)).Path
$ResolvedTrainPath = (Resolve-Path -LiteralPath (Resolve-RepositoryPath $TrainPath $RepositoryRoot)).Path
$ResolvedValidationPath = (Resolve-Path -LiteralPath (Resolve-RepositoryPath $ValidationPath $RepositoryRoot)).Path
$ResolvedOutputDirectory = Resolve-RepositoryPath $OutputDirectory $RepositoryRoot

if ($CostCny -lt -1) {
    throw "CostCny must be -1 for preflight or a non-negative actual cost for a training run."
}
if (-not (Get-Command conda -ErrorAction SilentlyContinue)) {
    throw "Unable to resolve conda. Open an Anaconda PowerShell prompt and retry."
}

$CondaEnvironmentOutput = @(& conda run -n intentfence python -c "import sys; print(sys.executable)")
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
Write-Host "Config: $ResolvedConfigPath"
Write-Host "Train: $ResolvedTrainPath"
Write-Host "Validation: $ResolvedValidationPath"
Write-Host "Output: $ResolvedOutputDirectory"

$ConfigCheck = @'
import re
import sys
from pathlib import Path

import yaml

payload = yaml.safe_load(Path(sys.argv[1]).read_text(encoding="utf-8"))
if not isinstance(payload, dict):
    raise SystemExit("config must be a mapping")
if payload.get("model_name") != "microsoft/deberta-v3-base":
    raise SystemExit("C2b requires microsoft/deberta-v3-base")
revision = str(payload.get("model_revision", ""))
if not re.fullmatch(r"[0-9a-f]{40}", revision):
    raise SystemExit("config model_revision must be a full lowercase 40-character Git SHA")
if payload.get("seed") not in {42, 52, 62}:
    raise SystemExit("C2b seed must be one of the preregistered seeds: 42, 52, 62")
if payload.get("input_mode") not in {"text", "context", "action"}:
    raise SystemExit("config input_mode must be text, context, or action")
print(f"base_config_passed seed={payload['seed']} input_mode={payload['input_mode']}")
'@
& $IntentFencePython -c $ConfigCheck $ResolvedConfigPath
if ($LASTEXITCODE -ne 0) {
    throw "C2b config preflight failed."
}

& $IntentFencePython -c "import torch, transformers; print(f'torch={torch.__version__}; transformers={transformers.__version__}')"
if ($LASTEXITCODE -ne 0) {
    throw "C2b dependency preflight failed in: $IntentFencePython"
}

$CudaOutput = @(& $IntentFencePython -c "import torch; print(f'cuda_available={torch.cuda.is_available()}; device_count={torch.cuda.device_count()}')")
if ($LASTEXITCODE -ne 0) {
    throw "Unable to inspect CUDA availability."
}
$CudaOutput | ForEach-Object { Write-Host $_ }
if ($RequireCuda -and ($CudaOutput -notmatch "cuda_available=True")) {
    throw "C2b full run requires CUDA; pass only -PreflightOnly on a CPU host."
}

& $IntentFencePython -m intentfence.train `
    --config $ResolvedConfigPath `
    --train $ResolvedTrainPath `
    --validation $ResolvedValidationPath `
    --dry-run
if ($LASTEXITCODE -ne 0) {
    throw "C2b data preflight failed."
}

if ($PreflightOnly) {
    Write-Host "C2b Base preflight passed; training was not started."
    exit 0
}

if (-not $RequireCuda) {
    throw "A non-preflight C2b Base run must pass -RequireCuda."
}
if ($CostCny -lt 0) {
    throw "A non-preflight run must provide the actual cost with -CostCny, using 0 for free execution."
}
$ResolvedAuthorizationFile = Resolve-RepositoryPath $AuthorizationFile $RepositoryRoot
if (-not (Test-Path -LiteralPath $ResolvedAuthorizationFile -PathType Leaf)) {
    throw "Training authorization file is missing: $ResolvedAuthorizationFile"
}
$Authorization = Get-Content -Raw -LiteralPath $ResolvedAuthorizationFile | ConvertFrom-Json
if ($Authorization.candidate_id -ne $ExpectedCandidate) {
    throw "Training authorization candidate_id does not match ExpectedCandidate."
}
if ($Authorization.human_verified -ne $true) {
    throw "Training authorization requires human_verified=true."
}
if ($Authorization.formal_training_authorized -ne $true) {
    throw "Training authorization requires formal_training_authorized=true."
}
if (-not [string]$Authorization.approved_by_project_owner) {
    throw "Training authorization requires approved_by_project_owner."
}
try {
    $ApprovedAt = [string]$Authorization.approved_at
    if ($ApprovedAt -notmatch "(?:Z|[+-]\d{2}:\d{2})$") {
        throw "timestamp has no explicit timezone offset"
    }
    [DateTimeOffset]::Parse($ApprovedAt) | Out-Null
} catch {
    throw "Training authorization approved_at must be a timezone-aware ISO-8601 timestamp."
}
if (Test-Path -LiteralPath $ResolvedOutputDirectory) {
    throw "Refusing to overwrite existing output directory: $ResolvedOutputDirectory"
}

$StartedAt = (Get-Date).ToUniversalTime()
$Stopwatch = [System.Diagnostics.Stopwatch]::StartNew()
& $IntentFencePython -m intentfence.train `
    --config $ResolvedConfigPath `
    --train $ResolvedTrainPath `
    --validation $ResolvedValidationPath `
    --output-dir $ResolvedOutputDirectory
if ($LASTEXITCODE -ne 0) {
    throw "C2b Base training failed; no automatic retry is performed."
}

& $IntentFencePython (Join-Path $RepositoryRoot "scripts/verify_checkpoint.py") `
    --model-dir (Join-Path $ResolvedOutputDirectory "best")
if ($LASTEXITCODE -ne 0) {
    throw "C2b Base checkpoint reload verification failed."
}

$Stopwatch.Stop()
$EndedAt = (Get-Date).ToUniversalTime()
& $IntentFencePython (Join-Path $RepositoryRoot "scripts/write_run_manifest.py") `
    --repository-root $RepositoryRoot `
    --config $ResolvedConfigPath `
    --train $ResolvedTrainPath `
    --validation $ResolvedValidationPath `
    --checkpoint-dir (Join-Path $ResolvedOutputDirectory "best") `
    --output (Join-Path $ResolvedOutputDirectory "run_manifest.json") `
    --started-at $StartedAt.ToString("o") `
    --ended-at $EndedAt.ToString("o") `
    --duration-seconds $Stopwatch.Elapsed.TotalSeconds `
    --cost-usd 0 `
    --cost-cny $CostCny `
    --stage "c2b_base" `
    --authorization-file $ResolvedAuthorizationFile
if ($LASTEXITCODE -ne 0) {
    throw "C2b run manifest generation failed."
}

Write-Host "C2b Base completed. Stop and provide the complete run manifest and logs before another variant or seed."
