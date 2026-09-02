[CmdletBinding()]
param(
    [string]$PythonCommand = "python",
    [string]$AuditDir = "data\interim\route_b_v2_candidate_8_human_audit_v2",
    [string]$ConfigPath = "configs\route_b_data_protocol.yaml"
)

$ErrorActionPreference = "Stop"
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path

function Resolve-RepositoryPath {
    param([string]$Path)

    $candidate = if ([System.IO.Path]::IsPathRooted($Path)) {
        $Path
    } else {
        Join-Path $repoRoot $Path
    }
    return (Resolve-Path -LiteralPath $candidate -ErrorAction Stop).Path
}

$pythonInfo = Get-Command -Name $PythonCommand -ErrorAction Stop
$pythonPath = $pythonInfo.Source
if ([string]::IsNullOrWhiteSpace($pythonPath)) {
    $pythonPath = $pythonInfo.Path
}
if ([string]::IsNullOrWhiteSpace($pythonPath)) {
    throw "Could not resolve Python command '$PythonCommand'"
}

$auditPath = Resolve-RepositoryPath -Path $AuditDir
$configPath = Resolve-RepositoryPath -Path $ConfigPath
$analysisPath = Join-Path $auditPath "audit_analysis.json"
if (Test-Path -LiteralPath $analysisPath) {
    throw "Refusing to overwrite existing audit analysis: $analysisPath"
}

$progressArguments = @(
    (Join-Path $repoRoot "scripts\check_route_b_human_audit_progress.py"),
    "--audit-dir", $auditPath
)
$progressOutput = @(& $pythonPath @progressArguments 2>&1)
$progressExitCode = $LASTEXITCODE
$progressOutput | ForEach-Object { Write-Output $_ }
if ($progressExitCode -ne 0) {
    throw "Human audit progress gate is not ready; no audit analysis was generated"
}

$analysisArguments = @(
    (Join-Path $repoRoot "scripts\analyze_route_b_blind_audits.py"),
    "--reviewer-a-risk", (Join-Path $auditPath "reviewer_a_risk.csv"),
    "--reviewer-b-risk", (Join-Path $auditPath "reviewer_b_risk.csv"),
    "--reviewer-a-alignment", (Join-Path $auditPath "reviewer_a_alignment.csv"),
    "--reviewer-b-alignment", (Join-Path $auditPath "reviewer_b_alignment.csv"),
    "--sealed-seed-labels", (Join-Path $auditPath "sealed_seed_labels.json"),
    "--audit-manifest", (Join-Path $auditPath "audit_manifest.json"),
    "--config", $configPath,
    "--output", $analysisPath
)
& $pythonPath @analysisArguments
$analysisExitCode = $LASTEXITCODE
if ($analysisExitCode -ne 0) {
    throw "Candidate 8 deterministic audit analysis failed with exit code $analysisExitCode"
}
