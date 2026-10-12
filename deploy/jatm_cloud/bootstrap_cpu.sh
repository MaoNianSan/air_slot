#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../.."
python3.11 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install 'torch==2.11.0+cpu' --index-url https://download.pytorch.org/whl/cpu
.venv/bin/python -m pip install -r deploy/jatm_cloud/requirements.runtime.txt
.venv/bin/python -m exp.jatm_s34.runtime_provenance --output-root deploy/jatm_cloud/runtime_installed
# Deliberately does not launch the scheduler or an experiment.
