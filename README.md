# Quote Memory (Archer)

Fuzzy subtitle search — half-remember a line, get episode + timestamp + context.

## Quick start (local)

```bash
conda activate google_july6th
pip install -r requirements.txt

# Index must exist locally or on HF — see serving/README.md
bash serving/run_local.sh          # UI :8888, API :8000
# or
bash serving/run_api.sh            # API only :8001
```

## Repo layout

| Path | In git? | Notes |
|------|---------|--------|
| `src/quote_lib/` | yes | Search, parse, guardrails |
| `scripts/` | yes | Ingest, index build, eval |
| `serving/` | yes | FastAPI + static UI + Dockerfile |
| `eval/` | yes | Query sets (variants generated locally) |
| `data/index/` | **no** | ~170 MB — upload via `serving/package_artifacts.sh` → HF |
| `data/processed/*.jsonl` | **no** | Rebuild from ingest pipeline |
| `data/processed/stats/` | yes | Guardrail config for deploy |
| `data/netflix/` | yes | Show-page placeholder JSON |
| `29thMay/` | **no** | Raw SRT source (local only) |

## Deploy

See [serving/README.md](serving/README.md): Hugging Face (index) → Railway (API) → Netlify (UI via Gatsby `static/quote-memory/`).

## Secrets

Copy `.env.example` → `.env` for local Netflix fetch experiments (optional). Never commit `.env`.
