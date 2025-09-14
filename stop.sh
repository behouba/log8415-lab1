#!/usr/bin/env bash
set -euo pipefail
# One-button nuke using the tag-based Python teardown
python scripts/teardown.py --confirm --purge
