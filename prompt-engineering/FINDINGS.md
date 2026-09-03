# Rephrasing eval — findings

Task: raw STT transcript -> short, de-identified, staff-facing action item
(2-5 words, Title Case, closed category-noun set). Eval set: `eval_set_225.csv`
(100 general + 100 personal-data-injected + 25 realistic-messy). Metrics: exact
match, semantic near-match, **PII-leak rate** (hard gate), split three ways.

---

## DECISION: lock **qwen3:4b** + prompt **v2**

| | |
|---|---|
| Score | 83.6% exact / 90.2% semantic — best of everything tested, cloud or local |
| PII leaks | **0** across all 225 rows incl. the name-injected split |
| Licence | Apache 2.0 — clean for a paid SaaS |
| Size | 4B — runs on a small CPU VM (~$100/mo `e2-standard-4`) behind the keyword fast-path, or any entry GPU |
| Serving | Ollama native `/api/chat`, `think:false`, grammar-constrained JSON output (`format` schema) — deterministic, parseable |
| Fallback model | qwen3:1.7b (70.7% / 89.8% / 0) if target hardware can't run 4b fast enough |

---

## Run 1 — prompt v1, cloud (Groq), 225 rows

| model | exact | semantic | gen | personal | messy | PII leak |
|---|---|---|---|---|---|---|
| qwen3.8-27b | 62.2% | 84.4% | 81% | 89% | 80% | 0 |
| gpt-oss-120b | 11.1% | 83.1% | 82% | 86% | 76% | 0 |
| gpt-oss-20b | 47.6% | 78.7% | 77% | 83% | 68% | 0 |

`gemma-4-31b` timed out in preflight, did not run.
Per-response detail: `results/comparison.txt` / `results/comparison.csv`.

**Read:** zero PII leaks on v1 already — the de-identification instruction works.
The exact-match gap is AIDE house-style, not comprehension: over-capitalisation
("Water Request"), "X request" vs the label's "X retrieval assistance",
singular/plural, over-specifying, "Unclear request" firing on real-but-vague
needs, synonyms ("Head pain" vs "Headache").

## Run 2 — prompt v2

v2 adds: "capitalise first word only", the retrieval-vs-request rule, tightened
"Unclear request", a 65-label preferred list, ~24 few-shot examples covering the
exact failure mappings.

Cloud smoke (qwen3.8-27b, 50 general rows): exact 60% -> **92%**, semantic 86% -> **100%**.

## Run 3 — prompt v2, local Ollama (CPU, laptop), 225 rows

| model | params | licence | exact | semantic | gen | personal | messy | PII leak | p50 |
|---|---|---|---|---|---|---|---|---|---|
| **qwen3:4b** | 4B | Apache 2.0 | **83.6%** | **90.2%** | 88% | 94% | 84% | **0** | 2.4s |
| qwen3:1.7b | 1.7B | Apache 2.0 | 70.7% | 89.8% | 87% | 91% | 96% | **0** | 0.9s |
| phi4-mini | 3.8B | MIT | (incomplete, n=4) | | | | | | |
| llama3.2:3b | 3B | Llama | not run | | | | | | |
| gemma3:4b | 4B | Gemma | not run | | | | | | |
| granite3.1-moe:3b | 3B/1B-active | Apache 2.0 | not run | | | | | | |

The laptop (RTX 3050 Ti, but Secure Boot blocked the GPU driver -> CPU only, 7 GB RAM)
lost power three times mid-run. phi4-mini/llama/gemma/granite never completed. qwen3:4b
already clears the bar so they are not decision-critical; if the box stabilises the
watcher finishes them and this table gets filled in.

## Why not a hosted API for the pilot

Established constraint: **no external API calls** in the pilot request path (data
residency / compliance). So the model must be self-hosted. That is why Run 3 (local,
real Q4 quant) is the deciding run and Run 1 (cloud) is only a ceiling reference.
The cloud APIs also no longer host the small deployable models (NIM EOL'd them).

## Open product decision (Noah, not blocking)

Free-text label (current) vs controlled output (fixed `category` enum + `urgency`
+ deterministic label formatter). Free-text at 84-90% semantic / 0 leak is good
enough for the pilot. Controlled output erases the exact-match gap structurally
and unlocks dashboard sort/filter + the analytics revenue stream — a product-v2 item.

## Next

1. Lock qwen3:4b + v2 (this file, CLAUDE.md).
2. Build the rephrase service: FastAPI wrapper = keyword fast-path -> Ollama qwen3:4b
   -> PII post-filter -> safe fallback; `/health`, API-key auth, audit log.
3. Package one Docker image (Ollama + qwen3:4b + wrapper); deploy to a VM in
   `australia-southeast1`.
4. Wire STT -> rephrase -> Redis.
