"""FastAPI quote search server."""

from __future__ import annotations

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from search_service import QuoteSearchService

search_service: QuoteSearchService | None = None


@asynccontextmanager
async def lifespan(_app: FastAPI):
    global search_service
    search_service = QuoteSearchService()
    yield


app = FastAPI(title="Quote Memory API", version="0.1.0", lifespan=lifespan)

DEFAULT_CORS_ORIGINS = ",".join(
    [
        "https://projects.tarun-ssharma.com",
        "http://localhost:8888",
        "http://127.0.0.1:8888",
        "http://localhost:8000",
        "http://127.0.0.1:8000",
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
    if search_service is None:
        return {"status": "starting", "cors_origins": allowed_origins}
    info = search_service.health()
    return {"status": "ok", "cors_origins": allowed_origins, **info}


@app.post("/search", response_model=SearchResponse)
def search(body: SearchRequest):
    if search_service is None:
        raise HTTPException(503, "Index not loaded")
    try:
        payload = search_service.search(body.query, top_k=body.top_k)
    except Exception as e:
        raise HTTPException(500, str(e)) from e
    return SearchResponse(**payload)
