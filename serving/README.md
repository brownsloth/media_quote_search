# Quote Memory — deploy

Same split as Hindi Jinnie: **static UI (Netlify)** → **FastAPI (Railway)** → **index on Hugging Face**.

## Where embeddings live today

**No separate vector DB** (no FAISS server, Pinecone, etc.). The index is:

| File | Role |
|------|------|
| `embeddings.npy` | ~97 MB float32 matrix (65992 × 384) |
| `chunks.jsonl` | Metadata + `text_line` + context |
| `meta.json` | Model names, counts |

Search = **numpy dot-product** (brute-force ANN) + cross-encoder rerank in process memory. Fine for ~66k chunks on Railway CPU.

For deploy, upload this bundle to **Hugging Face Hub** (same pattern as translation weights):

```bash
bash serving/package_artifacts.sh
# → 1starun8-research/archer-quote-index
```

Railway Docker build runs `serving/download_artifacts.py` to pull it.

You do **not** need a hosted vector DB unless you grow to millions of chunks.

---

## 1. Upload index to Hugging Face

```bash
pip install huggingface_hub
huggingface-cli login
bash serving/package_artifacts.sh
```

Creates on Hub:

```
index/embeddings.npy
index/chunks.jsonl
index/meta.json
guardrail_config.json
netflix/archer_episodes.json   ← optional, from Shakti fetch
```

---

## 2. Railway (API)

- **New project** → Deploy from GitHub repo
- **Builder:** Dockerfile
- **Dockerfile path:** `serving/Dockerfile`
- **Root directory:** `/`

**Env vars:**

| Var | Value |
|-----|--------|
| `HF_ARTIFACTS_REPO` | `1starun8-research/archer-quote-index` |
| `HF_TOKEN` | (if repo private) |
| `CORS_ORIGINS` | `https://projects.tarun-ssharma.com,http://localhost:8000,http://localhost:8001` |
| `NETFLIX_ID` | Netflix cookie value (optional — refreshes episode links on deploy) |
| `SECURE_NETFLIX_ID` | Netflix cookie value (optional) |
| `PORT` | (Railway sets automatically) |

Health: `GET https://<app>.up.railway.app/health`

Search: `POST /search` `{ "query": "danger zone", "top_k": 5 }`

**Note:** First request after cold start loads sentence-transformers + cross-encoder (~30–60s). Consider Railway min instances = 1 if you want warmth.

If `NETFLIX_ID` + `SECURE_NETFLIX_ID` are set, the container **re-fetches episode watch IDs on each deploy** (startup hook). Update those env vars when cookies expire, then redeploy — no code change needed.

---

## 3. Netlify (UI)

Copy static assets into your Gatsby portfolio (same as Hindi Jinnie):

```bash
cp -r serving/web/* /Users/starun/myblogs/projects/static/quote-memory/
```

Local Gatsby URL: **http://localhost:8000/quote-memory/** (not `/projects/quote-memory`).

`gatsby develop` does not serve nested static HTML by default. This repo includes
`gatsby-node.ts` with dev middleware — **restart** `npm run develop` after pulling it.

Set production API URL:

```js
// static/quote-memory/config.js
window.QUOTE_MEMORY_API = "https://YOUR-RAILWAY-APP.up.railway.app";
```

Deploy Gatsby site → Netlify rebuilds.

CORS is configured on **Railway**, not Netlify.

---

## 4. Local dev

**API only** (from repo root — use with Gatsby on :8000):

```bash
conda activate google_july6th
bash serving/run_api.sh          # default PORT=8001
# health: http://127.0.0.1:8001/health
```

**API + bundled UI** (all-in-one):

```bash
conda activate google_july6th
bash serving/run_local.sh
# UI http://localhost:8888  API http://localhost:8000
```

Uses `data/index/archer_full` by default. See `.env.example` for all env vars.

---

## Netflix episode links

Netflix URLs use **opaque video IDs**, not S/E numbers:

```
https://www.netflix.com/watch/{VIDEO_ID}   ← per episode
https://www.netflix.com/title/70171942     ← show page fallback
```

We do **not** put `?season=` in URLs (that was wrong). Instead:

1. Run Shakti fetch once (logged-in cookie) — [oldgalileo/shakti](https://github.com/oldgalileo/shakti):

```bash
export NETFLIX_ID='...'              # cookie value from DevTools
export SECURE_NETFLIX_ID='...'
bash scripts/data/run_fetch_netflix.sh
# → data/netflix/archer_episodes.json
```

2. Include in HF upload:

```bash
bash serving/package_artifacts.sh   # copies netflix/archer_episodes.json
```

3. API returns:
   - `netflix_link_type: "episode"` + `/watch/{id}` when mapped
   - `netflix_link_type: "show"` + `/title/70171942` otherwise

UI button says **Watch** vs **Netflix** accordingly. Timestamp seek is not supported by Netflix URLs.

---

## Scores FAQ

**Why negative scores?** Cross-encoder outputs raw logits (often −10…+10), not 0–1 probabilities. Final score = CE + fuzzy guardrail boosts/penalties. A line can have **high fuzzy match** but **negative CE** if the ±5 context window doesn’t align with the query — rank order matters more than the absolute number.

UI shows both `score` (final) and `ce` (cross-encoder) on hover via the score pill.
