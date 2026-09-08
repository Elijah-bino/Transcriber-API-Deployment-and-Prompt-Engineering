# Prompt Engineering & Evaluation

Selecting the prompt and open-weight model for the **rephrasing stage**: turn a raw
speech-to-text transcript into a short, de-identified, staff-facing action item.

```
"I've been waiting ages and I'm really thirsty, can someone bring me water?"  ─▶  "Water request"
"Hi I'm Daniel, I'm 72, could you bring me some water?"                        ─▶  "Water request"   (name + age stripped)
```

The transcription stage is separate — see [`../stt/`](../stt/). Full context:
[`../CLAUDE.md`](../CLAUDE.md).

---

## The problem, precisely

Output must be: **2–5 words · Title Case (first word only) · no punctuation · topic
first · ending in one of `{request, assistance, adjustment, question, update}` · no
patient name / age / location, even when the transcript states it.**

This is a narrow transformation, not open-ended reasoning — so a small model is
enough, and the whole exercise is prompt engineering, not fine-tuning.

`LABEL_CONVENTION.md` is the closed spec; `validate_labels.py` enforces it on the
datasets.

---

## What was done

### 1. Datasets (`data/`)

| file | rows | what it is |
|---|---|---|
| `AIDE_100_general_dataset.csv` | 100 | clean requests → label |
| `AIDE_100_personal_data_dataset.csv` | 100 | same requests **with a name/age/town injected**; the label strips all of it |
| `AIDE_200_row_LLM_evaluation_dataset.csv` | 200 | the two above, with a `dataset` split column |
| `AIDE_training_data_with_expected_shortened.csv` | 25 | messier, disfluent, run-on, ASR-style transcripts |
| **`eval_set_225.csv`** | **225** | the 200-row set + the 25 messy rows (`dataset=realistic_messy`) — **the harness scores against this** |

Rebuild the merged set with `eval/build_dataset.py`. (The `AIDE_` prefix is a legacy
codename; all data is synthetic.)

The `personal_data_injected` split is the point of the whole eval: it tests *does
the model strip PII while shortening*, not just *can it shorten*. Always scored
separately.

### 2. Prompt: v1 → v2 (`prompts/`)

**v1** stated the rules with four examples. Result: zero PII leaks, but low exact
match — models understood every request, they just didn't match the house
vocabulary (over-capitalising, "Phone request" vs "Phone retrieval assistance",
singular/plural, "Unclear request" on real-but-vague needs).

**v2 (locked)** adds: capitalise the first word only; an explicit
retrieval-vs-request rule; a tightened "Unclear request"; a ~65-label preferred
list; ~24 few-shot examples built directly from v1's failures, mixing clean and
PII-injected inputs.

v1 → v2 on a 50-row smoke test: exact **60% → 92%**, semantic **86% → 100%**.

### 3. Eval harness (`eval/`)

`run_eval.py` + `score.py`:

- **provider-agnostic** — OpenAI-compatible endpoints (NVIDIA NIM, Groq) plus an
  Ollama native path (`/api/chat`, `think:false`, JSON-schema constrained output so
  even small models can't leak chain-of-thought)
- one model at a time, **no cross-model failover** (isolation)
- rate-limited, **checkpointed per row** — kill and re-run to resume
- auto-scores at the end

**Metrics**, always split by `general` / `personal_data_injected` / `realistic_messy`:

| metric | meaning |
|---|---|
| **exact** | normalised output == expected, case-sensitive (catches format drift) |
| **semantic** | same category noun (or topic) + ≥ 50% content-word overlap after singularising |
| **pii_leak** | output has a digit, or a patient name/town from the transcript not in the label — **hard gate, any leak disqualifies a model** |

Other tools:
- `compare.py --out <results-dir>` → `comparison.csv` / `.txt`, one row per
  transcript, one column per model, `<MISS>` on non-exact cells
- `make_report.py` → `Prompt-Testing-Report.pdf`
- `models.txt` (cloud) / `models_local.txt` (Ollama) — the model lists
- `setup_and_run.sh` — bootstrap + detached run on a VM

### 4. Three runs

- **Run 1** — prompt v1, cloud (Groq), 225 rows. A score ceiling.
- **Run 2** — prompt v2, 50-row smoke. Confirmed v2 fixes the house-style gap.
- **Run 3** — prompt v2, **self-hosted Ollama, CPU, Q4** (the real deploy target).
  The deciding run.

---

## Result

**Run 3 — prompt v2, local Ollama, 225 rows:**

| model | params | licence | exact | semantic | gen | personal | messy | PII leak |
|---|---|---|---|---|---|---|---|---|
| **qwen3:4b** | 4B | Apache 2.0 | **83.6%** | **90.2%** | 88% | 94% | 84% | **0** |
| gemma3:4b | 4B | Gemma | 76.6% | 84.4% | 84% | — | — | **0** |
| llama3.2:3b | 3B | Llama | 74.2% | 85.8% | 83% | 90% | 80% | **0** |
| phi4-mini | 3.8B | MIT | 74.2% | 84.4% | 77% | 89% | 96% | **0** |
| qwen3:1.7b | 1.7B | Apache 2.0 | 70.7% | 89.8% | 87% | 91% | 96% | **0** |

**Every model: zero PII leaks** — v2's de-identification holds across the board.
The smaller models generalise ("Toast request" → "Food request") where `qwen3:4b`
keeps the specific item.

### DECISION — locked

**`qwen3:4b` + prompt `v2`.** 7 points clear on exact match, best on semantic,
Apache 2.0, runs on a small CPU VM behind the keyword fast-path.
**Fallback:** `qwen3:1.7b` if hardware can't keep `qwen3:4b` latency acceptable.

Details: [`FINDINGS.md`](FINDINGS.md) · [`Prompt-Testing-Report.pdf`](Prompt-Testing-Report.pdf)
· per-transcript outputs in [`comparison.csv`](comparison.csv)

---

## Running the harness

Local Ollama pass (the deciding one — no rate limits, real Q4 quant):

```bash
# on a box with Ollama:
ollama serve &
for m in qwen3:4b qwen3:1.7b phi4-mini llama3.2:3b gemma3:4b; do ollama pull "$m"; done

cd prompt-engineering/eval
python run_eval.py --models models_local.txt --data ../data/eval_set_225.csv \
                   --prompt ../prompts/v2.txt --out ../results --rpm 600
python compare.py --out ../results
python make_report.py
```

Cloud pass (needs `NVIDIA_API_KEY` / `GROQ_API_KEY` in `../.env`, gitignored):

```bash
python run_eval.py --models models.txt --data ../data/eval_set_225.csv \
                   --prompt ../prompts/v2.txt --out ../results --preflight-only
python run_eval.py --models models.txt --data ../data/eval_set_225.csv \
                   --prompt ../prompts/v2.txt --out ../results
```

Or, detached on a VM: `bash eval/setup_and_run.sh` (resumable — re-run to continue).
`results/` is gitignored.

Notes: Groq's Cloudflare 403s the default `python-urllib` User-Agent (the harness
sends a browser-like one). The free NIM catalog has EOL'd most small Apache/MIT
instruct models, which is why the deploy candidates are only testable via the local
Ollama pass.

---

## Status

- [x] datasets normalised + merged (225 rows), pass `validate_labels.py`
- [x] prompt v1 → v2 (v2 locked)
- [x] eval harness (NIM / Groq / Ollama, resumable, auto-scores)
- [x] Runs 1–3 complete — see `FINDINGS.md`
- [x] **DECISION: `qwen3:4b` + prompt `v2`**
- [ ] scaffold the rephrasing service (`service/` — Dockerfile, FastAPI, keyword fast-path, PII filter)
- [ ] load-test `/shorten` latency; pick VM size
- [ ] wire STT → rephrase → store

Deliverables: `FINDINGS.md`, `Prompt-Testing-Report.pdf`, `comparison.csv` / `.txt`.
