const input = document.getElementById("input");
const resultsEl = document.getElementById("results");
const statusEl = document.getElementById("status");
const subtitleEl = document.getElementById("subtitle");

const API_URL = (window.QUOTE_MEMORY_API || "http://localhost:8000").replace(/\/$/, "");
const DEBOUNCE_MS = 500;
const DEFAULT_SHOWS = "Archer · Friends · The Office · Game of Thrones · Breaking Bad";

let timer = null;
let requestId = 0;
let lastQuery = "";

const NETFLIX_N = `<svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M5.398 0v24L12 20.1 18.602 24V0H5.398z"/></svg>`;

function setStatus(text, { error = false } = {}) {
  statusEl.hidden = !text;
  statusEl.classList.toggle("error", error);
  statusEl.textContent = text || "";
}

function escapeHtml(s) {
  return String(s)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function renderContext(before, target, after) {
  const parts = [];
  for (const line of before || []) {
    parts.push(`<p class="ctx-line">${escapeHtml(line)}</p>`);
  }
  parts.push(`<p class="ctx-target">${escapeHtml(target)}</p>`);
  for (const line of after || []) {
    parts.push(`<p class="ctx-line">${escapeHtml(line)}</p>`);
  }
  return parts.join("");
}

function renderCard(r) {
  const show = r.show_title ? escapeHtml(r.show_title) : "";
  const ep = r.episode_label || "?";
  const badge = show ? `${show} · ${escapeHtml(ep)}` : escapeHtml(ep);
  const ts = `${r.timestamp_start} – ${r.timestamp_end}`;
  const note = r.guardrail_note
    ? `<span class="guardrail-note">${escapeHtml(r.guardrail_note)}</span>`
    : `<span class="guardrail-note"></span>`;
  const netflixTitle = show
    ? `Open ${show} on Netflix${r.episode_label ? " — find " + r.episode_label : ""}`
    : `Open on Netflix${r.episode_label ? " — find " + r.episode_label : ""}`;

  return `
    <article class="card" data-chunk-id="${escapeHtml(r.chunk_id)}" data-rank="${r.rank}">
      <div class="card-header">
        <span class="rank">#${r.rank}</span>
        <span class="ep-badge">${badge}</span>
        <span class="timestamp">${escapeHtml(ts)}</span>
        <span class="confidence ${r.confidence}">${r.confidence}</span>
        <span class="score-pill" title="Final = cross-encoder + guardrail (CE can be negative)">
          score ${r.score} · ce ${r.ce_score}
        </span>
      </div>
      <div class="context">
        ${renderContext(r.context_before, r.text_line, r.context_after)}
      </div>
      <div class="card-footer">
        ${note}
        <div class="card-actions">
          <div class="feedback" aria-label="Was this match helpful?">
            <button type="button" class="feedback-btn" data-vote="up" title="Good match">👍</button>
            <button type="button" class="feedback-btn" data-vote="down" title="Bad match">👎</button>
            <span class="feedback-msg" hidden></span>
          </div>
          <a class="netflix-btn netflix-btn--show"
             href="${escapeHtml(r.netflix_url)}" target="_blank" rel="noopener noreferrer"
             title="${escapeHtml(netflixTitle)}">
            ${NETFLIX_N}
            Netflix
          </a>
        </div>
      </div>
    </article>
  `;
}

function showPlaceholder(text) {
  resultsEl.innerHTML = `<div class="card placeholder-card">${escapeHtml(text)}</div>`;
}

async function sendFeedback(card, vote) {
  const chunkId = card.dataset.chunkId;
  const rank = Number(card.dataset.rank);
  const result = card.__result;
  if (!chunkId || !lastQuery) return;

  const msg = card.querySelector(".feedback-msg");
  const buttons = card.querySelectorAll(".feedback-btn");

  buttons.forEach((btn) => {
    btn.disabled = true;
    btn.classList.toggle("selected", btn.dataset.vote === vote);
  });

  try {
    const res = await fetch(`${API_URL}/feedback`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        query: lastQuery,
        chunk_id: chunkId,
        vote,
        rank,
        show_id: result?.show_id ?? null,
        show_title: result?.show_title ?? null,
        episode_label: result?.episode_label ?? null,
      }),
    });
    if (!res.ok) throw new Error(await res.text());
    if (msg) {
      msg.hidden = false;
      msg.textContent = "Thanks!";
    }
  } catch (e) {
    buttons.forEach((btn) => {
      btn.disabled = false;
      btn.classList.remove("selected");
    });
    if (msg) {
      msg.hidden = false;
      msg.textContent = "Could not save";
    }
    console.error(e);
  }
}

function bindFeedbackHandlers(results) {
  resultsEl.querySelectorAll(".card[data-chunk-id]").forEach((card, i) => {
    card.__result = results[i];
    card.querySelectorAll(".feedback-btn").forEach((btn) => {
      btn.addEventListener("click", () => sendFeedback(card, btn.dataset.vote));
    });
  });
}

async function loadShowsSubtitle() {
  if (!subtitleEl) return;
  try {
    const res = await fetch(`${API_URL}/health`);
    if (!res.ok) return;
    const data = await res.json();
    const titles = (data.shows || []).map((s) => s.title).filter(Boolean);
    if (titles.length) {
      subtitleEl.textContent = `Fuzzy subtitle search · ${titles.join(" · ")}`;
    } else {
      subtitleEl.textContent = `Fuzzy subtitle search · ${DEFAULT_SHOWS}`;
    }
  } catch {
    subtitleEl.textContent = `Fuzzy subtitle search · ${DEFAULT_SHOWS}`;
  }
}

async function search(text) {
  const id = ++requestId;
  lastQuery = text;
  setStatus("Searching…");
  showPlaceholder("….searching….");

  try {
    const res = await fetch(`${API_URL}/search`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ query: text, top_k: 5 }),
    });

    if (id !== requestId) return;

    if (!res.ok) {
      const err = await res.text();
      throw new Error(err || `HTTP ${res.status}`);
    }

    const data = await res.json();
    if (!data.results?.length) {
      showPlaceholder("No matches — try a shorter phrase or different wording.");
      setStatus(`No results · ${data.latency_ms} ms`);
      return;
    }

    resultsEl.innerHTML = data.results.map(renderCard).join("");
    bindFeedbackHandlers(data.results);
    setStatus(
      `${data.results.length} matches · ${data.lexical_mode} guardrails · ${data.latency_ms} ms`
    );
  } catch (e) {
    if (id !== requestId) return;
    showPlaceholder("Could not reach Quote Memory. Is the API running?");
    setStatus("API unreachable — check config.js", { error: true });
    console.error(e);
  }
}

input.addEventListener("input", () => {
  clearTimeout(timer);
  const text = input.value.trim();
  if (!text) {
    requestId++;
    lastQuery = "";
    resultsEl.innerHTML = "";
    setStatus("");
    showPlaceholder("Type a half-remembered quote…");
    return;
  }
  timer = setTimeout(() => search(text), DEBOUNCE_MS);
});

input.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    clearTimeout(timer);
    const text = input.value.trim();
    if (text) search(text);
  }
});

showPlaceholder("Type a half-remembered quote…");
loadShowsSubtitle();
