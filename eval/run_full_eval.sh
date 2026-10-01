#!/bin/bash
cd ~/springlens/springlens/eval
for i in {1..20}; do
  echo "=== Batch $i ==="
  python3 run_experiments.py --batch-size 10
  echo "=== Restarting Ollama, cooling down 20s ==="
  docker restart springlens-ollama
  sleep 20
done
