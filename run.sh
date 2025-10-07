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
echo "Setting up Python virtual environment and installing dependencies..."
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip > /dev/null
pip install boto3 > /dev/null
pip install aiohttp > /dev/null
echo "✅ Dependencies installed."

# Provision application instances (4 micro, 4 large)
python scripts/provision_instances.py

# Deploy FastAPI application to all instances
python scripts/deploy_fastapi.py

# Provision and deploy the custom latency-based Load Balancer
python scripts/provision_lb.py
python scripts/deploy_lb.py

echo
echo "Everything is ready! ✅"
echo "--------------------------------------------------"
echo "Application Instances: artifacts/instances.json"
echo "Load Balancer:         artifacts/lb.json"
LB_IP=$(jq -r '.public_ip' artifacts/lb.json)
echo
echo "Test the Load Balancer:"
echo "curl -s http://$LB_IP/cluster1 ; echo"
echo "curl -s http://$LB_IP/cluster2 ; echo"
echo "--------------------------------------------------"
