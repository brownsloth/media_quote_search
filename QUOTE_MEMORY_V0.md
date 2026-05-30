# Quote Memory v0 — Product & Implementation Spec

**Working name:** Quote Memory / Scene Recall  
**One-liner:** Shazam for half-remembered movie quotes — fuzzy text in, movie + scene context out.  
**Status:** v0 spec (no video, no clip hosting)

---

## 1. Problem & wedge

People remember fragments: wrong words, partial lines, a vibe, an actor, a decade — not exact subtitles.

Existing tools (Yarn, PlayPhrase) optimize for **exact or near-exact quote → clip**. This product optimizes for **imperfect human memory → candidate match + confidence**.

| They do | We do |
|---------|-------|
| Exact phrase search | Paraphrase, partial, misremembered wording |
| Clip playback first | Memory resolution first; link out later |
| Large catalog, search UX | Semantic recall + “was this it?” UX |

**v0 promise (manage carefully):**  
> “I half-remember a line from a movie — help me figure out what it’s from.”

**Not v0:**  
> “That scene where the car flips” / “Christian Bale driving fast” / hosted video playback.

---

## 2. v0 scope

### In scope

- Text query only (single input box + optional filters)
- English subtitles for **100 curated movies** (expand later)
- Fuzzy / paraphrased / partial quote matching
- Top 5 results with:
  - Movie title, year
  - Timestamp (start)
  - Matching subtitle line
  - ±3–5 line context window
  - Confidence band (High / Medium / Low)
- Subtitle-only retrieval (no plot summaries, no video embeddings in v0)
- Local or cloud API + simple web UI
- Hand-built eval set (80+ queries)

### Out of scope (v0)

- Video hosting or in-app clip playback
- TV shows (optional stretch; film-only keeps scope tight)
- Multimodal search (visual scenes, “vibe”, actor action)
- Plot-summary / metadata-only search
- User accounts, history sync, social features
- Mobile apps
- Commercial-scale subtitle scraping (demo/portfolio scale only until licensing is clear)

### Success criteria (v0)

| Metric | Target |
|--------|--------|
| Recall@1 on hand-built **exact** quotes (famous lines) | ≥ 85% |
| Recall@5 on **paraphrase** queries | ≥ 70% |
| Recall@5 on **partial / wrong-word** queries | ≥ 50% |
| P95 latency (CPU, 100-movie index) | < 500 ms |
| User trust | Top result clearly labeled when confidence is low |

If paraphrase recall@5 is below 50%, add reranker before expanding catalog.

---

## 3. System architecture

```
┌─────────────┐     ┌──────────────┐     ┌─────────────────┐
│  Web UI     │────▶│  Query API   │────▶│  Vector index   │
│  (Netlify)  │     │  (FastAPI)   │     │  (FAISS/Chroma) │
└─────────────┘     └──────┬───────┘     └────────▲────────┘
                           │                        │
                           │                 ┌──────┴──────┐
                           ▼                 │  Embeddings │
                    ┌──────────────┐         │  (built     │
                    │  Reranker    │         │   offline)  │
                    │  (cross-enc) │         └──────▲────────┘
                    └──────────────┘                │
                                                    │
                           ┌────────────────────────┘
                           │
                    ┌──────▼───────┐
                    │  SQLite /    │
                    │  JSON store  │
                    │  (chunks +   │
                    │   metadata)  │
                    └──────────────┘
```

**Offline pipeline (run once, re-run on catalog updates):**

```
subtitle files → parse → normalize → chunk → embed → index + DB
```

**Online path:**

```
user query → normalize → embed → ANN top-50 → rerank → top-5 → confidence → JSON
```

---

## 4. Data layer

### 4.1 Source

Start with **100 manually verified films**:

- Prefer one canonical English subtitle per film (best-rated fan sub or official where available)
- Sources: OpenSubtitles dumps, Kaggle subtitle datasets, personal collection
- **Do not** auto-scrape 10k films for v0 — quality beats quantity

Maintain a **curated manifest** (`films.csv`):

| field | example |
|-------|---------|
| `film_id` | `tt0468569` (IMDB) or TMDB id |
| `title` | The Dark Knight |
| `year` | 2008 |
| `subtitle_path` | `subs/the_dark_knight_2008.srt` |
| `subtitle_source` | opensubtitles / manual |
| `verified` | true |

### 4.2 Subtitle parsing

Support **SRT** first; add ASS/VTT if needed.

Extract per cue:

| field | description |
|-------|-------------|
| `cue_id` | stable id within film |
| `start_ms` | cue start timestamp |
| `end_ms` | cue end timestamp |
| `text` | cleaned dialogue line |
| `speaker` | parsed if format allows (`NAME:` prefix) |

**Normalize text:**

- Lowercase
- Strip HTML tags, `{\\an8}` ASS junk
- Remove `[music]`, `(gasps)`, `♪`, speaker prefixes for embedding (keep original for display)
- Collapse whitespace
- Optional: expand contractions for embedding only (`don't` → `do not`) — test both

### 4.3 Chunking strategy

**Unit of retrieval:** one subtitle cue + context window.

For cue at index `i`:

```
context_before = cues[i-5 : i]   # up to 5 lines
target_line    = cues[i]
context_after  = cues[i+1 : i+6] # up to 5 lines
```

Store two text fields:

| field | used for |
|-------|----------|
| `text_line` | display — the matched cue |
| `text_embed` | embedding — `"\n".join(context_before + [target] + context_after)` trimmed |

Also store `context_display` (original casing) for UI.

**Why context matters:** Famous quotes often span cues or need neighboring lines for semantic match.

**Edge cases:**

- Overlapping chunks: each cue is its own chunk (expect redundancy in index — fine for v0)
- Very short cues (`"No."`, `"Yeah."`): rely on context window; downweight in reranker if line length < 4 tokens
- Duplicate identical lines in same film: keep all; timestamp disambiguates in UI

### 4.4 Expected scale (100 films)

| estimate | value |
|----------|-------|
| Avg cues per film | ~800–1,500 |
| Total chunks | ~100k–150k |
| Embedding dim (MiniLM) | 384 |
| Raw index size (FAISS float32) | ~150k × 384 × 4 ≈ 230 MB |
| With metadata DB | < 500 MB total |

Fits comfortably on a laptop or small Railway instance.

---

## 5. Metadata layer

Even v0 should store rich metadata per chunk for filtering and display.

### 5.1 Per-chunk record

```json
{
  "chunk_id": "tt0468569_004821",
  "film_id": "tt0468569",
  "title": "The Dark Knight",
  "year": 2008,
  "genres": ["Action", "Crime", "Drama"],
  "director": "Christopher Nolan",
  "cast_top": ["Christian Bale", "Heath Ledger", "Michael Caine"],
  "start_ms": 7234000,
  "end_ms": 7238000,
  "timestamp_display": "2:00:34",
  "speaker": "Alfred",
  "text_line": "Some men just want to watch the world burn.",
  "context_display": "...",
  "text_embed": "...",
  "embedding_id": 4821
}
```

### 5.2 Film-level metadata (TMDB / OMDb)

Fetch once per film at ingest:

- Title, year, IMDB/TMDB id
- Genres, director, top 5 cast
- Optional: `imdb_url`, `tmdb_url` for outbound links

**Do not embed plot summaries in v0** — store for v0.5.

### 5.3 Speaker parsing (best-effort)

Heuristics on subtitle text:

- `ALFRED:` / `- Alfred -` / `[Alfred]` → `speaker` field
- Expect ~40–60% accuracy across random subs; OK for display, not for hard filters in v0

### 5.4 Optional query filters (v0)

| filter | implementation |
|--------|----------------|
| Year range | SQL pre-filter on `year` before ANN |
| Genre | SQL / metadata filter |
| Actor hint (free text) | post-filter: boost if name in `cast_top` or fuzzy match cast list |
| “Nolan film” | director field match |

Filters reduce candidate set before or after ANN — start with **post-ANN boost** (simpler).

---

## 6. Embedding model

### 6.1 Primary: bi-encoder (index + query)

**Model:** `sentence-transformers/all-MiniLM-L6-v2`

| property | value |
|----------|-------|
| Dim | 384 |
| Speed | ~1000+ sentences/sec on CPU batch |
| Quality | Strong for paraphrase within same language |
| Size | ~80 MB |

**Alternatives if recall is weak:**

| model | tradeoff |
|-------|----------|
| `all-mpnet-base-v2` | Better quality, 2–3× slower, 768-dim |
| `BAAI/bge-small-en-v1.5` | Strong retrieval baseline, similar size |

**v0 decision:** MiniLM unless eval fails paraphrase target.

### 6.2 What gets embedded

- **Index:** `text_embed` (line + context window, normalized)
- **Query:** user input, same normalization pipeline

**Do not** embed film title into every chunk for v0 — adds noise. Use metadata filters/boosts instead.

### 6.3 Index: FAISS vs Chroma

| option | v0 recommendation |
|--------|-------------------|
| **FAISS** (IndexFlatIP or HNSW) | Best if you want minimal deps, full control, 100k vectors |
| **Chroma** | Easier persistence + metadata filtering in one store |
| **LanceDB** | Good if you expect to grow fast |

**v0 pick:** FAISS `IndexFlatIP` on L2-normalized vectors (= cosine sim) — dead simple, 100k vectors is instant brute force.

At 150k × 384, brute-force search is <10 ms. HNSW unnecessary until ~1M+.

---

## 7. Reranker

ANN alone will miss paraphrases and tie on similar lines. **Rerank top-50 before returning top-5.**

### 7.1 Cross-encoder reranker

**Model:** `cross-encoder/ms-marco-MiniLM-L-6-v2`

- Input: `(user_query, candidate_text_embed)`
- Output: relevance score
- Run on ANN top-50 only → ~50–200 ms on CPU

### 7.2 Lexical fuzzy score (blend)

Compute alongside cross-encoder:

- Token overlap (Jaccard)
- Partial ratio (rapidfuzz / fuzzywuzzy)
- Longest common substring on significant tokens (drop stopwords)

**Combined score (v0):**

```
final = 0.55 * cross_encoder + 0.30 * fuzzy_partial + 0.15 * ann_cosine
```

Tune weights on eval set.

### 7.3 Why reranker matters for the wedge

| query | ANN alone | + reranker |
|-------|-----------|------------|
| "watch the world burn" | may hit generic “world” lines | pushes Alfred monologue up |
| "some men want world to burn" | scattered matches | cross-encoder aligns paraphrase |
| "batman butler fire quote" | weak | still weak — **expected v0 limit** |

---

## 8. Confidence scoring

Don't show a fake precise percentage. Use **score gap + calibrated bands**.

```
gap = score_rank1 - score_rank2
```

| band | rule (tune on eval) |
|------|---------------------|
| **High** | score₁ > 0.75 AND gap > 0.15 |
| **Medium** | score₁ > 0.55 OR gap > 0.08 |
| **Low** | otherwise — show “Not sure — here are close matches” |

Always show **top 5**, never single result without alternatives when band is Low.

Display:

```
The Dark Knight (2008) — High confidence
~2:00:34 — Alfred
"Some men just want to watch the world burn."
[context block]
```

---

## 9. Query API

### 9.1 Endpoints

| method | path | purpose |
|--------|------|---------|
| GET | `/health` | status, index size, model ids |
| POST | `/search` | main query |

### 9.2 Request

```json
{
  "query": "some men just want to watch the world burn",
  "top_k": 5,
  "filters": {
    "year_min": 2000,
    "year_max": 2010,
    "genre": "Action",
    "actor_hint": "Christian Bale"
  }
}
```

All filters optional.

### 9.3 Response

```json
{
  "query": "...",
  "confidence": "high",
  "latency_ms": 312,
  "results": [
    {
      "rank": 1,
      "score": 0.89,
      "film_id": "tt0468569",
      "title": "The Dark Knight",
      "year": 2008,
      "timestamp_ms": 7234000,
      "timestamp_display": "2:00:34",
      "speaker": "Alfred",
      "line": "Some men just want to watch the world burn.",
      "context": "..."
    }
  ]
}
```

### 9.4 Stack

Same pattern as Hindi Jinnie:

- **FastAPI** on Railway / local
- **Static UI** on Netlify / Gatsby
- Models loaded at startup (embedder + cross-encoder + FAISS index)
- `CORS_ORIGINS` for frontend domains

**Memory estimate (loaded):**

| component | RAM |
|-----------|-----|
| MiniLM bi-encoder | ~150 MB |
| Cross-encoder | ~150 MB |
| FAISS index | ~250 MB |
| Python overhead | ~200 MB |
| **Total** | ~750 MB–1 GB |

Fits Railway hobby tier.

---

## 10. Web UI (v0)

Minimal — one screen:

1. Large text input: “What do you remember?”
2. Optional collapsible filters (year, genre, actor hint)
3. Submit → loading state
4. Results list (5 cards):
   - Title + year + confidence badge
   - Timestamp + speaker
   - Highlighted matching line
   - Context (gray, smaller)
   - Optional: “Not this one” button (logs for future eval — no ML in v0)

**Copy for expectation setting (below input):**

> Works best with partial quotes or lines you half-remember. Won’t find scenes by visual description yet.

---

## 11. Offline ingest pipeline

### 11.1 Scripts (planned)

```
scripts/
  ingest/
    parse_srt.py          # SRT → cues JSONL
    fetch_tmdb_metadata.py
    build_chunks.py       # cues → chunks
    embed_chunks.py       # chunks → vectors
    build_index.py        # vectors → FAISS + chunk_id map
    run_ingest.sh         # orchestrate all steps
```

### 11.2 Artifacts

```
data/
  manifest/films.csv
  raw/subs/*.srt
  processed/cues/*.jsonl
  processed/chunks.jsonl
  index/faiss.index
  index/chunk_id_map.json
  index/metadata.sqlite
```

### 11.3 Rebuild policy

Full rebuild for v0 (100 films, minutes). Incremental ingest when catalog grows.

---

## 12. Evaluation harness

**Most important v0 investment after data curation.**

### 12.1 Test set structure

Hand-write **80–120 queries** in categories:

| category | count | example |
|----------|-------|---------|
| Exact quote | 20 | `"I'll be back"` |
| Paraphrase | 25 | `"watch the world burn"` → Dark Knight |
| Wrong word | 20 | `"some men just wanna see the world burn"` |
| Partial | 15 | `"world burn"` |
| With hint | 10 | query + filter actor/year |
| Negative / obscure | 10 | should return low confidence |

Each query has:

```json
{
  "query_id": "q042",
  "query": "watch the world burn",
  "expected_film_id": "tt0468569",
  "expected_cue_contains": "world burn",
  "category": "paraphrase"
}
```

### 12.2 Metrics

| metric | definition |
|--------|------------|
| Recall@1 (film) | top result is correct film |
| Recall@5 (film) | correct film in top 5 |
| Recall@1 (cue) | top cue contains expected substring |
| MRR | mean reciprocal rank of first correct film |
| Confidence calibration | % of High band that is actually correct |

Run after any change to embedding, chunking, reranker weights, or catalog.

### 12.3 Regression gate

Before expanding beyond 100 films:

- Paraphrase recall@5 ≥ 70%
- Wrong-word recall@5 ≥ 50%

---

## 13. Known limitations (v0)

Be honest in product copy and your own head:

| limitation | why |
|--------------|-----|
| Subtitle ≠ screenplay | Ad-libs, alternate cuts missing |
| Same quote, multiple films | “I’ll be back”, “here’s looking at you” |
| Mis-synced subs | Timestamp wrong by seconds |
| Speaker attribution noisy | Parsed from inconsistent formats |
| Vibe / visual / plot queries fail | No plot index, no video |
| Obscure films | Won’t be in 100-film catalog |
| Non-English | Out of scope |

---

## 14. Legal & ethics (read before public launch)

| topic | guidance |
|-------|----------|
| Subtitle redistribution | OK for personal research; **check license** before commercial product |
| OpenSubtitles ToS | Scraping/redistribution may be restricted |
| TMDB / OMDb | Use API terms; attribute sources |
| Clip linking | Linking to YouTube timestamps ≠ hosting; still gray for copyrighted content |
| Portfolio demo | Generally lower risk; don’t host subtitle files publicly |

**v0 for portfolio:** keep subtitle data private; ship index + API only.

---

## 15. Implementation challenges (expect these)

| # | challenge | mitigation |
|---|-----------|------------|
| 1 | Subtitle quality variance | Curate 100 films manually; one sub per film |
| 2 | Same quote in multiple movies | Show top 5; confidence band; film disambiguation in UI |
| 3 | Chunk too short / too long | Fixed ±5 context; min token filter |
| 4 | Embedding fails on slang/ad-libs | Reranker + fuzzy blend |
| 5 | Eval is subjective | Fixed test set + film-level recall metrics |
| 6 | False high confidence | Score gap threshold; never hide alternatives |
| 7 | Actor/plot hints without subtitle mention | v0: metadata boost only; v0.5: plot index |
| 8 | Scale to 10k films | Batch embed pipeline, HNSW, managed vector DB |
| 9 | Cold start content | 100 films = demo; 1k+ = useful product |
| 10 | User expects video | Set expectations in UI; link out in v0.5 |

---

## 16. Build order (recommended)

### Day 1 — Data + index

1. Pick 20 films with famous quotes (sanity check)
2. Parse SRT → chunks → embed → FAISS
3. CLI query script (no API yet)
4. Hand-test 10 queries manually

### Day 2 — Retrieval quality

5. Add cross-encoder reranker + fuzzy blend
6. Tune weights on 30-query dev set
7. Expand to 100 films
8. Build full eval set (80+ queries)

### Day 3 — Ship

9. FastAPI `/search`
10. Minimal web UI
11. Deploy API (Railway) + UI (Netlify)
12. Write short eval report (recall@1, recall@5 by category)

**Do not** add plot summaries, CLIP, or video until eval gates pass.

---

## 17. v0.5 → v1 roadmap (after v0 works)

| version | addition |
|---------|----------|
| **v0.5** | Plot summary + character description index (TMDB overview, Wikipedia plot) |
| **v0.5** | LLM reranker pass (“which of these 5 chunks best matches what the user remembers?”) |
| **v0.5** | “Not this one” feedback → hard negatives |
| **v1** | YouTube timestamp deep links (no hosting) |
| **v1** | TV shows + episode granularity |
| **v1** | Expand to 1k–5k titles |
| **v2** | Scene captions / CLIP for visual memory queries |
| **v2** | “Vibe search” — embedding of user description against plot + scene text |

---

## 18. Repo layout (proposed)

```
quote-memory/                    # new top-level or sibling repo
  docs/
    QUOTE_MEMORY_V0.md           # this file
  data/
    manifest/films.csv
    raw/subs/
    processed/
    index/
  scripts/ingest/
  src/
    parse/
    embed/
    search/
    api/
  eval/
    queries.jsonl
    run_eval.py
  web/
    index.html
    app.js
  serving/
    Dockerfile
    requirements.txt
```

Can live in current monorepo under `quote_memory/` or as a fresh repo — **fresh repo recommended** if this becomes a standalone portfolio piece.

---

## 19. Tech stack summary

| layer | choice |
|-------|--------|
| Subtitle parse | `pysrt` or custom SRT parser |
| Metadata | TMDB API |
| Bi-encoder | `sentence-transformers/all-MiniLM-L6-v2` |
| Cross-encoder | `cross-encoder/ms-marco-MiniLM-L-6-v2` |
| Fuzzy match | `rapidfuzz` |
| Vector index | FAISS (IndexFlatIP, cosine via normalized vectors) |
| Metadata DB | SQLite |
| API | FastAPI + uvicorn |
| UI | Static HTML/JS (same as Hindi Jinnie) |
| Deploy | Railway (API) + Netlify (UI) |
| Eval | Custom JSONL + recall scripts |

---

## 20. Example walkthrough

**User input:**

> "something about watching the world burn"

**Pipeline:**

1. Normalize query
2. Embed with MiniLM → vector `q`
3. FAISS search → top 50 chunks (cosine sim)
4. Rerank 50 with cross-encoder(query, chunk_text)
5. Blend with fuzzy score on `"watch world burn"` vs chunk text
6. Top hit: *The Dark Knight*, 2:00:34, Alfred, full monologue context
7. Confidence: **High** (score 0.89, gap 0.22 to #2)
8. Return JSON → UI renders card

**User input (v0 failure case):**

> "nolan movie car chase tunnel"

Expected: low confidence, weak matches — **correct behavior** until plot/visual index exists.

---

## 21. Open questions (decide during build)

- [ ] Single repo vs sibling repo?
- [ ] 100 films — fixed list or genre-diverse?
- [ ] Include TV in v0.1 or stay film-only?
- [ ] Show IMDB links in results?
- [ ] Log anonymous queries for eval expansion?
- [ ] Open-source subtitle data in repo or index-only deploy?

---

## 22. References & competitors

| product | note |
|---------|------|
| [Yarn](https://yarn.co) | Quote → clip; exact search oriented |
| [PlayPhrase.me](https://www.playphrase.me) | Type quote, watch scenes |
| OpenSubtitles | Data source (check ToS) |
| TMDB | Film metadata API |

**Differentiation:** imperfect memory, confidence-aware results, semantic paraphrase — not clip player first.

---

*Last updated: 2026-05-26 — v0 spec, pre-implementation.*
