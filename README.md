# Transcriber API Deployment & Prompt Engineering

Two pieces of a voice → dashboard pipeline for hospital / aged-care wards:

```
patient speaks ─▶ [ Transcription API ] ─▶ raw transcript ─▶ [ Rephrasing ] ─▶ "Water request" ─▶ nurse dashboard
                    stt/  — BUILT, deployed                    prompt-engineering/ — model + prompt chosen,
                                                               service wrapper still to build
```

The two stages are deliberately **independent and swappable** — you can change the
STT provider or the rephrasing model without touching the other.

---

## Part 1 — Transcription API (`stt/`)

A FastAPI microservice wrapping **Google Cloud Speech-to-Text** (v2, `en-AU`).
Audio in, raw transcript out. Deployed on a GCP VM behind an API key.

- Source: [`stt/main.py`](stt/main.py)
- API contract, deployment, security: [`stt/README.md`](stt/README.md)
  and [`stt/STT-API-Documentation.pdf`](stt/STT-API-Documentation.pdf)
- Validates format / size (25 MB) / duration (5 min) before the Google call;
  concurrency-limited; leaks no internal errors; never logs transcript content.

**Status:** built and running. Open items: enable HTTPS, lock down SSH, resolve
US-region data residency. See `CLAUDE.md` §5.

---

## Part 2 — Prompt Engineering (`prompt-engineering/`)

Choosing the prompt and open-weight model that turn a raw transcript into a short,
**de-identified** action item (`"Water request"`, `"Bathroom assistance"`), plus the
evaluation harness that made the decision.

### The task

2–5 words, Title Case, no punctuation, ending in one of `{request, assistance,
adjustment, question, update}`, and **no patient name / age / location even when the
transcript states it**. A narrow transformation — a small model is enough.

### What was done

1. **Datasets** (`data/`) — 225 labelled transcripts: 100 clean, 100 with
   name/age/town injected (labels strip it), 25 messy/disfluent. Label format is a
   closed convention (`LABEL_CONVENTION.md`), enforced by `validate_labels.py`.
2. **Prompt v1 → v2** (`prompts/`) — v2 adds first-word-only capitalisation, a
   retrieval-vs-request rule, a preferred-label list, and ~24 few-shot examples
   built from v1's failures. v1 → v2 smoke: exact 60% → 92%.
3. **Eval harness** (`eval/`) — `run_eval.py` + `score.py`, provider-agnostic
   (NVIDIA NIM, Groq, local Ollama), one model at a time, checkpointed, auto-scored
   on three metrics (exact, semantic, **PII-leak rate** as a hard gate), split by
   dataset.
4. **Three runs** — cloud baseline (v1), a v2 smoke test, and the deciding run:
   five self-hosted models at production Q4 quantisation.

### Result

| model | params | licence | exact | semantic | PII leak |
|---|---|---|---|---|---|
| **qwen3:4b** | 4B | Apache 2.0 | **83.6%** | **90.2%** | **0** |
| gemma3:4b | 4B | Gemma | 76.6% | 84.4% | 0 |
| llama3.2:3b | 3B | Llama | 74.2% | 85.8% | 0 |
| phi4-mini | 3.8B | MIT | 74.2% | 84.4% | 0 |
| qwen3:1.7b | 1.7B | Apache 2.0 | 70.7% | 89.8% | 0 |

Every model: **zero PII leaks** on the name-injected split. **`qwen3:4b` + prompt
`v2` is locked** — 7 points clear on exact match, Apache 2.0, runs cheap.

- Full write-up: [`prompt-engineering/FINDINGS.md`](prompt-engineering/FINDINGS.md)
- Client-ready report: [`prompt-engineering/Prompt-Testing-Report.pdf`](prompt-engineering/Prompt-Testing-Report.pdf)
- Every model's output per transcript: [`prompt-engineering/comparison.csv`](prompt-engineering/comparison.csv)
- How to run the harness: [`prompt-engineering/README.md`](prompt-engineering/README.md)

### Deployment plan (decided, not yet built)

One Docker image (`FROM ollama/ollama`, `RUN ollama pull qwen3:4b` baked in, +
FastAPI), on a VM in `australia-southeast1`, two endpoints (`/transcribe`,
`/shorten`), prompt bundled in the image, keyword fast-path in front of the model.
Not Cloud Run. Details in `CLAUDE.md` §4.6.

---

## Repo layout

```
stt/                     Transcription API — FastAPI + Google Cloud STT (deployed)
prompt-engineering/
  data/                  225-row eval set + source datasets
  prompts/               v1.txt, v2.txt  (v2 locked)
  eval/                  run_eval.py, score.py, compare.py, make_report.py, ...
  FINDINGS.md            full results + deployment plan
  Prompt-Testing-Report.pdf
  comparison.csv/.txt    per-transcript output of every model
  LABEL_CONVENTION.md    the closed label format
CLAUDE.md                technical context for both parts
```

## Secrets

`.env`, `env_variables.txt`, service-account JSON, `*.pem`, `*.key`, and build
artefacts are gitignored. No credentials are committed (verified across full git
history). Identifiers in `CLAUDE.md` are redacted to `<PLACEHOLDER>`.

## Running things

```bash
# eval harness — see prompt-engineering/README.md for provider setup
cd prompt-engineering/eval
python run_eval.py --models models_local.txt --data ../data/eval_set_225.csv \
                   --prompt ../prompts/v2.txt --out ../results
python compare.py --out ../results          # per-transcript side-by-side
python make_report.py                       # regenerate the PDF
```
