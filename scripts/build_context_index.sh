#!/usr/bin/env bash
# ==============================================================================
# BUILD THE RAG CONTEXT INDEX FOR EVERY SERVED PACKAGE
# ==============================================================================
#
# CI, not the image build, is where the index should be produced: the MotherDuck
# token is a Secret Manager asset, the index is data and not code, and building
# it here keeps `docker build` reproducible.  The image build re-runs the same
# pipeline idempotently (see Dockerfile), so either path ends in the same state.
#
# What this does, in order:
#   1. preflight  resolve MOTHERDUCK_TOKEN (environment first, then Secret
#                 Manager) and fail in seconds with the exact gcloud command if
#                 that is impossible - not four minutes later as a Malloy
#                 "Error(s) compiling model" line
#   2. npm ci     install the Malloy compiler that Stage 1 shells out to
#   3. pipeline   Stage 1 -> 2 -> 3 for every package in publisher.config.json,
#                 then ingest the graphs into Chroma.  Never --fresh: --fresh
#                 would regenerate the curated domain contexts
#   4. verify     verify_index_coverage.py --require ... - the index that ships
#                 must expose the money measures, or the deploy stops here
#
# Usage:
#   scripts/build_context_index.sh
#   scripts/build_context_index.sh --skip-npm
#   scripts/build_context_index.sh --config workspace/publisher.config.json \
#       --require jaffle_shop:Total_Revenue
#
# Environment:
#   MOTHERDUCK_TOKEN  if unset, read from Secret Manager (needs secretAccessor)
#   PROJECT_ID        project holding the secret (default: gcloud config)
#   SECRET_NAME       default motherduck-token
#   PYTHON            interpreter for the pipeline (default python3); a venv is
#                     created at context/.venv-index when its deps are missing
# ==============================================================================
set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${REPO_ROOT}"

CONFIG="workspace/publisher.config.json"
SECRET_NAME="${SECRET_NAME:-motherduck-token}"
PROJECT_ID="${PROJECT_ID:-}"
PYTHON="${PYTHON:-python3}"
REQUIREMENTS="context/orchestration/requirements.txt"
VENV_DIR="context/.venv-index"
REQUIRES=("jaffle_shop:Total_Revenue" "jaffle_shop:Gross_Margin")
SKIP_NPM=0

log() { printf '[index] %s\n' "$*"; }
die() { printf '[error] %s\n' "$*" >&2; exit 1; }

usage() {
  sed -n '2,32p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
}

while [ $# -gt 0 ]; do
  case "$1" in
    --config)   CONFIG="${2:?--config needs a path}"; shift 2 ;;
    --require)  REQUIRES+=("${2:?--require needs PKG:MEASURE}"); shift 2 ;;
    --python)   PYTHON="${2:?--python needs an interpreter}"; shift 2 ;;
    --skip-npm) SKIP_NPM=1; shift ;;
    -h|--help)  usage; exit 0 ;;
    *)          die "unknown argument '$1' (try --help)" ;;
  esac
done

[ -f "${CONFIG}" ] || die "config not found: ${CONFIG}"
[ -f "${REQUIREMENTS}" ] || die "requirements not found: ${REQUIREMENTS}"

# ------------------------------------------------------------------------------
# 1. Token preflight
# ------------------------------------------------------------------------------
resolve_token() {
  if [ -n "${MOTHERDUCK_TOKEN:-}" ]; then
    log "using MOTHERDUCK_TOKEN from the environment"
    return 0
  fi

  command -v gcloud >/dev/null 2>&1 \
    || die "MOTHERDUCK_TOKEN is not set and gcloud is unavailable; export MOTHERDUCK_TOKEN"

  [ -n "${PROJECT_ID}" ] || PROJECT_ID="$(gcloud config get-value project 2>/dev/null || true)"
  if [ -z "${PROJECT_ID}" ] || [ "${PROJECT_ID}" = "(unset)" ]; then
    die "no project: set PROJECT_ID or export MOTHERDUCK_TOKEN"
  fi

  local identity err_file token
  identity="$(gcloud auth list --filter=status:ACTIVE --format='value(account)' 2>/dev/null | head -1)"
  err_file="$(mktemp)"
  log "MOTHERDUCK_TOKEN not set; reading '${SECRET_NAME}' from Secret Manager (as ${identity:-unknown identity})"

  if ! token="$(gcloud secrets versions access latest \
        --secret="${SECRET_NAME}" --project="${PROJECT_ID}" 2>"${err_file}")"; then
    printf '[error] cannot read secret %s as %s\n' \
      "${SECRET_NAME}" "${identity:-unknown identity}" >&2
    printf '[error]   %s\n' "$(tail -1 "${err_file}")" >&2
    rm -f "${err_file}"
    cat >&2 <<EOF
[error] Grant the deploy identity read access once, then re-run:
[error]   gcloud secrets add-iam-policy-binding ${SECRET_NAME} \\
[error]     --project ${PROJECT_ID} \\
[error]     --member serviceAccount:${identity:-<deploy-sa>@<project>.iam.gserviceaccount.com} \\
[error]     --role roles/secretmanager.secretAccessor
[error] A local run can also just export MOTHERDUCK_TOKEN=...
EOF
    exit 1
  fi
  rm -f "${err_file}"

  [ -n "${token}" ] || die "Secret Manager returned an empty value for '${SECRET_NAME}'"
  export MOTHERDUCK_TOKEN="${token}"
  log "token resolved from Secret Manager"
}

# ------------------------------------------------------------------------------
# 2. Node dependencies for the Malloy AST compiler (Stage 1)
# ------------------------------------------------------------------------------
install_node_deps() {
  if [ "${SKIP_NPM}" = "1" ]; then
    log "--skip-npm: reusing the existing context/node_modules"
    return 0
  fi
  command -v npm >/dev/null 2>&1 || die "npm is required for Stage 1 (or pass --skip-npm)"
  log "installing the Stage-1 compiler deps (npm ci --omit=dev in context/)"
  ( cd context && npm ci --omit=dev --no-audit --no-fund >/dev/null ) \
    || die "npm ci failed in context/ (see context/package-lock.json)"
}

# ------------------------------------------------------------------------------
# 3. Interpreter: the pipeline imports Stage 3 unconditionally, so the four
#    service deps must be importable even for a Stage-1/2-only run.
# ------------------------------------------------------------------------------
_pipeline_importable() {
  "${PYTHON}" -c 'import chromadb, fastapi, uvicorn, httpx' >/dev/null 2>&1
}

resolve_python() {
  if _pipeline_importable; then
    log "pipeline deps present in ${PYTHON}"
    return 0
  fi
  if [ ! -x "${VENV_DIR}/bin/python" ]; then
    log "creating ${VENV_DIR} for ${REQUIREMENTS}"
    "${PYTHON}" -m venv "${VENV_DIR}" || die "could not create ${VENV_DIR}"
  fi
  PYTHON="${VENV_DIR}/bin/python"
  if ! _pipeline_importable; then
    log "installing ${REQUIREMENTS} into ${VENV_DIR}"
    "${PYTHON}" -m pip install -q --disable-pip-version-check -r "${REQUIREMENTS}" \
      || die "pip install -r ${REQUIREMENTS} failed"
  fi
  log "pipeline deps present in ${PYTHON}"
}

resolve_token
install_node_deps
resolve_python

export PYTHONPATH="${REPO_ROOT}/context:${REPO_ROOT}/context/shared${PYTHONPATH:+:${PYTHONPATH}}"

# ------------------------------------------------------------------------------
# 4. Rebuild the graphs and the vectors.  No --fresh: that would throw away the
#    curated domain contexts that decide which explore answers a question.
# ------------------------------------------------------------------------------
log "running the pipeline for every package in ${CONFIG} (no --fresh)"
"${PYTHON}" context/orchestration/run_context_pipeline.py \
  --all --index-chroma --config "${CONFIG}" \
  || die "run_context_pipeline.py failed - no image should be built from this tree"

# ------------------------------------------------------------------------------
# 5. Prove the index can answer for money, not just for schema.
# ------------------------------------------------------------------------------
VERIFY_ARGS=(--config "${CONFIG}")
for spec in "${REQUIRES[@]}"; do
  VERIFY_ARGS+=(--require "${spec}")
  log "requiring measure ${spec}"
done

log "verifying index coverage"
"${PYTHON}" context/orchestration/verify_index_coverage.py "${VERIFY_ARGS[@]}" \
  || die "index coverage regressed - refusing to continue (see the failed lines above)"

SERVED="$("${PYTHON}" - <<PY
import sys
sys.path[:0] = ['context', 'context/shared']
from _context_common import iter_packages
print(len(iter_packages(config_path='${CONFIG}')))
PY
)"

log "index coverage ${SERVED}/${SERVED} - every served package has a RAG context"
