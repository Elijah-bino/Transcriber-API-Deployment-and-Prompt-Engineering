#!/usr/bin/env bash
# Bootstrap + launch the eval on a VM, detached. Safe to re-run (resumes).
#
#   bash setup_and_run.sh                 # full run, all models, 225 rows
#   bash setup_and_run.sh --preflight-only
#   bash setup_and_run.sh --limit 10      # smoke test
#
set -euo pipefail
cd "$(dirname "$0")"
EVAL_DIR="$(pwd)"
PE_DIR="$(cd .. && pwd)"

if [ ! -f "$PE_DIR/.env" ]; then
  echo "ERROR: $PE_DIR/.env not found (needs NVIDIA_API_KEY, GROQ_API_KEY)" >&2
  exit 1
fi

PY="$(command -v python3 || command -v python)"
if [ ! -d .venv ]; then
  echo "creating venv..."
  "$PY" -m venv .venv
fi
./.venv/bin/pip -q install --upgrade pip >/dev/null
./.venv/bin/pip -q install requests >/dev/null   # not strictly needed (stdlib http), kept for convenience

mkdir -p "$PE_DIR/results"

if [ ! -f "$PE_DIR/data/eval_set_225.csv" ]; then
  ./.venv/bin/python build_dataset.py
fi

LOG="$PE_DIR/results/run_$(date +%Y%m%d_%H%M%S).log"
ln -sf "$(basename "$LOG")" "$PE_DIR/results/run.log" 2>/dev/null || true

echo "launching eval (detached), log: $LOG"
nohup ./.venv/bin/python run_eval.py \
  --models models.txt \
  --data "$PE_DIR/data/eval_set_225.csv" \
  --prompt "$PE_DIR/prompts/v1.txt" \
  --out "$PE_DIR/results" \
  --rpm 40 \
  "$@" \
  > "$LOG" 2>&1 &

PID=$!
echo "$PID" > "$PE_DIR/results/run.pid"
echo
echo "  PID $PID"
echo "  follow:  tail -f $LOG"
echo "  stop:    kill $PID"
echo "  resume:  bash setup_and_run.sh   (just re-run; it continues)"
