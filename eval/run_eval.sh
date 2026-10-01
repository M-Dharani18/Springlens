#!/bin/bash
set -e
cd /home/dharani/springlens/springlens/eval
source .venv/bin/activate

# Ensure GOOGLE_API_KEY is set in environment before running
if [ -z "$GOOGLE_API_KEY" ]; then
    echo "ERROR: GOOGLE_API_KEY environment variable is not set."
    exit 1
fi


python3 run_ragas_faithfulness.py
