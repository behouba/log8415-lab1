#!/usr/bin/env bash
set -euo pipefail

# Activate the virtual environment if it exists, so boto3 is found
if [ -f .venv/bin/activate ]; then
  source .venv/bin/activate
  echo "Virtual environment activated."
else
  echo "WARN: .venv not found. The teardown script might fail if boto3 is not globally installed."
fi

# One-button nuke using the tag-based Python teardown
python scripts/teardown.py --confirm --purge
