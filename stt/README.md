# Transcription API

FastAPI microservice: audio in → raw transcript out, via **Google Cloud
Speech-to-Text v2** (`en-AU`, `long` model). First stage of the pipeline — no
rephrasing or de-identification happens here.

- `main.py` — the deployed service
- `fastapi_stt.py` — an earlier draft (v1 API, no auth), superseded by `main.py`
- `STT-API-Documentation.pdf` — full API reference
- `test_audio.mp3` / `.webm` — test fixtures
- `env_variables.txt` — **local only, gitignored** — holds the VM IP and API key

## Endpoints

| method | path | auth | notes |
|---|---|---|---|
| `GET` | `/` | none | health check → `{"status":"ok","service":"AIDE Speech-to-Text API"}` |
| `POST` | `/transcribe` | `X-API-Key` header | `multipart/form-data`, single field `file` |

`POST /transcribe` → `200 {"filename": "...", "text": "<raw transcript>"}`

| code | meaning |
|---|---|
| `400` | empty / unreadable audio |
| `401` | missing or invalid API key |
| `413` | file > 25 MB, or audio > 5 min |
| `415` | unsupported format / non-audio MIME |
| `500` | unexpected failure — internals logged server-side only |

**Formats:** `.wav .mp3 .flac .ogg .m4a .webm`
**Limits:** 25 MB · 5 min (via `ffprobe`) · 10 concurrent (excess queues, doesn't fail)

> ⚠️ The `text` field is a **raw** transcript — it can contain names, room numbers,
> and medical detail. Do not log, cache or persist it. De-identification is the
> rephrasing stage's job.

## Run locally

```bash
python -m venv venv && source venv/bin/activate
pip install fastapi "uvicorn[standard]" google-cloud-speech
export AIDE_GCP_PROJECT_ID=<your-gcp-project>
export AIDE_STT_API_KEY=$(openssl rand -hex 32)
# needs Application Default Credentials with the Cloud Speech Client role
uvicorn main:app --host 0.0.0.0 --port 8000
```

`ffprobe` (from ffmpeg) must be on `PATH` for the duration check.

## Deployment (current)

GCP VM (`e2-medium`, Ubuntu 24.04), systemd unit `aide-stt.service`, env from
`/etc/aide-stt.env` (root, `chmod 600`), Uvicorn on `:8000`. The VM's service
account has the `Cloud Speech Client` role, so no key file is needed.

**Open items:** HTTPS is not enabled (traffic is plain HTTP); SSH is open to
`0.0.0.0/0`; the VM is in a US region. See `../CLAUDE.md` §5.

## Client integration

Never call `/transcribe` from the browser — proxy it server-side so the API key
stays off the client and there is one place to forward the transcript to the
rephrasing service. See `../CLAUDE.md` §2.6.
