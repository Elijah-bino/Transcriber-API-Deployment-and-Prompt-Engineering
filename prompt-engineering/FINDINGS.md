# Rephrasing eval — findings

## Run 1 — prompt v1, cloud pass (2026-09-03)

225 rows (`eval_set_225.csv`), Groq-hosted models, `prompts/v1.txt`.
`gemma-4-31b` timed out in preflight and did not run.

| model | exact | semantic | gen | personal | messy | PII leak | p50 ms |
|---|---|---|---|---|---|---|---|
| qwen3.8-27b | 62.2% | 84.4% | 81% | 89% | 80% | **0** | 212 |
| gpt-oss-120b | 11.1% | 83.1% | 82% | 86% | 76% | **0** | 394 |
| gpt-oss-20b | 47.6% | 78.7% | 77% | 83% | 68% | **0** | 286 |

(semantic = lexical near-match after singularising; see `eval/score.py`)

### What it means

1. **Zero PII leaks, every model, including the personal-data split.** v1's
   de-identification instruction works. This is the hard gate — passed.
2. **Models comprehend the requests fine (~79-84% semantic).** The gap to exact
   match is almost entirely AIDE house-style, not misunderstanding:
   - over-capitalisation ("Water Request") — gpt-oss-120b does it constantly (11% exact)
   - "X retrieval assistance" vs the model's "X request" for out-of-reach items
   - singular vs plural ("Curtain" vs "Curtains"), spacing ("Check-in" vs "Check in")
   - over-specifying ("Sitting up assistance" vs "Sitting assistance")
   - "Unclear request" fired on real-but-vague needs ("I'm not feeling well")
   - synonyms ("Head pain" vs "Headache", "Shortness of breath" vs "Breathing difficulty")
3. **qwen3.8-27b is the batch leader** on every split and the fastest. Apache 2.0.
   But 27B — not cheap to self-host. It's a ceiling reference, not the deploy pick.

### Consequences

- This is a **specification** problem. A controlled-output design (model picks a
  `category` from a fixed enum + short `detail`, deterministic formatter builds the
  label) would erase most of the exact-match gap. Recommended for the pilot build.
- Immediate step: **prompt v2** (`prompts/v2.txt`) — explicit "capitalise first word
  only", the retrieval-vs-request rule, tightened "Unclear request", a
  prefer-these-labels list, ~24 few-shot examples covering the tricky mappings.
- The models that actually matter (3-8B, cheap) were **not testable** here — free
  NIM has EOL'd them. Next: the local Ollama pass (`eval/models_local.txt`).

## Run 2 — prompt v2

TODO.

## Run 3 — local Ollama pass (qwen3 4b/8b, phi4-mini, llama3.2 3b, gemma3 4b, granite3.1-moe 3b)

TODO.
