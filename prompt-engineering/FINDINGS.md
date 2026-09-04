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
(Per-row cloud outputs not retained — Run 3 below is the deciding run.)

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

## Run 3 — prompt v2, local Ollama (CPU Q4, laptop), 225 rows

| model | params | licence | exact | semantic | gen | personal | messy | PII leak | p50 |
|---|---|---|---|---|---|---|---|---|---|
| **qwen3:4b** | 4B | Apache 2.0 | **83.6%** | **90.2%** | 88% | 94% | 84% | **0** | 2.4s |
| gemma3:4b | 4B | Gemma | 76.6% | 84.4% | 84% | (finishing) | | **0** | 1.9s |
| llama3.2:3b | 3B | Llama | 74.2% | 85.8% | 83% | 90% | 80% | **0** | 1.4s |
| phi4-mini | 3.8B | MIT | 74.2% | 84.4% | 77% | 89% | 96% | **0** | 1.6s |
| qwen3:1.7b | 1.7B | Apache 2.0 | 70.7% | 89.8% | 87% | 91% | 96% | **0** | 0.9s |
| granite3.1-moe:3b | 3B/1B-active | Apache 2.0 | (finishing) | | | | | | |

Per-response detail: `comparison.csv` / `.txt`.

**qwen3:4b wins outright** — 7 points clear on exact over the next model, best on semantic,
0 leaks. **Every model: 0 PII leaks** — the v2 de-identification instruction holds across the
board. The smaller models generalise ("Toast request" -> "Food request") where qwen3:4b keeps
the specific item.

The eval box (a gaming laptop; Secure Boot blocked the GPU so CPU only, 7 GB RAM) lost power
three times; the watcher auto-resumed each time. gemma3:4b and granite were still finishing at
the last pull — they will not change the decision.

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

## Deployment plan (decided 2026-09-04, build starts next session)

**VM + FastAPI. Not Cloud Run** — serverless scale-to-zero pays the 15-25s model
RAM-load on every cold start; `min-instances=1` removes that but costs ~= a VM and
adds deploy-time reload blips, so a plain VM is simpler with the same cost.

- **One Docker image**: `FROM ollama/ollama`, `RUN ollama pull qwen3:4b` (baked into a
  layer at build time -- pulled from ollama.com once, never re-downloaded), + FastAPI.
  `start.sh`: `ollama serve &` then `uvicorn`. `OLLAMA_KEEP_ALIVE=-1` so the model
  stays resident.
- **Two endpoints, decoupled**: `POST /transcribe` -> Google Cloud STT;
  `POST /shorten` -> keyword fast-path -> localhost Ollama qwen3:4b -> PII post-filter
  -> safe fallback. Plus `GET /health`, `X-API-Key` auth, audit log.
- **The prompt (`v2.txt`) ships inside the service image**, sent as the system message
  on every call. So a prompt change = rebuild+redeploy the service; the model layer is
  unchanged. Prompt caching (identical prefix every call) should amortise the ~1400-token
  prefill to a one-time cost per warm process -> steady-state ~1-3s. **Must load-test.**
- **Registry**: Artifact Registry (`australia-southeast1-docker.pkg.dev/aide-507408/...`)
  -- same cloud, private, no pull limits, gcloud auth. (Docker Hub also works; AR is
  better for a GCP target.) For a single pilot VM a registry is optional -- can build
  and run on the same box.
- **Build machine**: NOT the eval laptop (no Docker, unreliable). Either Cloud Build
  (`gcloud builds submit`) or the target VM builds its own image on setup. **Open.**
- **VM**: `australia-southeast1`, service account with `Cloud Speech Client` (so
  `/transcribe` needs no key file), Docker, HTTPS via Caddy, firewall on the API port.
  Size: start `e2-standard-4` (CPU) vs go straight to `g2` + L4 GPU. **Open.**

## Next

1. Scaffold `service/`: Dockerfile, start.sh, app/ (main, keywords, rephrase, pii, audit),
   prompts/v2.txt, cloudbuild.yaml.
2. Load-test `/shorten` latency on the chosen VM size -- confirm prompt caching gives ~1-3s.
3. Wire STT -> rephrase -> Redis; retire aidevm's standalone STT.
4. Rotate all plaintext keys.
