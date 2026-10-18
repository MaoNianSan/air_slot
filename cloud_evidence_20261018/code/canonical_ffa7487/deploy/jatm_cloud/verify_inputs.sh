#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../.."
: "${1:?Pass the uploaded DATA_TRANSFER_MANIFEST.json path}"
.venv/bin/python -m exp.jatm_s34.cloud_verify --root . --manifest "$1" --output deploy/jatm_cloud/TRANSFER_VERIFICATION.json
.venv/bin/python -m exp.jatm_s34.cloud_inputs --output deploy/jatm_cloud/ANNUAL_INPUT_GATE.json
