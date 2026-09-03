#!/usr/bin/env bash
# Bootstrap + launch the eval on a VM, detached. Safe to re-run (resumes).
#
#   bash setup_and_run.sh                          # prompt v1, results in results/
#   bash setup_and_run.sh --preflight-only
#   bash setup_and_run.sh --limit 10               # smoke test
#   PROMPT=v2 OUT=results/v2 bash setup_and_run.sh # prompt v2, separate output dir
#   MODELS=models_local.txt LLM_BASE=http://localhost:11434/v1 bash setup_and_run.sh
#
# PROMPT  = prompt file: a bare name (-> prompts/<name>.txt) or a path. default v1
# OUT     = results dir, relative to prompt-engineering/ or absolute. default results
# MODELS  = model list file in eval/. default models.txt
# RPM     = requests/min. default 40
set -euo pipefail
cd "$(dirname "$0")"
PE_DIR="$(cd .. && pwd)"

if [ ! -f "$PE_DIR/.env" ]; then
  echo "ERROR: $PE_DIR/.env not found (needs NVIDIA_API_KEY, GROQ_API_KEY)" >&2
  exit 1
fi

PROMPT="${PROMPT:-v1}"
case "$PROMPT" in
  */*|*.txt) PROMPT_FILE="$PROMPT" ;;
  *)         PROMPT_FILE="$PE_DIR/prompts/${PROMPT}.txt" ;;
esac
[ -f "$PROMPT_FILE" ] || { echo "ERROR: prompt not found: $PROMPT_FILE" >&2; exit 1; }

OUT="${OUT:-results}"
case "$OUT" in /*) OUT_DIR="$OUT" ;; *) OUT_DIR="$PE_DIR/$OUT" ;; esac

MODELS="${MODELS:-models.txt}"
RPM="${RPM:-40}"

PY="$(command -v python3 || command -v python)"
[ -d .venv ] || { echo "creating venv..."; "$PY" -m venv .venv; }
./.venv/bin/pip -q install --upgrade pip >/dev/null 2>&1 || true

mkdir -p "$OUT_DIR"
[ -f "$PE_DIR/data/eval_set_225.csv" ] || ./.venv/bin/python build_dataset.py

LOG="$OUT_DIR/run_$(date +%Y%m%d_%H%M%S).log"
ln -sf "$(basename "$LOG")" "$OUT_DIR/run.log" 2>/dev/null || true

echo "prompt: $PROMPT_FILE"
echo "models: $MODELS   out: $OUT_DIR   rpm: $RPM"
echo "launching eval (detached), log: $LOG"
nohup ./.venv/bin/python run_eval.py \
  --models "$MODELS" \
  --data "$PE_DIR/data/eval_set_225.csv" \
  --prompt "$PROMPT_FILE" \
  --out "$OUT_DIR" \
  --rpm "$RPM" \
  "$@" \
  > "$LOG" 2>&1 &

PID=$!
echo "$PID" > "$OUT_DIR/run.pid"
echo
echo "  PID $PID"
echo "  follow:  tail -f $LOG"
echo "  stop:    kill $PID"
echo "  resume:  re-run the same command (it continues from the last done row)"
