# Project Context

> Ground-truth technical context for anyone (human or AI) working in this repo.
> Two independent pieces of work live here:
>
> 1. **Transcription API** (`stt/`) — a deployed FastAPI microservice that wraps
>    Google Cloud Speech-to-Text.
> 2. **Prompt Engineering** (`prompt-engineering/`) — selecting the prompt and
>    open-weight model that turn a raw transcript into a short, de-identified
>    action item, plus the eval harness that made the call.
>
> They are two stages of the same pipeline but are built and deployed as
> **independent, swappable components** — changing the STT provider or the
> rephrasing model must not require touching the other half.

Redacted identifiers appear as `<PLACEHOLDER>` — real project IDs, service
accounts, IPs and keys are not committed. See `.gitignore`.

---

## 1. The pipeline

```
   AUDIO ──▶ [ STT service ] ──▶ TRANSCRIPT ──▶ [ rephrasing service ] ──▶ SHORT ACTION ITEM ──▶ store ──▶ dashboard
             stt/  (BUILT)                       prompt-engineering/       (model + prompt chosen;
                                                                            service wrapper NOT built)
```

- **STT stage** — audio in, raw transcript out. No rephrasing. Built and running
  on a VM. Section 2.
- **Rephrasing stage** — transcript in, 2–5 word de-identified action item out.
  Model (`qwen3:4b`) and prompt (`v2`) locked by evaluation; the FastAPI service
  that wraps them is not built yet. Sections 3–4.

Terminology (these get conflated):

| layer | examples | role |
|---|---|---|
| **model** | Qwen3, Llama, Gemma, Phi | the weights |
| **inference engine** | Ollama, vLLM, llama.cpp | loads and serves the model |
| **our API** | FastAPI | the public boundary — auth, validation, rate-limiting. The inference engine is never exposed directly. |

---

## 2. Transcription API (`stt/`) — BUILT

### 2.1 What it does

A FastAPI microservice: accepts an audio recording, validates it (format, size,
duration), sends it to Google Cloud Speech-to-Text (v2 API, `en-AU`, `long`
model), returns the raw transcript as JSON. First pipeline stage only.

Full source: `stt/main.py`. API docs: `stt/STT-API-Documentation.pdf`.

### 2.2 Infrastructure (as deployed)

| item | value |
|---|---|
| GCP project | `<GCP_PROJECT_ID>` |
| VM | `stt-vm`, zone `us-central1-a` — **US region, see §5.3** |
| Machine type | `e2-medium` (2 vCPU, 4 GB) |
| Boot disk | 10 GB balanced PD, Ubuntu 24.04 minimal |
| Service account | `<compute-service-account>`, role `Cloud Speech Client` |
| App path | `~/aide-stt/main.py`, venv `~/aide-stt/venv/` |
| Process manager | systemd unit `/etc/systemd/system/aide-stt.service` |
| Env | `/etc/aide-stt.env` (root, `chmod 600`) — `AIDE_GCP_PROJECT_ID`, `AIDE_STT_API_KEY` |
| Port | `8000` (Uvicorn `--host 0.0.0.0 --port 8000`) |

Firewall (VM network): ingress `tcp:8000`, `tcp:80`, `tcp:22`, `icmp` all from
`0.0.0.0/0`; internal allow on `10.128.0.0/9`. **HTTPS is not enabled** — traffic,
including the API key, is plain HTTP. See §5.1.

### 2.3 API contract

**Base URL:** `http://<VM_EXTERNAL_IP>:8000`
**Auth:** header `X-API-Key: <shared secret>` on `/transcribe`; missing/invalid → `401`.
Key generated with `openssl rand -hex 32`, stored only in `/etc/aide-stt.env`, never
in git or client-side code.

**`GET /`** — health check, no auth → `{"status":"ok","service":"AIDE Speech-to-Text API"}`

**`POST /transcribe`**
- Headers: `X-API-Key`, `Content-Type: multipart/form-data`
- Body: single field `file`
- Formats: `.wav .mp3 .flac .ogg .m4a .webm` (`webm` = browser `MediaRecorder` default)
- Limits: 25 MB · 5 min (checked via `ffprobe`) · 10 concurrent (excess queues on an `asyncio.Semaphore`)
- `200` → `{"filename": "...", "text": "<raw transcript>"}`

| error | meaning |
|---|---|
| `400` | empty / unreadable audio |
| `401` | missing / invalid API key |
| `413` | > 25 MB or > 5 min |
| `415` | unsupported format or non-audio MIME |
| `500` | unexpected failure — internals logged server-side only, never returned |

> ⚠️ **The `text` field is sensitive.** It is a raw transcript and can contain
> names, room numbers, medical detail (a real test returned
> `"... my name is Jordan please I need assistance here at the room 1035 ..."`).
> Nothing downstream should log, cache or persist it beyond the retention design.
> De-identification is the rephrasing stage's job — this endpoint intentionally
> does not strip anything.

STT config (Speech-to-Text v2), recognizer `projects/<PROJECT>/locations/global/recognizers/_`:
```python
cloud_speech.RecognitionConfig(
    auto_decoding_config=cloud_speech.AutoDetectDecodingConfig(),
    language_codes=["en-AU"],
    model="long",
)
```
Google's dedicated `medical_conversation` / `medical_dictation` models have clinical
vocabulary but are **en-US only**, so the general model (which supports en-AU) was
kept. Worth re-testing both against real accented audio before treating that as settled.

### 2.4 Security already implemented

API-key auth · extension + MIME validation before processing · size cap enforced
before the full read · duration cap via `ffprobe` before the Google call · concurrency
semaphore · generic `500`s (no Google/project/IAM detail leaked) · transcript/audio
never logged (only metadata) · `get_audio_duration` catches `FileNotFoundError`
(missing `ffprobe`) and anything else so nothing bypasses the safe-error layer.

### 2.5 Developer access

GCP IAM + OS Login (no manually-shared SSH keys). OS Login enabled via VM metadata
`enable-oslogin=TRUE`. Grants: an owner account (full), a collaborator account
(`Compute OS Login` + `Compute Viewer`), and the compute service account
(`Cloud Speech Client`, used by the app).

```bash
gcloud auth login
gcloud config set project <GCP_PROJECT_ID>
gcloud compute ssh stt-vm --zone=us-central1-a
# on the VM:
sudo systemctl status aide-stt        # running?
sudo journalctl -u aide-stt -f        # live logs
sudo systemctl restart aide-stt       # restart
```

### 2.6 Frontend integration

**Do not call `/transcribe` from browser JS** — no CORS, and the API key would be
exposed. Proxy server-side:

```
browser (records audio) ──▶ your backend route (holds the key) ──▶ STT VM /transcribe ──▶ Google STT
```

One server-side place to hold the key, no CORS issue, and one place to plug in the
next pipeline step (forward `text` to the rephrasing service).

### 2.7 Confirmed working

Real end-to-end test (upload → validate → Google STT → transcript returned) passed.
The returned transcript contained a name and room number — a concrete demonstration
of the PII-in-raw-transcript problem the rephrasing stage must solve.

---

## 3. Rephrasing stage — what it must do

Transcript → short, de-identified, staff-facing action item.

```
IN:  "I've been waiting here for ages and I'm really thirsty. Can someone please bring me some water?"
OUT: "Water request"
```

A **narrow transformation problem**, not general reasoning — which is why a small
open-weight model is enough. Output format (closed convention, see
`prompt-engineering/LABEL_CONVENTION.md`): 2–5 words, Title Case (first word only),
no punctuation, topic first, ending in one of `{request, assistance, adjustment,
question, update}`, and **no name / age / location even if the patient states it**.

Approach, ranked: (1) prompt engineering on an existing model — done; (2) fine-tune
a small model later, once real labelled pilot data exists; (3) train from scratch —
ruled out.

### 3.1 Architecture-within-architecture: keyword fast-path

An intent check in front of the model, so obvious requests skip the model entirely:

```
transcript ─▶ keyword/rule match?  ── yes ──▶ label directly (no model call, ~instant)
                     │
                     └─ no ──▶ model ──▶ label
                                   │
                         both ─▶ PII post-filter ─▶ safe fallback ─▶ store ─▶ dashboard
```

`"water please"` → keyword match. `"my mouth is extremely dry, is there any chance
somebody could get me something to drink"` → model. Cuts inference cost, latency,
compute and failure surface.

### 3.2 Service boundary

```
client ─▶ Rephrase API (FastAPI)  ── auth, validation, rate-limit, PII filter, audit log
                 │  authenticated, private
                 ▼
          Ollama / vLLM (never internet-exposed) ─▶ qwen3:4b
```

---

## 4. Rephrasing — evaluation and decision (`prompt-engineering/`)

Full write-up: `prompt-engineering/FINDINGS.md` and `Prompt-Testing-Report.pdf`.
Per-response detail: `prompt-engineering/comparison.csv`.

### 4.1 Datasets

`prompt-engineering/data/`:

| file | rows | purpose |
|---|---|---|
| `AIDE_100_general_dataset.csv` | 100 | clean requests → label |
| `AIDE_100_personal_data_dataset.csv` | 100 | same requests + injected name/age/town; labels strip all of it |
| `AIDE_200_row_LLM_evaluation_dataset.csv` | 200 | the two above concatenated, with a `dataset` split column |
| `AIDE_training_data_with_expected_shortened.csv` | 25 | messier, disfluent, ASR-style transcripts |
| `eval_set_225.csv` | 225 | the 200-row set + the 25 messy rows (`dataset=realistic_messy`) — **what the harness scores against** |

(The `AIDE_` filename prefix is a legacy project codename; the data is synthetic.)

The `personal_data_injected` split is the important one: it tests *does the model
strip PII while shortening*, not just *can it shorten*. Scored separately, never
blended.

`LABEL_CONVENTION.md` documents the closed label format; `validate_labels.py`
enforces it. Only the 25-row file was off-convention (3 labels fixed).

### 4.2 Prompt

`prompt-engineering/prompts/` — `v1.txt` then `v2.txt` (the harness takes `--prompt`).
**v2 is locked.** v1 stated the rules; v2 adds "capitalise the first word only", an
explicit retrieval-vs-request rule, a tightened "Unclear request", a ~65-label
preferred list, and ~24 few-shot examples built from v1's failure cases (mixing
clean and PII-injected inputs). v1 → v2 on a 50-row cloud smoke test: exact 60% → 92%.

### 4.3 Eval harness

`prompt-engineering/eval/` — `run_eval.py` + `score.py`. Provider-agnostic
(OpenAI-compatible: NVIDIA NIM, Groq; plus an Ollama native path with
`think:false` + JSON-schema constrained output). One model at a time, no
cross-model failover, rate-limited, checkpointed per row (kill and re-run to
resume), auto-scores.

Metrics, split by `general` / `personal_data_injected` / `realistic_messy`:

1. **exact** — normalised output == expected, case-sensitive.
2. **semantic** — same category noun (or topic) + ≥ 50% content-word overlap after singularising.
3. **pii_leak** (hard gate) — output contains a digit, or a patient name/town from the transcript not in the label. Any leak disqualifies a model.

`compare.py` builds the per-transcript side-by-side. `make_report.py` builds the PDF.

### 4.4 Results

**Run 1** (prompt v1, cloud/Groq, 225 rows): qwen3.8-27b 62%/84%, gpt-oss-120b
11%/83%, gpt-oss-20b 48%/79%. All 0 PII leaks. Exact-match gap was house-style
(capitalisation etc.), not comprehension.

**Run 3** (prompt v2, self-hosted Ollama, CPU, Q4, 225 rows):

| model | params | licence | exact | semantic | PII leak |
|---|---|---|---|---|---|
| **qwen3:4b** | 4B | Apache 2.0 | **83.6%** | **90.2%** | **0** |
| gemma3:4b | 4B | Gemma | 76.6% | 84.4% | 0 |
| llama3.2:3b | 3B | Llama | 74.2% | 85.8% | 0 |
| phi4-mini | 3.8B | MIT | 74.2% | 84.4% | 0 |
| qwen3:1.7b | 1.7B | Apache 2.0 | 70.7% | 89.8% | 0 |

**Every model: 0 PII leaks** — v2's de-identification holds across the board.

### 4.5 DECISION — locked

**`qwen3:4b` + prompt `v2`.** 83.6% exact / 90.2% semantic / 0 leaks — best of every
model tested, cloud or local, ahead of the 27B. Apache 2.0. Runs on a small CPU VM
behind the keyword fast-path. **Fallback:** `qwen3:1.7b` if hardware can't keep
`qwen3:4b` latency acceptable.

Self-hosted (not a hosted API) because the pilot forbids external API calls in the
request path (data residency). The cloud eval is a ceiling reference only; the free
APIs no longer host the small deployable models.

### 4.6 Deployment plan (decided, build not started)

**VM + FastAPI, not Cloud Run.** Serverless scale-to-zero pays a 15–25s model
RAM-load on every cold start; pinning one warm instance costs about the same as a VM,
so a plain VM is simpler for the same money.

- **One Docker image**: `FROM ollama/ollama`, `RUN ollama pull qwen3:4b` (baked into
  a layer at build time — downloaded once, never re-downloaded), + FastAPI.
  `start.sh`: `ollama serve &` then `uvicorn`. `OLLAMA_KEEP_ALIVE=-1`.
- **Two endpoints, decoupled**: `POST /transcribe` → Google Cloud STT;
  `POST /shorten` → keyword fast-path → localhost Ollama qwen3:4b (`/api/chat`,
  `think:false`, JSON schema) → PII post-filter → safe fallback. Plus `GET /health`,
  `X-API-Key`, audit log (transcript, output, model + prompt version, latency).
- **Prompt `v2.txt` ships inside the service image**, sent as the system message per
  call. A prompt change rebuilds the service, not the model layer. The identical
  prefix every call lets the engine cache the ~1400-token prefill → steady-state
  ~1–3s (must load-test).
- **Registry**: Artifact Registry (same cloud, private, no pull limits) — or none,
  building and running on the one VM.
- **Build machine**: not the eval laptop. Cloud Build or the target VM. OPEN.
- **VM**: `australia-southeast1`, service account with `Cloud Speech Client` (so
  `/transcribe` needs no key file), Docker, HTTPS via Caddy, firewall on the API
  port. Size: `e2-standard-4` CPU vs `g2` + L4 GPU. OPEN — needs the latency test.

---

## 5. Known gaps and open decisions

### 5.1 Security
- **HTTPS not enabled** on the STT VM — API key travels plain HTTP. Needs Caddy /
  Nginx + Let's Encrypt in front of Uvicorn before real patient audio.
- **SSH open to `0.0.0.0/0`** — not a breach (OS Login still needs valid IAM) but
  invites internet-wide port-22 scanning. Restrict to known IPs or use IAP.
- API-key rotation process not defined.

### 5.2 Compliance / privacy
- Self-hosting the model helps (control over inference location, storage, retention,
  network) but does **not by itself make the system compliant** — needs real
  privacy/legal review against the applicable privacy and health-records regulation
  before any compliance claim.
- Raw STT transcripts contain PII by design — every consumer of `/transcribe` must
  treat the response as sensitive.

### 5.3 Data residency
- The STT VM is in `us-central1-a` (United States). If the compliance story requires
  patient data to stay in-country, this needs to move. Flagged early because it gets
  harder to migrate later.

### 5.4 Scaling
- Single VM, no autoscaling, no queue. STT concurrency capped at 10 (queues, doesn't
  fail). Fine for pilot testing; load-test (10 → 25 → 50 → 100 concurrent) before a
  real deployment.

### 5.5 Rephrasing service
- Model + prompt locked; the FastAPI wrapper, Docker image, and VM are not built.
  Next: answer the two OPEN questions in §4.6, then scaffold `service/`.

### 5.6 Open product decision (not blocking the build)
- Free-text label (current) vs controlled output (fixed `category` enum + `urgency`
  + deterministic label formatter). Free-text at 84–90% semantic / 0 leak is enough
  for a pilot; controlled output removes the exact-match gap structurally and
  enables dashboard sort/filter.

### 5.7 Secrets to rotate
Any key that has been handled in plaintext during development: the STT API key
(`stt/env_variables.txt`, gitignored), and any model-provider keys in
`prompt-engineering/.env` (gitignored). None are committed.

---

## 6. Immediate next steps

1. Answer §4.6 OPEN questions: build machine, VM size.
2. Scaffold `service/`: `Dockerfile` (`FROM ollama/ollama`, `RUN ollama pull qwen3:4b`),
   `start.sh`, `app/` (`main.py` = `/transcribe` + `/shorten` + `/health` + `X-API-Key`;
   `keywords.py` fast-path; `rephrase.py` = Ollama `/api/chat` + `think:false` + JSON
   schema + v2 prompt; `pii.py` post-filter → safe fallback; `audit.py`),
   `prompts/v2.txt`, `cloudbuild.yaml`. Ollama never exposed directly.
3. Load-test `/shorten` latency on the chosen VM; confirm ~1–3s steady state.
4. Wire STT → rephrase → store. First end-to-end second-generation pipeline.
   Retire the standalone STT VM.
5. Rotate all plaintext keys.
6. Reserve the STT VM external IP as static (currently ephemeral).
7. Enable HTTPS + lock down SSH before real patient audio.

---

## 7. Conventions

- **STT** = the transcription stage (`stt/`, built). **Rephrasing** = the shortening
  stage (`prompt-engineering/` for the eval; a `service/` wrapper still to build).
  Always separate, swappable components — do not conflate.
- Rephrasing work and its `.env` live in `prompt-engineering/` — see its `README.md`
  and `FINDINGS.md`. `.env` is gitignored.
- Redacted identifiers use `<PLACEHOLDER>`. Never commit a real project ID, service
  account, IP, or key.
