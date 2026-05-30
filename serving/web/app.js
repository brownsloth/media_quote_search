const input = document.getElementById("input");
const resultsEl = document.getElementById("results");
const statusEl = document.getElementById("status");

const API_URL = (window.QUOTE_MEMORY_API || "http://localhost:8000").replace(/\/$/, "");
const DEBOUNCE_MS = 500;

let timer = null;
let requestId = 0;

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
  const ep = r.episode_label || "?";
  const ts = `${r.timestamp_start} – ${r.timestamp_end}`;
  const note = r.guardrail_note
    ? `<span class="guardrail-note">${escapeHtml(r.guardrail_note)}</span>`
    : `<span class="guardrail-note"></span>`;

  return `
    <article class="card">
      <div class="card-header">
        <span class="rank">#${r.rank}</span>
        <span class="ep-badge">${escapeHtml(ep)}</span>
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
        <a class="netflix-btn netflix-btn--show"
           href="${escapeHtml(r.netflix_url)}" target="_blank" rel="noopener noreferrer"
           title="Open Archer on Netflix${r.episode_label ? " — find " + r.episode_label : ""}">
          ${NETFLIX_N}
          Netflix
        </a>
      </div>
    </article>
  `;
}

function showPlaceholder(text) {
  resultsEl.innerHTML = `<div class="card placeholder-card">${escapeHtml(text)}</div>`;
}

async function search(text) {
  const id = ++requestId;
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
