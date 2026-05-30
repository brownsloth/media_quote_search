# Netlify / Gatsby integration

Same pattern as Hindi Jinnie.

```bash
cp -r serving/web/* /Users/starun/myblogs/projects/static/quote-memory/
```

Add `gatsby-node.ts` (already in projects repo) so `gatsby develop` serves
`/quote-memory/` and `/hindi-jinnie/`. Restart dev server after changes.

Edit `static/quote-memory/config.js`:

```js
window.QUOTE_MEMORY_API = "https://YOUR-RAILWAY-APP.up.railway.app";
```

Add a page or iframe link on your portfolio. Push → Netlify rebuilds.

Set `CORS_ORIGINS` on Railway to include `https://projects.tarun-ssharma.com`.
