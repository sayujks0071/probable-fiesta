#!/bin/bash
# Wrapper to run healthcheck and alerts
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export PYTHONPATH="$REPO_ROOT"

echo "=== Running Monitor $(date) ==="
python3 "$REPO_ROOT/scripts/healthcheck.py"
EXIT_CODE=$?

if [ $EXIT_CODE -ne 0 ]; then
    echo "Healthcheck Failed!"
    # We could send an alert here too if needed, but healthcheck logs it.
fi

python3 "$REPO_ROOT/scripts/check_alerts.py"
