#!/usr/bin/env bash
# Local Ollama pass: one model at a time -> pull, eval 225 rows, remove, next.
# Harness saves per-model raw/scored/mismatches under results/local/.
# Stdlib only -- no venv needed. Run detached:
#   nohup bash run_local_pass.sh > /dev/null 2>&1 &
set -u
cd "$(dirname "$0")"
PE="$(cd .. && pwd)"
OUT="$PE/results/local"
PROMPT="$PE/prompts/v2.txt"
DATA="$PE/data/eval_set_225.csv"
mkdir -p "$OUT"
LOG="$OUT/pass.log"
PY="$(command -v python3 || command -v python)"

# smallest / fastest first. done models (225-row raw already on disk) are skipped.
# qwen3:8b dropped -- won't fit 4GB VRAM / 7GB RAM cleanly and we have 1.7b+4b.
MODELS=(qwen3:1.7b qwen3:4b phi4-mini llama3.2:3b gemma3:4b granite3.1-moe:3b)

{
echo "=== local pass start $(date) ==="
"$PY" --version; ollama --version
for m in "${MODELS[@]}"; do
  echo
  echo "########## $m  $(date) ##########"
  if ! ollama pull "$m" 2>&1 | tail -2; then
    echo "PULL FAILED: $m"; continue
  fi
  printf 'ollama,%s\n' "$m" > /tmp/one_model.txt
  "$PY" run_eval.py --models /tmp/one_model.txt --data "$DATA" \
      --prompt "$PROMPT" --out "$OUT" --rpm 600 || echo "RUN FAILED: $m"
  ollama rm "$m" 2>&1 || true
  echo "removed $m | disk: $(df -h / | awk 'NR==2{print $4" free"}')"
done
echo
echo "=== ALL DONE $(date) ==="
"$PY" score.py --data "$DATA" --out "$OUT"
} 2>&1 | tee -a "$LOG"
