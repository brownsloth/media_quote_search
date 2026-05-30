"""FastAPI quote search server."""

from __future__ import annotations

import os
import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from search_service import QuoteSearchService

search_service: QuoteSearchService | None = None
_load_lock = threading.Lock()
_load_error: str | None = None


def _get_or_load_service() -> QuoteSearchService:
    global search_service, _load_error
    if search_service is not None:
        return search_service
    if _load_error is not None:
        raise RuntimeError(_load_error)
    with _load_lock:
        if search_service is not None:
            return search_service
        if _load_error is not None:
            raise RuntimeError(_load_error)
        try:
            print("Loading index and models (first request may take 30–60s) ...", flush=True)
            search_service = QuoteSearchService()
            print("Index ready.", flush=True)
            return search_service
        except Exception as e:
            _load_error = str(e)
            raise


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # Bind HTTP immediately; load heavy index on first /health or /search.
    yield


app = FastAPI(title="Quote Memory API", version="0.1.0", lifespan=lifespan)

DEFAULT_CORS_ORIGINS = ",".join(
    [
        "https://projects.tarun-ssharma.com",
        "http://localhost:8888",
        "http://127.0.0.1:8888",
        "http://localhost:8000",
        "http://127.0.0.1:8000",
        "http://localhost:8001",
        "http://127.0.0.1:8001",
    ]
)

origins = os.environ.get("CORS_ORIGINS", DEFAULT_CORS_ORIGINS).split(",")
allowed_origins = [o.strip() for o in origins if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class SearchRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=500)
    top_k: int = Field(default=5, ge=1, le=10)


class SearchResponse(BaseModel):
    query: str
    lexical_mode: str
    latency_ms: int
    results: list[dict]


@app.get("/health")
def health():
    if _load_error:
        return {"status": "error", "error": _load_error, "cors_origins": allowed_origins}
    if search_service is None:
        return {"status": "starting", "cors_origins": allowed_origins}
    info = search_service.health()
    return {"status": "ok", "cors_origins": allowed_origins, **info}


@app.post("/search", response_model=SearchResponse)
def search(body: SearchRequest):
    try:
        svc = _get_or_load_service()
    except RuntimeError as e:
        raise HTTPException(503, str(e)) from e
    try:
        payload = svc.search(body.query, top_k=body.top_k)
    except Exception as e:
        raise HTTPException(500, str(e)) from e
    return SearchResponse(**payload)
