# AIDE — Prompt Engineering & Eval

Workspace for the LLM rephrasing stage: transcript -> short de-identified action item.
STT stage is separate (`../stt/`). See `../claude.md` section 4.

## Layout

```
prompt-engineering/
  data/
    eval_set_225.csv                         <- what the harness scores against
       = AIDE_200_row_LLM_evaluation_dataset.csv  (general 100 + personal_data_injected 100)
       + AIDE_training_data_with_expected_shortened.csv  (25, tagged realistic_messy)
    AIDE_100_*.csv, AIDE_200_*.csv            source datasets
    training data PRE-AI.md                   raw source transcripts
  prompts/
    v1.txt                                    current system prompt
  eval/
    build_dataset.py    rebuilds eval_set_225.csv from the sources
    run_eval.py         harness: dataset x prompt x model -> results/raw/*.csv  (resumable)
    score.py            results/raw/*.csv -> scored/, mismatches/, summary.csv + ranked table
    models.txt          cloud API models (NIM + Groq)
    models_local.txt    the local Ollama pass (the real small-model bake-off)
    setup_and_run.sh    VM bootstrap + detached launch
  LABEL_CONVENTION.md   closed label format all labels + outputs must follow
  validate_labels.py    checks the label files against the convention
  results/              gitignored
  .env                  NVIDIA_API_KEY, GROQ_API_KEY  (gitignored)
```

## Metrics (score.py)

| metric | meaning |
|---|---|
| exact | normalised output == expected, case-sensitive (catches over-capitalising) |
| semantic | same final category noun AND >=50% content-word overlap |
| pii_leak | output has a digit, or a patient name/town from the transcript not in the label. **hard gate** |

Reported split three ways: `general`, `personal_data_injected`, `realistic_messy`. Never blended.

## Run on the VM

```bash
cd ~/aide/prompt-engineering/eval
bash setup_and_run.sh --preflight-only     # check which models answer
bash setup_and_run.sh                       # full run, detached, ~30-60 min
tail -f ../results/run.log
```
Re-run `setup_and_run.sh` any time to resume (it skips completed rows).
Results: `../results/summary.csv` + per-model `../results/raw/*.csv`, `scored/`, `mismatches/`.

## Status

- [x] datasets normalized + merged (225 rows), all pass `validate_labels.py`
- [x] prompt v1 -> v2
- [x] eval harness (NIM / Groq / Ollama, resumable, rate limited, auto-scores)
- [x] Run 1 cloud (v1), Run 2 v2 smoke, Run 3 local Ollama (v2) -- see `FINDINGS.md`
- [x] **DECISION: qwen3:4b + prompt v2** (83.6% exact / 90.2% semantic / 0 PII leaks; beat all others by 7+ pts on exact)
- [x] local pass mostly done: qwen3:4b, qwen3:1.7b, phi4-mini, llama3.2:3b, gemma3:4b (granite still finishing) -- all 0 leaks
- [x] deployment decided: VM + FastAPI, one Docker image, 2 endpoints (see FINDINGS.md)
- [ ] OPEN: build machine (Cloud Build vs VM), VM size (CPU vs GPU)
- [ ] scaffold `service/`, load-test `/shorten` latency
- [ ] wire STT -> rephrase -> Redis

Deliverables: `FINDINGS.md`, `AIDE-Prompt-Testing-Report.pdf`,
`comparison.csv` / `.txt` (final: 5 local models on prompt v2, every response per transcript)

## API reality (2026-09)

Free NIM has EOL'd almost every small Apache/MIT instruct model. `models.txt` is
thin and large-skewed on purpose -- it gives a **ceiling** (what's the best possible
score) plus `gpt-oss-20b` as the one real cheap-ish Tier A candidate. The models we
would actually deploy (3-8B) are tested in the **local Ollama pass**, which also
gives the true Q4 quant numbers. Groq needs a browser-like `User-Agent` or its
Cloudflare returns 403 (handled in the harness).

Rotate the NVIDIA / Groq / OpenRouter keys after the eval work -- they have been
in plaintext.
