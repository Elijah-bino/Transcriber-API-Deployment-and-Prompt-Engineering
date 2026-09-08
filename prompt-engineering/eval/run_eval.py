"""Rephrasing-stage eval harness.

Runs one prompt against a list of models (NVIDIA NIM / Groq, OpenAI-compatible),
scores nothing here -- just captures raw output per row. Isolated per model
(no cross-model failover). Rate limited. Resumable: re-run and it continues
from the last completed row of each model.

Usage (from prompt-engineering/eval/):
  python run_eval.py --models models.txt --data ../data/eval_set_225.csv \
                     --prompt ../prompts/v1.txt --out ../results --rpm 40
  python run_eval.py ... --preflight-only        # just check which models answer
  python run_eval.py ... --limit 10              # smoke test on first 10 rows
  python run_eval.py ... --only groq             # run only one provider

After the run it calls score.py automatically.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import pathlib
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request

PROVIDERS = {
    "nvidia": {
        "base_url": "https://integrate.api.nvidia.com/v1",
        "key_env": "NVIDIA_API_KEY",
    },
    "groq": {
        "base_url": "https://api.groq.com/openai/v1",
        "key_env": "GROQ_API_KEY",
    },
    "ollama": {
        # local Ollama, OpenAI-compatible, no auth. override host with OLLAMA_BASE_URL
        "base_url": os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434/v1"),
        "key_env": None,
    },
}

MAX_TOKENS = 64           # plain instruct models
MAX_TOKENS_REASONING = 512  # models that emit hidden/parsed chain-of-thought first
MAX_RETRIES = 6
RAW_COLS = ["id", "dataset", "transcript", "expected", "output", "latency_ms", "error"]


# --------------------------------------------------------------------------- env

def load_env(pe_dir: pathlib.Path) -> dict[str, str]:
    env: dict[str, str] = {}
    envfile = pe_dir / ".env"
    if envfile.exists():
        for line in envfile.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip().strip('"').strip("'")
    return env


# ----------------------------------------------------------------------- http io

def _clean(text: str) -> str:
    text = (text or "").strip()
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.S | re.I).strip()
    text = re.sub(r"^<think>.*$", "", text, flags=re.S | re.I).strip()
    return text


def chat(base_url: str, api_key: str, model: str, system: str, user: str,
         max_tokens: int, extra: dict | None = None,
         provider: str = "") -> tuple[str | None, str | None]:
    """Return (output, error). One attempt, no retry."""

    # --- Ollama: native endpoint + JSON-schema constrained decoding.
    # think:false is unreliable across models (qwen3:4b ignores it), but a
    # grammar-constrained schema forces a short answer with no CoT leak.
    if provider == "ollama":
        root = base_url.rsplit("/v1", 1)[0]
        sys_json = system + '\n\nRespond as JSON: {"action_item": "<the item>"}'
        body = {
            "model": model,
            "messages": [{"role": "system", "content": sys_json},
                         {"role": "user", "content": user}],
            "think": False,
            "stream": False,
            "format": {
                "type": "object",
                "properties": {"action_item": {"type": "string", "maxLength": 60}},
                "required": ["action_item"],
            },
            "options": {"temperature": 0, "num_predict": max(max_tokens, 160)},
        }
        req = urllib.request.Request(
            f"{root}/api/chat", data=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json"}, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=180) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            raw = (data.get("message", {}) or {}).get("content", "") or ""
            try:
                return _clean(str(json.loads(raw).get("action_item", ""))), None
            except (json.JSONDecodeError, AttributeError):
                return _clean(raw), None
        except urllib.error.HTTPError as e:
            return None, f"HTTP {e.code} | {e.read().decode('utf-8', 'replace')[:300]}"
        except Exception as e:  # noqa: BLE001
            return None, f"{type(e).__name__}: {e}"

    # --- OpenAI-compatible (NIM / Groq) ---
    body = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": 0,
        "max_tokens": max_tokens,
    }
    if extra:
        body.update(extra)
    if "reasoning_effort" not in (extra or {}):
        body["stop"] = ["\n"]

    req = urllib.request.Request(
        f"{base_url}/chat/completions",
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            # Groq sits behind Cloudflare which 403s the default python-urllib UA
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) eval-harness/1.0",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=90) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        msg = data["choices"][0]["message"]
        text = _clean(msg.get("content") or "")
        if not text and msg.get("reasoning"):
            text = msg["reasoning"].strip().splitlines()[-1].strip()
        return text, None
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")[:300]
        retry_after = e.headers.get("Retry-After")
        return None, f"HTTP {e.code} | retry_after={retry_after} | {detail}"
    except Exception as e:  # noqa: BLE001
        return None, f"{type(e).__name__}: {e}"


def call_with_retry(base_url, api_key, model, system, user, max_tokens, extra,
                    provider=""):
    delay = 5.0
    for attempt in range(MAX_RETRIES):
        t0 = time.time()
        out, err = chat(base_url, api_key, model, system, user, max_tokens, extra,
                        provider)
        latency = int((time.time() - t0) * 1000)
        if err is None:
            return out, latency, None
        transient = ("HTTP 429" in err or "HTTP 5" in err
                     or "timed out" in err.lower() or "URLError" in err)
        if not transient or attempt == MAX_RETRIES - 1:
            return None, latency, err
        wait = delay
        if "retry_after=" in err:
            try:
                ra = err.split("retry_after=")[1].split(" ")[0]
                if ra and ra != "None":
                    wait = max(wait, float(ra))
            except (ValueError, IndexError):
                pass
        print(f"      transient ({err[:60]}...), retry {attempt + 1}/{MAX_RETRIES} in {wait:.0f}s")
        time.sleep(wait)
        delay = min(delay * 2, 120)
    return None, 0, "exhausted retries"


# --------------------------------------------------------------------------- run

def safe_name(provider: str, model: str) -> str:
    return f"{provider}__{model.replace('/', '_').replace(':', '_')}"


def is_reasoning(model: str) -> bool:
    m = model.lower()
    return any(k in m for k in ("gpt-oss", "reasoning", "thinking", "-r1", "nemotron-3"))


def model_extra(provider: str, model: str) -> dict:
    if "gpt-oss" in model.lower():
        # reasoning tokens land in a separate field; content stays clean
        return {"reasoning_effort": "low"}
    return {}


def model_max_tokens(model: str) -> int:
    return MAX_TOKENS_REASONING if is_reasoning(model) else MAX_TOKENS


def load_models(path: pathlib.Path, only: str | None) -> list[tuple[str, str]]:
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        line = line.split("#", 1)[0].strip()  # strip inline comments
        if not line or "," not in line:
            continue
        provider, model = (x.strip() for x in line.split(",", 1))
        if only and provider != only:
            continue
        out.append((provider, model))
    return out


def load_rows(path: pathlib.Path, limit: int | None) -> list[dict]:
    rows = list(csv.DictReader(open(path, newline="", encoding="utf-8")))
    return rows[:limit] if limit else rows


def done_ids(raw_path: pathlib.Path) -> set[str]:
    if not raw_path.exists():
        return set()
    return {r["id"] for r in csv.DictReader(open(raw_path, newline="", encoding="utf-8"))
            if r.get("output", "") != "" or r.get("error", "") != ""}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", default="models.txt")
    ap.add_argument("--data", required=True)
    ap.add_argument("--prompt", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--rpm", type=float, default=40.0)
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--only", default=None, help="run only this provider")
    ap.add_argument("--preflight-only", action="store_true")
    args = ap.parse_args()

    here = pathlib.Path(__file__).resolve().parent
    pe_dir = here.parent
    env = load_env(pe_dir)

    out_dir = pathlib.Path(args.out).resolve()
    (out_dir / "raw").mkdir(parents=True, exist_ok=True)

    models = load_models(here / args.models, args.only)
    rows = load_rows(pathlib.Path(args.data), args.limit)
    system_prompt = pathlib.Path(args.prompt).read_text(encoding="utf-8").strip()
    min_interval = 60.0 / args.rpm

    print(f"models: {len(models)} | rows: {len(rows)} | rpm: {args.rpm} "
          f"| prompt: {pathlib.Path(args.prompt).name}")

    # ---- preflight -------------------------------------------------------
    preflight_path = out_dir / "_preflight.csv"
    pf = []
    alive = []
    for provider, model in models:
        cfg = PROVIDERS[provider]
        key = env.get(cfg["key_env"], "") if cfg["key_env"] else "local"
        if not key:
            pf.append((provider, model, "NO_KEY", f"{cfg['key_env']} missing in .env"))
            continue
        out, err = chat(cfg["base_url"], key, model, "Reply with the word ok.",
                        "ping", model_max_tokens(model),
                        model_extra(provider, model), provider)
        if err is None:
            pf.append((provider, model, "OK", (out or "")[:40]))
            alive.append((provider, model))
        else:
            pf.append((provider, model, "DEAD", err[:200]))
        time.sleep(1.0)

    with open(preflight_path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["provider", "model", "status", "detail"])
        w.writerows(pf)
    print(f"\npreflight -> {preflight_path}")
    for p, m, s, d in pf:
        print(f"  [{s:4}] {p}/{m}   {d}")

    if args.preflight_only:
        return 0
    if not alive:
        print("\nno models passed preflight, nothing to run.")
        return 1

    # ---- main loop ------------------------------------------------------
    for provider, model in alive:
        cfg = PROVIDERS[provider]
        key = env[cfg["key_env"]] if cfg["key_env"] else "local"
        extra = model_extra(provider, model)
        mtok = model_max_tokens(model)
        raw_path = out_dir / "raw" / f"{safe_name(provider, model)}.csv"
        already = done_ids(raw_path)
        new_file = not raw_path.exists()

        todo = [r for r in rows if r["id"] not in already]
        print(f"\n=== {provider}/{model} ===  {len(already)} done, {len(todo)} to do")
        if not todo:
            continue

        with open(raw_path, "a", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            if new_file:
                w.writerow(RAW_COLS)
                f.flush()
            for i, r in enumerate(todo, 1):
                t_start = time.time()
                out, latency, err = call_with_retry(
                    cfg["base_url"], key, model, system_prompt,
                    r["transcript"], mtok, extra, provider)
                w.writerow([r["id"], r["dataset"], r["transcript"],
                            r["expected_shortened"], out or "", latency, err or ""])
                f.flush()
                if i % 25 == 0 or i == len(todo):
                    print(f"    {i}/{len(todo)}  last='{(out or err or '')[:50]}'")
                elapsed = time.time() - t_start
                if elapsed < min_interval:
                    time.sleep(min_interval - elapsed)

    # ---- score --------------------------------------------------------
    print("\nscoring...")
    subprocess.run([sys.executable, str(here / "score.py"),
                    "--data", args.data, "--out", args.out], check=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
