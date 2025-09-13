#!/usr/bin/env bash
set -euo pipefail

# Ensure env is loaded
if [ ! -f .env ]; then
  echo "No .env found. Run: scripts/bootstrap_env.sh && set -a; source .env; set +a"
  exit 1
fi
set -a; source .env; set +a

# Python venv
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip boto3

# 1) Provision EC2 (Ubuntu 22.04) – 5× micro, 4× large
python scripts/provision_instances.py

# 2) Deploy FastAPI app to each instance and start uvicorn
python scripts/deploy_fastapi.py

# 3) Create (or reuse) ALB + two target groups + path rules /cluster1 and /cluster2
python scripts/create_alb.py

echo "All done. See artifacts/instances.json and artifacts/alb.json."
