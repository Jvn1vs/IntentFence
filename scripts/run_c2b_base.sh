#!/usr/bin/env bash
set -Eeuo pipefail

# C2b Base owner-run entrypoint for Linux GPU hosts.
# This mirrors scripts/run_c2b_base.ps1 and deliberately keeps training owner-executed.

usage() {
    cat <<'EOF'
Usage:
  scripts/run_c2b_base.sh \
    --config-path <path> \
    --train-path <path> \
    --validation-path <path> \
    --output-directory <path> \
    [options]

Options:
  --authorization-file <path>
  --expected-candidate <id>
  --candidate-manifest-path <path>
  --readiness-report-path <path>
  --protocol-lock-path <path>
  --policy-path <path>
  --protocol-document-path <path>
  --integrity-report-path <path>
  --audit-analysis-path <path>
  --audit-manifest-path <path>
  --public-report-path <path>
  --ai-review-manifest-path <path>
  --integrity-policy-path <path>
  --ai-review-policy-path <path>
  --cost-cny <number>       Actual non-negative CNY cost for a training run.
  --log-file <path>         Console log path; defaults to <output-directory>.log.
  --require-cuda            Required for a non-preflight run.
  --preflight-only          Do not load a model or start training.
  --conda-executable <path> Full conda executable path or command name.
  --help
EOF
}

die() {
    echo "ERROR: $*" >&2
    exit 1
}

require_value() {
    [[ $# -ge 2 && -n "$2" ]] || die "$1 requires a value"
}

resolve_path() {
    local value="$1"
    if [[ "$value" == /* ]]; then
        printf '%s\n' "$value"
    else
        printf '%s/%s\n' "$REPOSITORY_ROOT" "$value"
    fi
}

require_file() {
    [[ -f "$1" ]] || die "Required file does not exist: $1"
}

CONFIG_PATH=""
TRAIN_PATH=""
VALIDATION_PATH=""
OUTPUT_DIRECTORY=""
AUTHORIZATION_FILE="data/interim/route_b_v2_candidate_8/training_authorization.json"
EXPECTED_CANDIDATE="route_b_v2_candidate_8"
CANDIDATE_MANIFEST_PATH="data/interim/route_b_v2_candidate_8/manifest.json"
READINESS_REPORT_PATH="data/interim/route_b_v2_candidate_8/readiness.json"
PROTOCOL_LOCK_PATH="configs/route_b_protocol_lock.json"
POLICY_PATH="configs/route_b_data_protocol.yaml"
PROTOCOL_DOCUMENT_PATH="docs/route_b_data_protocol.md"
INTEGRITY_REPORT_PATH="data/interim/route_b_v2_candidate_8/integrity_v2_data_protocol.json"
AUDIT_ANALYSIS_PATH="data/interim/route_b_v2_candidate_8_human_audit_v2/audit_analysis.json"
AUDIT_MANIFEST_PATH="data/interim/route_b_v2_candidate_8_human_audit_v2/audit_manifest.json"
PUBLIC_REPORT_PATH="reports/data_quality/route_b_candidate_8_card.md"
AI_REVIEW_MANIFEST_PATH=""
INTEGRITY_POLICY_PATH=""
AI_REVIEW_POLICY_PATH=""
COST_CNY="-1"
LOG_FILE=""
REQUIRE_CUDA=0
PREFLIGHT_ONLY=0
CONDA_EXECUTABLE="${CONDA_EXE:-}"

SCRIPT_DIRECTORY="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPOSITORY_ROOT="$(cd -- "$SCRIPT_DIRECTORY/.." && pwd)"

while [[ $# -gt 0 ]]; do
    case "$1" in
        --config-path)
            require_value "$@"
            CONFIG_PATH="$2"
            shift 2
            ;;
        --train-path)
            require_value "$@"
            TRAIN_PATH="$2"
            shift 2
            ;;
        --validation-path)
            require_value "$@"
            VALIDATION_PATH="$2"
            shift 2
            ;;
        --output-directory)
            require_value "$@"
            OUTPUT_DIRECTORY="$2"
            shift 2
            ;;
        --authorization-file)
            require_value "$@"
            AUTHORIZATION_FILE="$2"
            shift 2
            ;;
        --expected-candidate)
            require_value "$@"
            EXPECTED_CANDIDATE="$2"
            shift 2
            ;;
        --candidate-manifest-path)
            require_value "$@"
            CANDIDATE_MANIFEST_PATH="$2"
            shift 2
            ;;
        --readiness-report-path)
            require_value "$@"
            READINESS_REPORT_PATH="$2"
            shift 2
            ;;
        --protocol-lock-path)
            require_value "$@"
            PROTOCOL_LOCK_PATH="$2"
            shift 2
            ;;
        --policy-path)
            require_value "$@"
            POLICY_PATH="$2"
            shift 2
            ;;
        --protocol-document-path)
            require_value "$@"
            PROTOCOL_DOCUMENT_PATH="$2"
            shift 2
            ;;
        --integrity-report-path)
            require_value "$@"
            INTEGRITY_REPORT_PATH="$2"
            shift 2
            ;;
        --audit-analysis-path)
            require_value "$@"
            AUDIT_ANALYSIS_PATH="$2"
            shift 2
            ;;
        --audit-manifest-path)
            require_value "$@"
            AUDIT_MANIFEST_PATH="$2"
            shift 2
            ;;
        --public-report-path)
            require_value "$@"
            PUBLIC_REPORT_PATH="$2"
            shift 2
            ;;
        --ai-review-manifest-path)
            require_value "$@"
            AI_REVIEW_MANIFEST_PATH="$2"
            shift 2
            ;;
        --integrity-policy-path)
            require_value "$@"
            INTEGRITY_POLICY_PATH="$2"
            shift 2
            ;;
        --ai-review-policy-path)
            require_value "$@"
            AI_REVIEW_POLICY_PATH="$2"
            shift 2
            ;;
        --cost-cny)
            require_value "$@"
            COST_CNY="$2"
            shift 2
            ;;
        --log-file)
            require_value "$@"
            LOG_FILE="$2"
            shift 2
            ;;
        --require-cuda)
            REQUIRE_CUDA=1
            shift
            ;;
        --preflight-only)
            PREFLIGHT_ONLY=1
            shift
            ;;
        --conda-executable)
            require_value "$@"
            CONDA_EXECUTABLE="$2"
            shift 2
            ;;
        --help|-h)
            usage
            exit 0
            ;;
        *)
            die "Unknown argument: $1"
            ;;
    esac
done

[[ -n "$CONFIG_PATH" ]] || die "--config-path is required"
[[ -n "$TRAIN_PATH" ]] || die "--train-path is required"
[[ -n "$VALIDATION_PATH" ]] || die "--validation-path is required"
[[ -n "$OUTPUT_DIRECTORY" ]] || die "--output-directory is required"
[[ "$EXPECTED_CANDIDATE" == "route_b_v2_candidate_8" ]] || die "This C2b entrypoint only supports route_b_v2_candidate_8."
[[ "$COST_CNY" =~ ^-?[0-9]+([.][0-9]+)?$ ]] || die "Cost CNY must be a number."
(( $(awk -v value="$COST_CNY" 'BEGIN { print (value >= -1) ? 1 : 0 }') == 1 )) || die "Cost CNY must be -1 for preflight or non-negative for a training run."

RESOLVED_CONFIG_PATH="$(resolve_path "$CONFIG_PATH")"
CANDIDATE_TRAIN_PATH="$(resolve_path "$TRAIN_PATH")"
CANDIDATE_VALIDATION_PATH="$(resolve_path "$VALIDATION_PATH")"
RESOLVED_OUTPUT_DIRECTORY="$(resolve_path "$OUTPUT_DIRECTORY")"

if [[ -n "$LOG_FILE" ]]; then
    RESOLVED_LOG_FILE="$(resolve_path "$LOG_FILE")"
else
    RESOLVED_LOG_FILE="${RESOLVED_OUTPUT_DIRECTORY}.log"
fi
LOG_PARENT_DIRECTORY="$(dirname -- "$RESOLVED_LOG_FILE")"
mkdir -p "$LOG_PARENT_DIRECTORY"
[[ ! -e "$RESOLVED_LOG_FILE" ]] || die "Refusing to overwrite existing log file: $RESOLVED_LOG_FILE"
exec > >(tee "$RESOLVED_LOG_FILE") 2>&1
export PYTHONUNBUFFERED=1

require_file "$RESOLVED_CONFIG_PATH"
require_file "$CANDIDATE_TRAIN_PATH"
require_file "$CANDIDATE_VALIDATION_PATH"

if [[ -z "$CONDA_EXECUTABLE" ]]; then
    CONDA_EXECUTABLE="conda"
fi
if [[ "$CONDA_EXECUTABLE" == */* ]]; then
    [[ -x "$CONDA_EXECUTABLE" ]] || die "Conda executable is not executable: $CONDA_EXECUTABLE"
    RESOLVED_CONDA_EXECUTABLE="$(readlink -f "$CONDA_EXECUTABLE" 2>/dev/null || printf '%s' "$CONDA_EXECUTABLE")"
else
    RESOLVED_CONDA_EXECUTABLE="$(command -v "$CONDA_EXECUTABLE" || true)"
    [[ -n "$RESOLVED_CONDA_EXECUTABLE" ]] || die "Unable to resolve conda. Pass --conda-executable with the full path."
fi

echo "Using Conda: $RESOLVED_CONDA_EXECUTABLE"
INTENTFENCE_PYTHON="$($RESOLVED_CONDA_EXECUTABLE run -n intentfence python -c 'import sys; print(sys.executable)' | awk 'NF { last=$0 } END { print last }')"
[[ -n "$INTENTFENCE_PYTHON" && -f "$INTENTFENCE_PYTHON" ]] || die "Unable to resolve the intentfence Conda Python."
echo "Using intentfence Python: $INTENTFENCE_PYTHON"
echo "Config: $RESOLVED_CONFIG_PATH"
echo "Train: $CANDIDATE_TRAIN_PATH"
echo "Validation: $CANDIDATE_VALIDATION_PATH"
echo "Output: $RESOLVED_OUTPUT_DIRECTORY"
echo "Log: $RESOLVED_LOG_FILE"

"$INTENTFENCE_PYTHON" "$REPOSITORY_ROOT/scripts/validate_c2b_config.py" \
    --config "$RESOLVED_CONFIG_PATH" || die "C2b config preflight failed."
"$INTENTFENCE_PYTHON" "$REPOSITORY_ROOT/scripts/validate_c2b_preflight.py" \
    --expected-candidate "$EXPECTED_CANDIDATE" \
    --candidate-manifest "$(resolve_path "$CANDIDATE_MANIFEST_PATH")" \
    --train-path "$CANDIDATE_TRAIN_PATH" \
    --validation-path "$CANDIDATE_VALIDATION_PATH" || die "C2b candidate preflight is not bound to the expected manifest."
"$INTENTFENCE_PYTHON" -c 'import torch, transformers; print(f"torch={torch.__version__}; transformers={transformers.__version__}")' \
    || die "C2b dependency preflight failed in: $INTENTFENCE_PYTHON"
CUDA_OUTPUT="$($INTENTFENCE_PYTHON -c 'import torch; print(f"cuda_available={torch.cuda.is_available()}; device_count={torch.cuda.device_count()}")')"
echo "$CUDA_OUTPUT"
if (( REQUIRE_CUDA == 1 )) && [[ "$CUDA_OUTPUT" != *"cuda_available=True"* ]]; then
    die "C2b full run requires CUDA; use --preflight-only on a CPU host."
fi

"$INTENTFENCE_PYTHON" -m intentfence.train \
    --config "$RESOLVED_CONFIG_PATH" \
    --train "$CANDIDATE_TRAIN_PATH" \
    --validation "$CANDIDATE_VALIDATION_PATH" \
    --dry-run || die "C2b data preflight failed."

if (( PREFLIGHT_ONLY == 1 )); then
    echo "C2b Base preflight passed; training was not started."
    exit 0
fi

(( REQUIRE_CUDA == 1 )) || die "A non-preflight C2b Base run must pass --require-cuda."
(( $(awk -v value="$COST_CNY" 'BEGIN { print (value >= 0) ? 1 : 0 }') == 1 )) || die "A non-preflight run must provide the actual cost with --cost-cny."
RESOLVED_AUTHORIZATION_FILE="$(resolve_path "$AUTHORIZATION_FILE")"
[[ ! -e "$RESOLVED_OUTPUT_DIRECTORY" ]] || die "Refusing to overwrite existing output directory: $RESOLVED_OUTPUT_DIRECTORY"

STARTED_AT="$(date -u +%Y-%m-%dT%H:%M:%S.%NZ)"
START_EPOCH="$(date +%s.%N)"
TRAINING_ARGUMENTS=(
    -m intentfence.train
    --config "$RESOLVED_CONFIG_PATH"
    --train "$CANDIDATE_TRAIN_PATH"
    --validation "$CANDIDATE_VALIDATION_PATH"
    --output-dir "$RESOLVED_OUTPUT_DIRECTORY"
    --c2b-authorization-file "$RESOLVED_AUTHORIZATION_FILE"
    --c2b-expected-candidate "$EXPECTED_CANDIDATE"
    --c2b-candidate-manifest "$(resolve_path "$CANDIDATE_MANIFEST_PATH")"
    --c2b-readiness-report "$(resolve_path "$READINESS_REPORT_PATH")"
    --c2b-protocol-lock "$(resolve_path "$PROTOCOL_LOCK_PATH")"
    --c2b-policy "$(resolve_path "$POLICY_PATH")"
    --c2b-protocol-document "$(resolve_path "$PROTOCOL_DOCUMENT_PATH")"
    --c2b-integrity-report "$(resolve_path "$INTEGRITY_REPORT_PATH")"
    --c2b-audit-analysis "$(resolve_path "$AUDIT_ANALYSIS_PATH")"
    --c2b-audit-manifest "$(resolve_path "$AUDIT_MANIFEST_PATH")"
    --c2b-public-report "$(resolve_path "$PUBLIC_REPORT_PATH")"
)
if [[ -n "$AI_REVIEW_MANIFEST_PATH" ]]; then
    TRAINING_ARGUMENTS+=(--c2b-ai-review-manifest "$(resolve_path "$AI_REVIEW_MANIFEST_PATH")")
fi
if [[ -n "$INTEGRITY_POLICY_PATH" ]]; then
    TRAINING_ARGUMENTS+=(--c2b-integrity-policy "$(resolve_path "$INTEGRITY_POLICY_PATH")")
fi
if [[ -n "$AI_REVIEW_POLICY_PATH" ]]; then
    TRAINING_ARGUMENTS+=(--c2b-ai-review-policy "$(resolve_path "$AI_REVIEW_POLICY_PATH")")
fi

"$INTENTFENCE_PYTHON" "${TRAINING_ARGUMENTS[@]}" || die "C2b Base training failed; no automatic retry is performed."
"$INTENTFENCE_PYTHON" "$REPOSITORY_ROOT/scripts/verify_checkpoint.py" \
    --model-dir "$RESOLVED_OUTPUT_DIRECTORY/best" || die "C2b Base checkpoint reload verification failed."

END_EPOCH="$(date +%s.%N)"
ENDED_AT="$(date -u +%Y-%m-%dT%H:%M:%S.%NZ)"
DURATION_SECONDS="$(awk -v start="$START_EPOCH" -v end="$END_EPOCH" 'BEGIN { printf "%.6f", end - start }')"
"$INTENTFENCE_PYTHON" "$REPOSITORY_ROOT/scripts/write_run_manifest.py" \
    --repository-root "$REPOSITORY_ROOT" \
    --config "$RESOLVED_CONFIG_PATH" \
    --train "$CANDIDATE_TRAIN_PATH" \
    --validation "$CANDIDATE_VALIDATION_PATH" \
    --checkpoint-dir "$RESOLVED_OUTPUT_DIRECTORY/best" \
    --output "$RESOLVED_OUTPUT_DIRECTORY/run_manifest.json" \
    --started-at "$STARTED_AT" \
    --ended-at "$ENDED_AT" \
    --duration-seconds "$DURATION_SECONDS" \
    --cost-usd 0 \
    --cost-cny "$COST_CNY" \
    --stage c2b_base \
    --authorization-file "$RESOLVED_AUTHORIZATION_FILE" || die "C2b run manifest generation failed."

echo "C2b Base completed. Stop and provide the complete run manifest and logs before another variant or seed."
