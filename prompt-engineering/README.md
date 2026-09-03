# AIDE — Prompt Engineering & Eval

Workspace for the LLM rephrasing stage: transcript -> short de-identified action item.
STT stage is separate (`../stt/`). See `../claude.md` section 4.

## Layout

```
prompt-engineering/
  data/                 datasets (moved here 2026-09-03)
    AIDE_200_row_LLM_evaluation_dataset.csv   <- the scoring set
    AIDE_100_general_dataset.csv              general split (no PII in transcript)
    AIDE_100_personal_data_dataset.csv        name/age/town injected; labels strip it
    AIDE_training_data_with_expected_shortened.csv   25 rows, normalized
    training data PRE-AI.md                   raw source transcripts
  LABEL_CONVENTION.md   the closed label format all labels + outputs must follow
  validate_labels.py    checks every label file against the convention
  prompts/              versioned system prompts (v1, v2, ...)
  results/              eval output (gitignored)
  .env                  OPENROUTER_API_KEY (gitignored)
```

## Status

- [x] datasets normalized, all 4 files pass `validate_labels.py`
- [x] draft prompt v1 (`prompts/v1.txt`)
- [ ] eval harness
- [ ] baseline run: Kimi K2.5 (current live model)
- [ ] candidate runs: Qwen3 8B/4B, Gemma, Phi-4-mini, Ministral (via Ollama on GCP VM)

## OpenRouter key

Free tier, $0 balance. Only `:free` models work, ~50 requests/day, ~20/min.
A 200-row eval = 200 requests, so it will not complete on free tier in one day,
and Kimi K2.5 is a paid model (needs credits). Load ~$10 of credits to unblock:
that also raises the free-model cap to 1000/day. Full Kimi eval run costs ~$0.05.
