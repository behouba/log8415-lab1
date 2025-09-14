#!/usr/bin/env bash
set -euo pipefail


# Ensure env is loaded
if [ ! -f .env ]; then
  echo "No .env found."
  echo "Run: scripts/bootstrap_env.sh && set -a; source .env; set +a"
  exit 1
fi
set -a; source .env; set +a

# Python venv
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip boto3

# 4× micro (cluster2) + 4× large (cluster1)
python scripts/provision_instances.py

# Deploy FastAPI to all instances
python scripts/deploy_fastapi.py

# Provision & deploy the custom latency-based LB (Option 1)
python scripts/provision_lb.py
python scripts/deploy_lb.py

echo
echo "All done ✅"
echo "Instances: artifacts/instances.json"
echo "LB:        artifacts/lb.json"
LB=$(jq -r '.public_ip' artifacts/lb.json)
echo "Try:       curl -s http://$LB/cluster1 ; curl -s http://$LB/cluster2"
