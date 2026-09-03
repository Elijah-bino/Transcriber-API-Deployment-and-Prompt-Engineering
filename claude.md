# AIDE — Full Project Context

> **Purpose of this document:** This is the ground-truth context file for any AI assistant (Claude Code included) working on AIDE's codebase. It covers what AIDE is, why it exists, everything built so far, everything decided but not yet built, and everything still open. If something isn't covered here or in `AIDE.md` (the product/business context doc), don't guess — flag it and ask, or check with Elijah (backend infra) or Noah (CEO).
>
> This document is technical infrastructure-focused. For product/business/regulatory/market context (team, funding, TGA status, pricing, design system), see the separate `AIDE.md` context document — this file assumes that one exists alongside it and doesn't repeat all of it, though key parts are summarized in Section 1 for standalone usefulness.

---

## 1. What AIDE Is (Summary)

AIDE is a Melbourne-based health-tech startup building a voice-powered patient request platform for hospital wards and aged care facilities. Patients speak requests into a device (currently a phone/browser, no dedicated hardware). AI transcribes and rephrases each request into a concise, de-identified action item displayed on a shared nurse dashboard — so staff know what a patient needs before walking to the room.

Tagline: **"Know before you go."**

### The core problem

A traditional nurse call button carries exactly one bit of information: someone wants something. The nurse walks to the room blind — could be water, pain relief, a bathroom trip, or an emergency. That creates wasted trips, no ability to prioritise by urgency, and slower response for patients who genuinely need something urgent.

### AIDE's actual four-part loop

This is the precise definition of what AIDE does, and it matters for both product decisions and competitive positioning — a company only counts as a functional competitor if it does most or all of this loop, not just something in the same broad "AI voice in healthcare" category:

1. **Patient-initiated voice input** — the patient speaks the request themselves, in the moment, with no hardware beyond a phone or browser.
2. **AI rephrasing into an action item** — the raw transcript becomes a short, de-identified summary ("assistance requested," "water," "pain relief").
3. **A shared staff dashboard** — the rephrased request appears for the ward before a nurse walks over, with room number and timestamp.
4. **A compliance-grade response log** — original transcript, AI rephrasing, and total response time, recorded per request.

### Team

- **Noah** — CEO and Co-Founder. Product vision, strategy, stakeholder relations.
- **Two co-founders (CTO titles)** — full-stack development, AI integration, platform infrastructure.
- **One co-founder (CFO and Head of Brand)** — financial planning, brand strategy, go-to-market.
- **Elijah** (this doc's primary author/user) — handles backend infrastructure build and maintenance. Master of Data Science student at Monash, also works at Electrify Your Life (energy NGO) and Woolworths part-time. Melbourne-based.
- **Vivek Subramaniam** — developer friend, building the frontend, collaborating on backend integration.

Company status: pre-incorporation, no ABN yet, ~$800 funding to date, $0 revenue, 0 customers, pre-pilot. Origin: started as "NurseCall" in a Monash Generator Startup Sprint, rebranded to AIDE.

### Brand system (for any UI/doc generation work)

- **Colours:** Ward Green `#0B3630`, Alert Amber `#E8914A`, Resolved Teal `#5AC9A8`, Linen `#FAF6F0`
- **Typography:** DM Serif Display (headings), Inter (body)
- **Content standards:** short sentences, plain language, no em-dashes in AIDE-facing content, every claim needs a cited source, no fabricated statistics/quotes/case studies

---

## 2. System Architecture — Current and Planned

### 2.1 High-level pipeline (target state)

```
          PATIENT
             │
             ▼
           AUDIO
             │
             ▼
        ┌─────────┐
        │   STT   │   ← BUILT (this doc, Section 3)
        └────┬────┘
             │
             ▼
         TRANSCRIPT
             │
             ▼
       ┌───────────┐
       │ AIDE LLM  │   ← NOT YET BUILT (this doc, Section 4)
       └─────┬─────┘
             │
             ▼
      SHORT REQUEST
             │
             ▼
       STRUCTURED DATA
             │
             ▼
           REDIS  →  NURSE DASHBOARD (existing web MVP)
```

STT and the LLM rephrasing step are treated as **independent, swappable components**. Neither should be tightly coupled to the other's implementation — you can change the STT provider or the LLM/model without touching the other half.

### 2.2 Two live/planned generations of the stack

**Generation 1 (original web MVP, already built and functional, per `AIDE.md`):**
- Frontend: Next.js, TypeScript, Tailwind CSS, hosted on Vercel
- Transcription: Web Speech API (browser-native)
- AI rephrasing: cloud AI via OpenRouter (Kimi K2.5)
- Database: Upstash Redis
- Repo: `github.com/deltaromeomngo-create/nurse-call`
- Live MVP: `nurse-call-pi.vercel.app`

**Generation 2 (in progress — what this document mainly covers):**
- Transcription: dedicated GCP-hosted STT microservice (Section 3) using Google Cloud Speech-to-Text, replacing the browser-native Web Speech API for reliability, accuracy (en-AU, medical vocab), and architectural control
- Rephrasing: moving toward a self-hosted open-weight LLM on GCP infrastructure (Section 4), replacing/supplementing the OpenRouter/Kimi call, primarily for data-residency and long-term cost control
- Rationale for the shift: the original architecture (`AIDE → OpenRouter → Kimi`) sends raw patient conversation data to a third-party general-purpose LLM API. If AIDE's core product/compliance promise is that sensitive patient information stays under AIDE's own infrastructure, that's a real architectural risk worth addressing before scaling, even though it's functionally working today.

### 2.3 Why self-host at all — the reasoning, spelled out

There are two separate legal/practical questions that get conflated easily:

1. **Can we commercially use this model?** — a model-license question (Section 4.4 answers this for the current shortlist).
2. **Can we legally process patient information using this architecture?** — a completely different question, about data flow, storage, retention, and jurisdiction. Self-hosting *helps* here because AIDE controls where inference happens, network access, storage, logs, backups, access controls, retention, and encryption — but self-hosting does **not automatically make AIDE compliant**. That must be validated with actual privacy/legal/regulatory professionals, not assumed from the architecture alone.

### 2.4 Inference architecture concepts (terminology, since these get mixed up easily)

Three distinct layers:
- **The model** — e.g. Qwen, Llama, Gemma, Mistral/Ministral, Phi. The actual weights.
- **The inference engine/server** — e.g. Ollama, vLLM, llama.cpp, Hugging Face Transformers. Software that loads and serves the model.
- **AIDE's own API** — FastAPI, which the frontend/backend calls. This is the layer that should be the actual security boundary — the raw inference engine (Ollama, etc.) should never be exposed directly to the internet.

```
Internet
   ↓
AIDE API (FastAPI)   ← public-facing, does auth/validation/rate-limiting
   ↓
private/internal Ollama or vLLM   ← never exposed directly
   ↓
Model (Qwen/Gemma/etc.)
```

**Inference engine options considered:**
| Option | Summary | When to use |
|---|---|---|
| **Ollama** | Very easy local runtime (`ollama pull`, `ollama run`), exposes an OpenAI-compatible API on `localhost:11434` | Best for development and first prototype — handles model loading/quantization complexity for you |
| **vLLM** | Production-grade inference server, OpenAI-compatible API, better throughput/GPU utilization/concurrency | Best once moving to a real production serving layer; Google's own docs describe serving Gemma on GKE via vLLM |
| **llama.cpp** | Lightweight HTTP server, excellent for smaller/quantized models and CPU-oriented deployments | Good fit if staying on CPU-only VMs longer than expected |
| **Hugging Face Transformers** | Maximum flexibility, direct Python integration | Not recommended as the production serving layer — more useful for experimentation |

**Decision for now:** Ollama for development and the first production prototype (already directionally planned per `AIDE.md`'s "Ollama + Llama 3.2 3B on Raspberry Pi 5" note — though the model choice itself is being revisited, see Section 4.3). Re-evaluate vLLM vs Ollama vs llama.cpp once real throughput/latency/concurrency requirements are known.

### 2.5 Important operational nuance: "local inference" ≠ "no internet"

Running Ollama locally does not inherently require sending prompts to an external LLM provider — inference can happen entirely on the VM. But the VM itself will still have other network traffic (model downloads, OS/package updates, Docker pulls, monitoring, DNS). "Patient data must never leave our controlled infrastructure" is an architectural/security requirement that must be enforced at the network and application level (e.g. GCP firewall rules restricting outbound traffic), not something to assume is automatically true just because Ollama is installed.

---

## 3. STT Service — BUILT

### 3.1 What it does

A FastAPI microservice that accepts a patient's audio recording, validates it, sends it to Google Cloud Speech-to-Text (v2 API), and returns the raw transcript as JSON. This is the first stage of the pipeline only — no rephrasing/shortening happens here.

### 3.2 Infrastructure

| Item | Value |
|---|---|
| GCP Project ID | `aide-507408` |
| VM name | `aidevm` |
| Zone | `us-central1-a` (⚠️ US region — see Section 6.3, data residency flag) |
| Machine type | `e2-medium` (2 vCPUs, 4 GB memory) |
| Boot disk | 10 GB, Balanced persistent disk, Ubuntu 24.04 minimal (noble) |
| Service account | `506159084397-compute@developer.gserviceaccount.com`, has `Cloud Speech Client` role |
| App location on VM | `~/aide-stt/main.py`, Python venv at `~/aide-stt/venv/` |
| Process manager | `systemd` — unit file `/etc/systemd/system/aide-stt.service` |
| Env vars | Loaded from `/etc/aide-stt.env` (root-owned, `chmod 600`) — contains `AIDE_GCP_PROJECT_ID` and `AIDE_STT_API_KEY` |
| Port | `8000` (Uvicorn, `--host 0.0.0.0 --port 8000`) |

**Firewall rules currently active on this VM's network:**
| Rule | Direction | Target | Source | Protocol/Port | Action |
|---|---|---|---|---|---|
| `allow-fastapi-8000` | Ingress | All | `0.0.0.0/0` | `tcp:8000` | Allow |
| `default-allow-http` | Ingress | `http-server` tag | `0.0.0.0/0` | `tcp:80` | Allow |
| `default-allow-ssh` | Ingress | All | `0.0.0.0/0` | `tcp:22` | Allow — ⚠️ open to the whole internet, see Section 6.3 |
| `default-allow-icmp` | Ingress | All | `0.0.0.0/0` | `icmp` | Allow |
| `default-allow-internal` | Ingress | All | `10.128.0.0/9` | all | Allow |

HTTPS is **not** currently enabled on this VM (confirmed Off in console). All traffic including the API key travels as plain HTTP. See Section 6.3.

### 3.3 API contract

**Base URL:** `http://<VM_EXTERNAL_IP>:8000` (get current IP via `curl ifconfig.me` on the VM, or GCP Console → Compute Engine → aidevm → External IP)

**Authentication:** every request to `/transcribe` requires header `X-API-Key: <shared secret>`. Missing/invalid key → `401`. The key is generated via `openssl rand -hex 32`, stored in `/etc/aide-stt.env`, never committed to git, never placed in client-side/browser code.

#### `GET /` — health check, no auth required
Response `200`:
```json
{ "status": "ok", "service": "AIDE Speech-to-Text API" }
```

#### `POST /transcribe`
**Headers:** `X-API-Key` (required), `Content-Type: multipart/form-data`
**Body:** single field `file` (the audio file)

**Allowed formats:** `.wav` `.mp3` `.flac` `.ogg` `.m4a` `.webm` (webm added specifically because browser `MediaRecorder` defaults to webm in Chrome/Firefox)

**Limits:** 25 MB max file size · 5 minute max duration (checked via `ffprobe`) · 10 max simultaneous transcriptions (additional requests queue via an `asyncio.Semaphore`, don't fail)

**Success response `200`:**
```json
{
  "filename": "test_audio.mp3",
  "text": "hello hi hi my name is Elijah please I need assistance here at the room 1035 my charger dropped down and my phone is about to die I need to call my parents I need help please somebody come"
}
```
⚠️ **This response is sensitive.** The `text` field is a raw, unprocessed transcript and can contain names, room numbers, and other identifying details (confirmed by the example above, captured during real testing). Nothing downstream should log, cache, or persist this response outside of what AIDE's actual data-retention design accounts for. The de-identification/rephrasing step (Section 4) is what's supposed to strip this — this endpoint intentionally does not.

**Error responses:**
| Status | Meaning |
|---|---|
| `400` | Empty or unreadable audio file |
| `401` | Missing/invalid API key |
| `413` | File >25MB or audio >5min |
| `415` | Unsupported format or non-audio MIME type |
| `500` | Unexpected failure (Google STT error etc.) — internals are never leaked to the client; logged server-side only |

**STT configuration specifics (Google Cloud Speech-to-Text v2):**
```python
config = cloud_speech.RecognitionConfig(
    auto_decoding_config=cloud_speech.AutoDetectDecodingConfig(),
    language_codes=["en-AU"],
    model="long",
)
```
Recognizer path: `projects/{PROJECT_ID}/locations/global/recognizers/_`

Google Cloud Speech-to-Text also offers dedicated `medical_conversation` / `medical_dictation` models with clinical vocabulary — **but these are currently en-US locale only**, so the general model (which supports en-AU) was kept instead. Worth re-testing both against real accented patient audio before assuming the general model is the better choice long-term — it's an accuracy tradeoff, not a settled decision.

### 3.4 Security measures already implemented

- API key auth (Section 3.3)
- File extension + MIME type validation before any processing
- File size cap enforced before reading the full file into memory
- Audio duration cap enforced via `ffprobe` before sending to Google (protects against small-but-long compressed files)
- Concurrency limiting via semaphore (protects the 4GB VM from being overwhelmed)
- Generic `500` responses — internal errors (Google API details, project IDs, IAM info) are logged server-side only, never returned to the client
- Transcript/audio content is never logged — only metadata (file size, format, duration, timing) appears in logs
- `get_audio_duration`'s exception handling was widened to catch `FileNotFoundError` (e.g. `ffprobe` missing) and any other unexpected error, so nothing bypasses the safe-error-response layer

### 3.5 Access control for developers

Access is via **GCP IAM with OS Login**, not manually-shared SSH keys — Google manages key exchange automatically once a Google account has the right IAM roles.

**Current grants:**
| Principal | Roles |
|---|---|
| `elijahbino369@gmail.com` (Elijah) | Owner, Organization Administrator, Project Mover, Service Usage Admin |
| `1049viveksubramaniang@gmail.com` (Vivek) | `Compute OS Login` (roles/compute.osLogin — standard non-root SSH), `Compute Viewer` (roles/compute.viewer — needed for `gcloud` to look up VM details when connecting) |
| `506159084397-compute@developer.gserviceaccount.com` | `Cloud Speech Client` (service account used by the app itself) |

OS Login is enabled on the VM via custom metadata `enable-oslogin=TRUE`.

**Connection command (for any dev with granted access):**
```bash
gcloud auth login
gcloud config set project aide-507408
gcloud compute ssh aidevm --zone=us-central1-a
```

If sudo/admin access is needed later, upgrade the relevant IAM role from `Compute OS Login` to `Compute OS Admin Login` (roles/compute.osAdminLogin).

**Debugging commands once connected:**
```bash
sudo systemctl status aide-stt      # is it running?
sudo journalctl -u aide-stt -f      # live logs
sudo systemctl restart aide-stt     # restart the service
```

### 3.6 Recommended frontend integration pattern

**Do not call this endpoint directly from browser JavaScript.** No CORS headers are configured, and embedding the API key in client-side code exposes it to anyone reading the network tab.

```
Patient's browser
      │  (records audio, POSTs to AIDE's OWN backend)
      ▼
Next.js API route (server-side, e.g. /app/api/transcribe/route.ts)
      │  (holds the API key, forwards the request)
      ▼
AIDE STT VM (/transcribe)
      │
      ▼
Google Speech-to-Text
```

Example server-side proxy:
```javascript
// app/api/transcribe/route.ts
export async function POST(req) {
  const incoming = await req.formData();
  const res = await fetch("http://<VM_EXTERNAL_IP>:8000/transcribe", {
    method: "POST",
    headers: { "X-API-Key": process.env.AIDE_STT_API_KEY },
    body: incoming,
  });
  const data = await res.json();
  return Response.json(data);
}
```

This gives three things at once: no CORS issue (browser only talks to its own domain), the API key never reaches the browser, and there's one place (the Next.js route) to plug in the next pipeline step (forwarding `text` to the rephrasing LLM) without touching frontend code.

### 3.7 Full current `main.py` source

```python
from fastapi import FastAPI, UploadFile, File, HTTPException, Header
from google.cloud import speech_v2
from google.cloud.speech_v2.types import cloud_speech
import asyncio
import logging
import os
import subprocess
import tempfile


# ============================================================
# Configuration
# ============================================================

APP_NAME = "AIDE Speech-to-Text API"

PROJECT_ID = os.environ["AIDE_GCP_PROJECT_ID"]
LOCATION = "global"

API_KEY = os.environ["AIDE_STT_API_KEY"]

MAX_FILE_SIZE = 25 * 1024 * 1024       # 25 MB
MAX_DURATION_SECONDS = 5 * 60          # 5 minutes
MAX_CONCURRENT_TRANSCRIPTIONS = 10

ALLOWED_EXTENSIONS = {
    ".wav",
    ".mp3",
    ".flac",
    ".ogg",
    ".m4a",
    ".webm",    # browser MediaRecorder default (Chrome/Firefox)
}


# ============================================================
# Logging
# ============================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)

logger = logging.getLogger(APP_NAME)


# ============================================================
# Application
# ============================================================

app = FastAPI(title=APP_NAME)

client = speech_v2.SpeechClient()

transcription_semaphore = asyncio.Semaphore(
    MAX_CONCURRENT_TRANSCRIPTIONS
)


# ============================================================
# Helper: get file extension
# ============================================================

def get_extension(filename: str | None) -> str:
    if not filename:
        return ""

    return os.path.splitext(filename.lower())[1]


# ============================================================
# Helper: validate duration using ffprobe
# ============================================================

def get_audio_duration(audio_data: bytes, extension: str) -> float:
    """
    Write the uploaded audio temporarily and use ffprobe
    to determine its duration.

    The temporary file is deleted automatically.
    """

    suffix = extension if extension else ".audio"

    temp_path = None

    try:
        with tempfile.NamedTemporaryFile(
            suffix=suffix,
            delete=False,
        ) as temp_file:

            temp_file.write(audio_data)
            temp_path = temp_file.name

        result = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                temp_path,
            ],
            capture_output=True,
            text=True,
            timeout=15,
        )

        if result.returncode != 0:
            raise ValueError("Unable to read audio duration.")

        duration = float(result.stdout.strip())

        return duration

    except subprocess.TimeoutExpired:
        raise ValueError("Audio validation timed out.")

    except (ValueError, TypeError):
        raise ValueError("Invalid or unreadable audio file.")

    except Exception:
        # Catches FileNotFoundError (ffprobe missing/misconfigured)
        # and anything else unexpected, so nothing escapes this
        # function and bypasses the safe error response below.
        raise ValueError("Invalid or unreadable audio file.")

    finally:
        if temp_path and os.path.exists(temp_path):
            os.remove(temp_path)


# ============================================================
# Health check
# ============================================================

@app.get("/")
def health_check():
    return {
        "status": "ok",
        "service": APP_NAME,
    }


# ============================================================
# Transcription endpoint
# ============================================================

@app.post("/transcribe")
async def transcribe(
    file: UploadFile = File(...),
    x_api_key: str = Header(default=None),
):

    # --------------------------------------------------------
    # 0. Authenticate the caller
    # --------------------------------------------------------

    if x_api_key != API_KEY:
        logger.warning("Rejected request: missing or invalid API key.")

        raise HTTPException(
            status_code=401,
            detail="Unauthorized.",
        )

    filename = file.filename or "unknown"

    logger.info(
        "Received transcription request: %s",
        filename,
    )

    # --------------------------------------------------------
    # 1. Validate file extension
    # --------------------------------------------------------

    extension = get_extension(filename)

    if extension not in ALLOWED_EXTENSIONS:
        logger.warning(
            "Rejected unsupported file format: %s",
            extension or "unknown",
        )

        raise HTTPException(
            status_code=415,
            detail=(
                "Unsupported audio format. "
                "Allowed formats: WAV, MP3, FLAC, OGG, M4A, WEBM."
            ),
        )

    # --------------------------------------------------------
    # 2. Validate MIME type
    # --------------------------------------------------------

    if not file.content_type or not file.content_type.startswith("audio/"):
        logger.warning(
            "Rejected invalid MIME type: %s",
            file.content_type,
        )

        raise HTTPException(
            status_code=415,
            detail="Uploaded file must be an audio file.",
        )

    # --------------------------------------------------------
    # 3. Read file with size protection
    # --------------------------------------------------------

    audio_data = await file.read()

    file_size = len(audio_data)

    if file_size == 0:
        logger.warning(
            "Rejected empty audio file: %s",
            filename,
        )

        raise HTTPException(
            status_code=400,
            detail="Audio file is empty.",
        )

    if file_size > MAX_FILE_SIZE:
        logger.warning(
            "Rejected oversized file: %s (%.2f MB)",
            filename,
            file_size / (1024 * 1024),
        )

        raise HTTPException(
            status_code=413,
            detail="Audio file exceeds the 25 MB limit.",
        )

    logger.info(
        "Audio accepted: %.2f MB",
        file_size / (1024 * 1024),
    )

    # --------------------------------------------------------
    # 4. Validate audio duration
    # --------------------------------------------------------

    try:
        duration = get_audio_duration(
            audio_data,
            extension,
        )

    except ValueError as exc:

        logger.warning(
            "Audio validation failed: %s",
            str(exc),
        )

        raise HTTPException(
            status_code=400,
            detail="Invalid or unreadable audio file.",
        )

    logger.info(
        "Audio duration: %.2f seconds",
        duration,
    )

    if duration <= 0:
        raise HTTPException(
            status_code=400,
            detail="Audio duration could not be determined.",
        )

    if duration > MAX_DURATION_SECONDS:
        logger.warning(
            "Rejected audio longer than 5 minutes: %.2f seconds",
            duration,
        )

        raise HTTPException(
            status_code=413,
            detail="Audio duration exceeds the 5 minute limit.",
        )

    # --------------------------------------------------------
    # 5. Limit simultaneous transcription requests
    # --------------------------------------------------------

    logger.info(
        "Waiting for transcription slot..."
    )

    async with transcription_semaphore:

        logger.info(
            "Transcription slot acquired."
        )

        try:

            # ------------------------------------------------
            # Google Speech-to-Text configuration
            # English (Australia)
            # ------------------------------------------------

            config = cloud_speech.RecognitionConfig(
                auto_decoding_config=(
                    cloud_speech.AutoDetectDecodingConfig()
                ),
                language_codes=["en-AU"],
                model="long",
            )

            request = cloud_speech.RecognizeRequest(
                recognizer=(
                    f"projects/{PROJECT_ID}"
                    f"/locations/{LOCATION}"
                    f"/recognizers/_"
                ),
                config=config,
                content=audio_data,
            )

            logger.info(
                "Sending audio to Google Speech-to-Text."
            )

            response = client.recognize(
                request=request
            )

            transcript = " ".join(
                result.alternatives[0].transcript
                for result in response.results
                if result.alternatives
            ).strip()

            logger.info(
                "Transcription completed successfully."
            )

            # ------------------------------------------------
            # Return result
            #
            # NOTE: this response contains the raw patient
            # transcript and may include PII (names, room
            # numbers, medical details). Callers must not log,
            # cache, or persist this response casually.
            # ------------------------------------------------

            return {
                "filename": filename,
                "text": transcript,
            }

        except Exception:

            # Do NOT expose Google's internal error details
            # to the API client.

            logger.exception(
                "Speech-to-text processing failed."
            )

            raise HTTPException(
                status_code=500,
                detail="Speech-to-text processing failed.",
            )
```

### 3.8 Confirmed working test

Real test performed against the deployed service:
```json
{
  "filename": "test_audio.mp3",
  "text": "hello hi hi my name is Elijah please I need assistance here at the room 1035 my charger dropped down and my phone is about to die I need to call my parents I need help please somebody come"
}
```
This confirms end-to-end functionality: file upload → validation → Google STT → transcript returned. It also concretely demonstrates the PII-in-raw-transcript issue described in Section 3.3 — the transcript includes name and room number, which the downstream rephrasing stage (Section 4) must strip.

---

## 4. LLM Rephrasing Service — NOT YET BUILT (design decisions made)

### 4.1 What it needs to do

Take the raw transcript from Section 3 and produce a short, de-identified, staff-facing action item.

```
INPUT:  "I've been waiting here for ages and I'm really thirsty.
         Can someone please bring me some water?"
OUTPUT: "Water assistance"
```

This is a **narrow transformation problem**, not a general-purpose reasoning task. That single fact drives most of the design decisions below — a large/frontier model is very likely unnecessary.

### 4.2 Explicit decision: prompt engineering first, not fine-tuning, not building a model from scratch

Ranked approach, in the order to actually pursue:

1. **Prompt engineering on an existing model** (current state: OpenRouter/Kimi K2.5; being evaluated: small self-hosted open-weight models). No training required. For a narrow, repeatable task like this, a well-written prompt with few-shot examples should get very close to full performance.
2. **Fine-tuning a small open-weight model** — worth doing *later*, not now. Only pays off once there's a meaningfully sized labeled dataset of real transcript→ideal-rephrase pairs (hundreds to low-thousands), and its main benefit at that point is cost/latency (a small fine-tuned model matching a bigger prompted model), not quality unreachable by prompting.
3. **Building an LLM from scratch** — explicitly ruled out. Wrong scope entirely (would need enormous data/compute/time) for a narrow classification-like task.

### 4.3 Model shortlist under consideration

Do not default to Llama 3.2 3B just because it was the original plan in `AIDE.md` — the open-model ecosystem moves fast and this should be benchmarked, not assumed.

| Model family | Starting size | Why it's on the list |
|---|---|---|
| **Qwen3** | 4B / 8B | Excellent general-purpose candidate, strong instruction-following |
| **Gemma 4** | varies (E2B/E4B edge-optimized, larger server-scale variants) | Google DeepMind, strong small-model ecosystem |
| **Phi-4-mini** | ~mini-scale | Microsoft, very clean licensing, competitive reasoning for its size |
| **Ministral** | 3B / 8B | Mistral's efficient-inference line |
| **Llama 3.2** | 3B / 8B | Mature ecosystem, original plan, most tooling/community support |

**Also worth knowing:** `Qwen3-ASR` exists as an open-source ASR (speech recognition) project under Apache 2.0 with vLLM serving support — meaning it's plausible, longer-term, to bring *both* STT and the rephrasing LLM under fully self-hosted infrastructure rather than only the LLM half. Not an immediate priority given Section 3's STT service already works well, but worth knowing it's a realistic future direction if Google Cloud STT costs or data-residency concerns become more pressing.

### 4.4 Licensing — confirmed, not assumed

This was explicitly researched because AIDE plans to monetize and needed certainty that no chosen model blocks that.

**Key finding: none of the realistic candidate models restrict commercial use.** The original concern ("if we use Whisper, we can't monetize") was based on a mistaken premise — OpenAI's open-source Whisper is MIT-licensed, fully free for commercial use, no royalty or revenue-share. The same is true across the board for the models below:

| Model family | License | Commercial use? | Notes |
|---|---|---|---|
| **Qwen3** | Apache 2.0 | Yes, no restrictions | Cleanest option |
| **Gemma 4** (released Apr 2026) | Apache 2.0 | Yes, no restrictions | Older Gemma (1–3) used the custom "Gemma Terms of Use" — commercial use is *still* permitted there too, just with extra conditions (notice file, prohibited-use policy). Use Gemma 4+ for the cleanest terms. |
| **Phi-4 / Phi-4-mini** | MIT | Yes, no restrictions | As clean as Qwen |
| **Ministral 3B/8B** | Apache 2.0 | Yes, no restrictions | |
| **Llama 3.2 (3B)** | Llama Community License | Yes | Requires "Built with Llama" attribution; a separate license is only triggered above 700M monthly active users (irrelevant at AIDE's current stage) |
| **Whisper (OpenAI, open-source)** | MIT | Yes, no restrictions | Corrects the original mistaken assumption about monetization |

**General rule established for the team:** "It's on Hugging Face" does not automatically mean it's commercially usable — always check the *specific model's* license, not just the model family, since different checkpoints/variants in the same family can carry different terms (e.g. Gemma 1-3 vs Gemma 4).

There are **two separate legal questions** worth keeping distinct going forward:
1. Can we commercially use the model? — a licensing question (answered above).
2. Can we legally process patient information using this architecture? — a privacy/compliance question (Section 2.3), requiring actual legal/privacy professional review, not something the engineering choices alone resolve.

### 4.5 Architecture-within-architecture: don't route everything through the LLM

Proposed design — an intent classifier in front of the LLM, so simple/obvious requests skip the model call entirely:

```
                Transcript
                    │
                    ▼
             Intent classifier
                    │
          ┌─────────┴─────────┐
          │                   │
       obvious             ambiguous
          │                   │
          ▼                   ▼
      Rule/keyword          LLM
      classifier              │
          │                   │
          └─────────┬─────────┘
                    ▼
             Structured event
                    │
                    ▼
                  Redis
                    │
                    ▼
                Dashboard
```

Example: `"water please"` doesn't need a sophisticated LLM call — a keyword match suffices. But `"I've been sitting here for a while and my mouth is extremely dry. Is there any chance somebody could get me something to drink?"` needs the LLM. This reduces inference cost, latency, compute load, and failure surface. This was already directionally planned in `AIDE.md` ("hybrid keyword classifier to reduce model invocations") — this section formalizes the reasoning behind it.

### 4.6 Don't expose the model directly — service boundary design

```
Mobile/Web
    │
    ▼
AIDE Backend
    │
    │ authenticated request
    ▼
Inference Service       ← this is the boundary that enforces:
    │                       authentication, authorization, rate limiting,
    ▼                       input validation, logging, output validation,
   Qwen/etc.                timeout, retry, model selection, prompt
                             templates, data retention rules
```

Same principle as the STT service (Section 3.6) — the frontend should never call the inference engine (Ollama/vLLM) directly.

### 4.7 Datasets — what exists right now

Three CSV files, uploaded and inspected:

**`AIDE_100_general_dataset.csv`** — 100 rows, columns `transcript`, `expected_shortened`
- Clean requests, no PII in the transcript
- Transcript length: 3–10 words (avg 5.8)
- Label length: 2–5 words (avg 2.5), 84 unique labels out of 100 rows
- Labels are Title Case, end in a small vocabulary (*request*, *assistance*, *adjustment*), object-first phrasing ("Water request," not "Requesting water")

**`AIDE_100_personal_data_dataset.csv`** — 100 rows, same columns
- Same underlying requests, but with name/age woven into the transcript ("Hi, I'm Daniel and I'm 72 years old. Could you bring me some water?")
- Transcript length: 7–15 words (avg 10.3) — longer because of the injected personal details
- **Critically: every `expected_shortened` label strips the name and age entirely**, keeping only the request (e.g. same example → "Water request"). This is the de-identification behavior the rephrasing LLM must learn/be instructed to do.

**`AIDE_200_row_LLM_evaluation_dataset.csv`** — 200 rows, columns `dataset`, `transcript`, `expected_shortened`
- Combines both of the above: 100 rows tagged `dataset=general`, 100 rows tagged `dataset=personal_data_injected`
- Purpose-built for evaluation, not training — this is the scoring set

**Why the `personal_data_injected` split matters so much:** it's not just testing "can the model shorten text," it's testing "does the model strip PII while shortening." A model/prompt combination could score well on `general` and still leak names/ages on `personal_data_injected` — these need to be scored and reported **separately**, not blended into one aggregate accuracy number.

### 4.8 Draft system prompt (starting point, not final)

Built directly from patterns observed in the actual dataset:

```
You are a triage assistant for a hospital patient-request system.
Convert a patient's spoken request into a short staff-facing action item.

Rules:
1. Output 2-5 words, Title Case, no punctuation.
2. Never include the patient's name, age, or any other identifying detail,
   even if they stated it. Only the request matters.
3. End with a plain noun: "Request", "Assistance", or "Adjustment" where natural.
4. If multiple needs are mentioned, output only the most urgent one.
5. If the request is unclear or not a request, output: "Unclear request"

Examples:
"Can you bring me a glass of water please?" -> Water request
"Hi, I'm Daniel and I'm 72 years old. Could you bring me some water?" -> Water request
"I'm Michael, 61, and my lower back is hurting." -> Lower back pain assistance
"Could you lower the television volume?" -> Television volume adjustment
```

Recommendation: pull 6–10 real rows from the dataset as few-shot examples, deliberately mixing `general` and `personal_data_injected` rows so the model sees the PII-stripping behavior demonstrated directly, not just described in the rules.

### 4.9 Evaluation methodology (planned, not yet built)

Turn "prompt engineering" into a measurable, comparable process rather than eyeballing outputs:

1. Run every transcript in the 200-row eval set through a candidate prompt + model combination.
2. Score each output against `expected_shortened` two ways:
   - **Exact match** (strict string comparison)
   - **Fuzzy/semantic match** (e.g. "Water request" vs "Water assistance" should count as a near-miss, not a total failure — needs a defined similarity threshold or an LLM-as-judge approach)
3. **Break the score down by the `dataset` column, always.** A model can look great in aggregate while still leaking PII on the `personal_data_injected` split — that split must be scored and reported separately, never blended.
4. Track a distinct **PII-leak rate** metric — did the output contain a name, age, or other identifying detail that was present in the input transcript? This is arguably the most important metric for a healthcare product and should never be allowed to hide inside a general accuracy number.
5. Log every mismatch with input/expected/actual, so failures are diagnosable, not just a percentage.

This evaluation script does not exist yet as of this document — building it is a natural next step, and it should be reusable across any candidate model/prompt (Qwen3, Gemma 4, Phi-4-mini, current OpenRouter/Kimi setup, etc.) so results are directly comparable.

---

## 5. Competitive Landscape (Summary)

Full detail lives in separate deliverables already produced (`AIDE-Competitor-Comparison.docx/pdf`, `AIDE-Competitive-Landscape-Aug2026.md`) — this section is a condensed pointer for context, not the full analysis.

**The four-part functional loop (Section 1) is the test used to separate real competitors from category-adjacent companies.** Many companies sit inside the broad "AI voice in healthcare" category without doing AIDE's specific thing.

**Functional/incumbent competitors (do some or most of the loop):**
- **Austco Healthcare** (Port Melbourne, VIC, ASX: AHC) — nurse call hardware incumbent, has discussed voice/AI roadmap for years but hasn't shipped a patient-facing voice product. Biggest "sleeping giant" risk given local presence and existing hospital relationships.
- **Rauland** (US-owned, deployed in AU hospitals) — the incumbent AIDE explicitly sits alongside, not inside.
- **TigerConnect** (US) — software-first clinical communication, AI orchestration, closest positioning match among larger incumbents.
- **Aiva Health** (Los Angeles) — the most mature global functional analog. 10,000+ rooms deployed across US/Canada, integrates with Rauland nurse call directly, recently added a voice interface over ChatGPT/Claude/Gemini Enterprise. Not in Australia. Requires Alexa hardware (unlike AIDE's no-hardware approach).

**Category-adjacent, NOT functional competitors (important distinction, established explicitly in this project's research):**
- **Hayylo** (Melbourne) — home care client/family communication platform, no ward, no bedside request capture.
- **Capyra / AI Mily** (Melbourne, nurse-founded) — solves interpreter/translation access, not request triage. Same accelerator ecosystem (MedTech Actuator) and narrative overlap, not product overlap.
- **Hippocratic AI** (Palo Alto) — general healthcare LLM platform doing outbound nurse-initiated calling, not inbound bedside capture. Extremely well-capitalised — worth watching for a future pivot, not a current threat.
- **CipherHealth** (New York) — broad multi-module care-coordination platform; captures needs via scheduled rounding, not always-on patient voice.
- **SONIFI Health** — in-room TV interface for requests, not voice-based.

---

## 6. Known Gaps, Risks, and Open Decisions

### 6.1 Security
- **HTTPS not yet enabled** on the STT VM — all traffic (including the API key) travels as plain HTTP. Needs a reverse proxy (Caddy or Nginx with Let's Encrypt) in front of Uvicorn before any real patient audio flows through this in production.
- **`default-allow-ssh` firewall rule is open to `0.0.0.0/0`** — not an active breach (OS Login still requires valid IAM permissions to authenticate) but makes the VM visible to automated internet-wide port-22 scanning. Consider restricting to known IPs or moving to GCP's Identity-Aware Proxy (IAP) for SSH before production.
- API key rotation process not yet defined.

### 6.2 Compliance / Privacy
- Self-hosting an LLM (Section 2.3) is necessary but not sufficient for compliance — needs actual legal/privacy review against the Australian Privacy Act 1988, Victorian Health Records Act 2001, and any other applicable regulation, before claiming compliance anywhere (pitch materials, hospital conversations, etc.).
- Raw STT transcripts (Section 3.3) contain PII by design — every consumer of that endpoint's output needs to treat it as sensitive.

### 6.3 Data residency
- The STT VM is hosted in **`us-central1-a`** — physically in the United States. AIDE's privacy/compliance story is built around Australian regulation (Privacy Act, Health Records Act) and an architectural goal of keeping patient data "under our own infrastructure." Whether "under our own infrastructure" also needs to mean "within Australia" for that story to hold up is an open question for Noah and likely legal counsel — not a decision to make unilaterally at the infrastructure level, but important enough to flag before this becomes harder to migrate later.

### 6.4 Scaling
- Single VM, no autoscaling, no queue system yet — concurrency capped at 10 simultaneous STT requests (queues rather than fails beyond that). Fine for pilot-stage testing; will need load-testing (10 → 25 → 50 → 100 concurrent) to determine whether a queue system or larger/multiple VMs are needed before any real pilot deployment.

### 6.5 Rephrasing pipeline — everything in Section 4 is design work, not implementation
As of this document, the rephrasing/LLM stage is **not yet built**. What exists: a model shortlist with confirmed licensing, an architecture direction (self-hosted via Ollama initially), a draft prompt, three labeled datasets, and a defined (but not yet coded) evaluation methodology. Next concrete step: build the evaluation script (Section 4.9) and run the draft prompt (Section 4.8) against at least 2–3 candidate models to get real, comparable numbers before committing to one model/approach.

### 6.6 Immediate next steps (as of this document)
1. Build and run the evaluation script against the 200-row dataset for the current OpenRouter/Kimi setup (establish a baseline) and at least one self-hosted candidate (e.g. Qwen3 8B via Ollama).
2. Fill in the real STT VM external IP anywhere it's still a placeholder in developer-facing docs.
3. Address the HTTPS gap before any real (non-test) patient audio is sent through the STT endpoint.
4. Resolve the US-hosted-VM data residency question with Noah before it's harder to migrate.
5. Decide on and implement the intent-classifier-plus-LLM-fallback design (Section 4.5) once a model is chosen, to control inference cost/latency.

---

## 7. Glossary / Conventions for anyone (human or AI) working on this project

- **"The four-part loop"** — shorthand for AIDE's actual functional definition (Section 1). Use this as the test for whether something is a real competitor or feature gap, not the vaguer "AI voice in healthcare" category.
- **STT** = Speech-to-Text (Section 3, built). **Rephrasing/LLM stage** = the shortening step (Section 4, not yet built). These are always discussed as separate, swappable components — avoid conflating them.
- Content/communication style for anything AIDE-facing: short sentences, plain language, no em-dashes, every claim cited, no fabricated statistics or quotes.
- When in doubt about product/business/regulatory facts not covered here, defer to `AIDE.md` or explicitly flag the gap rather than guessing — this mirrors the instruction already embedded in `AIDE.md` itself ("if a question is not covered here, respond with 'I don't have confirmed information on that — check with Noah' rather than guessing").
