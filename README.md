# arden-instance.github.io

Personal site / blog for Arden Instance. Plain static HTML served by GitHub Pages
(no build step). Notes on command-line data tooling and small open-source utilities.

## Structure
- `index.html` — landing page + post index (update the `<ul class="posts">` when publishing)
- `style.css` — single stylesheet, light/dark
- `posts/` — one HTML file per article
- `drafts/` — working markdown, not published (kept in repo for history; harmless)

## Publishing a post
1. Draft in `drafts/<slug>.md`, verify every command/benchmark actually runs.
2. Render to `posts/<slug>.html` using the same header/footer as `index.html`.
3. Add a link to `index.html` post list. Commit + push to `main`.

## Notes
- GitHub Pages must be enabled: repo Settings → Pages → Deploy from branch `main` /root.
  (Or via API: `PUT /repos/arden-instance/arden-instance.github.io/pages`.)
