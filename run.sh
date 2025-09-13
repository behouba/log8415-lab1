#!/usr/bin/env bash
set -euo pipefail

python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip boto3

python scripts/provision_instances.py
python scripts/deploy_fastapi.py
python scripts/create_alb.py

