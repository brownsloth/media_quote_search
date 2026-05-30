/**
 * Fetch Archer SxxExx → Netflix watch IDs using YOUR logged-in browser session.
 *
 * How to use:
 *   1. Log into https://www.netflix.com in Chrome
 *   2. Open DevTools → Console (any netflix.com tab)
 *   3. Paste this entire file, press Enter
 *   4. Downloads archer_episodes.json
 *   5. Import: python scripts/data/import_netflix_mapping.py ~/Downloads/archer_episodes.json
 */
(async () => {
  const SHOW_ID = "70171942";
  const MAX_SEASONS = 20;
  const MAX_EPISODES = 35;

  const build =
    netflix?.appContext?.state?.model?.models?.serverDefs?.data?.BUILD_IDENTIFIER;
  const authURL = netflix?.reactContext?.models?.userInfo?.data?.authURL;
  if (!build || !authURL) {
    console.error("Open netflix.com while logged in, then re-run.");
    return;
  }

  const paths = [
    ["videos", SHOW_ID, "title"],
    ["videos", SHOW_ID, "seasonCount"],
    [
      "videos",
      SHOW_ID,
      "seasonList",
      "seasons",
      { from: 0, to: MAX_SEASONS },
      [
        "id",
        "length",
        "shortName",
        "episodes",
        { from: 0, to: MAX_EPISODES },
        ["id", "title", "shortName"],
      ],
    ],
  ];

  const qs = new URLSearchParams({
    drmSystem: "widevine",
    falcor_server: "0.1.0",
    withSize: "true",
    materialize: "true",
    routeAPIRequestsThroughFTL: "false",
    isVolatileBillboardsEnabled: "true",
    isTop10Supported: "true",
    original_path: "/shakti/mre/pathEvaluator",
  });

  let body = paths.map((p) => "path=" + JSON.stringify(p)).join("&");
  body += "&authURL=" + authURL;

  const url = `/api/shakti/${build}/pathEvaluator?` + qs.toString();
  console.log("Shakti POST", url, "authURL len", authURL.length);

  const resp = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body,
    credentials: "include",
  });

  if (!resp.ok) {
    console.error("Shakti failed", resp.status, await resp.text());
    return;
  }

  const data = await resp.json();
  const graph = data.jsonGraph || data;

  function atom(node) {
    if (node && typeof node === "object" && node.$type === "atom") return node.value;
    if (node && typeof node === "object" && "value" in node) return node.value;
    return node;
  }

  function deref(node) {
    if (node && node.$type === "ref") {
      let cur = graph;
      for (const part of node.value || []) {
        cur = cur?.[String(part)] ?? cur?.[part];
      }
      return cur;
    }
    return node;
  }

  function listValues(node) {
    node = deref(node);
    if (node?.$type === "list") return node.values || [];
    if (Array.isArray(node)) return node;
    if (node && typeof node === "object") {
      const keys = Object.keys(node).filter((k) => /^\d+$/.test(k));
      if (keys.length) return keys.sort((a, b) => +a - +b).map((k) => node[k]);
    }
    return [];
  }

  const videos = graph.videos || {};
  const show = videos[SHOW_ID] || {};
  const seasons = listValues(show.seasonList?.seasons);
  const episodes = {};

  seasons.forEach((seasonRef, si) => {
    let seasonObj = deref(seasonRef);
    const seasonId = atom(seasonObj?.id ?? seasonRef?.id);
    const seasonBlock = videos[String(seasonId)] || seasonObj || {};
    const eps = listValues(seasonBlock.episodes);
    eps.forEach((epRef, ei) => {
      const epObj = deref(epRef);
      const epId = atom(epObj?.id ?? epRef?.id);
      if (epId != null) {
        const key = `S${String(si + 1).padStart(2, "0")}E${String(ei + 1).padStart(2, "0")}`;
        episodes[key] = String(epId);
      }
    });
  });

  const title = atom(show.title) || "Archer";
  const payload = {
    show_id: SHOW_ID,
    show_title: title,
    shakti_build_id: build,
    episode_count: Object.keys(episodes).length,
    episodes,
    source: "browser_fetch_archer_episodes.js",
  };

  console.log(`Parsed ${payload.episode_count} episodes`);
  Object.keys(episodes)
    .sort()
    .slice(0, 5)
    .forEach((k) => console.log(`  ${k} → https://www.netflix.com/watch/${episodes[k]}`));

  const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = "archer_episodes.json";
  a.click();
  console.log("Downloaded archer_episodes.json");
})();
