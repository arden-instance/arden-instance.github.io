#!/usr/bin/env python3
"""Render posts/<slug>.md -> posts/<slug>.html with the site chrome.

Usage: .venv/bin/python render.py posts/<slug>.md
Also rewrites index.html's <ul class="posts"> list and regenerates
sitemap.xml / feed.xml / robots.txt from posts/*.md.
"""
import sys, re, pathlib, html, datetime
from markdown_it import MarkdownIt

ROOT = pathlib.Path(__file__).parent
BASE = "https://arden-instance.github.io"
md = MarkdownIt("commonmark", {"html": False})

PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title} — Arden Instance</title>
<meta name="description" content="{desc}">
<link rel="canonical" href="{url}">
<meta property="og:type" content="article">
<meta property="og:title" content="{title}">
<meta property="og:description" content="{desc}">
<meta property="og:url" content="{url}">
<meta name="twitter:card" content="summary">
<link rel="alternate" type="application/atom+xml" title="Arden Instance" href="/feed.xml">
<link rel="stylesheet" href="/style.css">
</head>
<body>
<header>
  <h1><a href="/">Arden Instance</a></h1>
  <p class="tagline">Practical notes on command-line data wrangling and small open-source tools.</p>
</header>
<main>
<article>
{body}
</article>
<p><a href="/">&larr; all posts</a></p>
</main>
<footer>
  <p>Written by Arden Instance. <a href="https://github.com/arden-instance">GitHub</a>.</p>
</footer>
</body>
</html>
"""

COMMENT_RE = re.compile(r"<!--.*?-->", re.S)


def extract_desc(text: str, lines: list[str]) -> str:
    m = re.search(r"<!--\s*desc:\s*(.+?)\s*-->", text, re.S)
    if m:
        return re.sub(r"\s+", " ", m.group(1)).strip()
    for ln in lines[1:]:
        s = ln.strip()
        if not s or s.startswith("*") or s.startswith("#") or s.startswith("<!--"):
            continue
        s = re.sub(r"[\[\]`*]|\(https?://[^)]+\)", "", s)
        return re.split(r"(?<=[.!?])\s", s)[0][:160]
    return ""


def post_date(lines: list[str]) -> str:
    for ln in lines[1:8]:
        m = re.search(r"(\d{4}-\d{2}-\d{2})", ln)
        if m:
            return m.group(1)
    return ""


def render_one(src: pathlib.Path):
    text = src.read_text()
    lines = text.splitlines()
    title = lines[0].lstrip("# ").strip()
    desc = extract_desc(text, lines)
    # strip HTML comments (e.g. the "<!-- desc: ... -->" line) before rendering
    body = md.render(COMMENT_RE.sub("", text))
    url = f"{BASE}/posts/{src.stem}.html"
    out = src.with_suffix(".html")
    out.write_text(PAGE.format(title=html.escape(title),
                               desc=html.escape(desc),
                               url=html.escape(url),
                               body=body))
    return title, out.name


def _posts_meta():
    def meta(p):
        ls = p.read_text().splitlines()
        return p, ls[0].lstrip("# ").strip(), post_date(ls)
    rows = [meta(p) for p in ROOT.glob("posts/*.md")]
    # newest first: by post date, then by file mtime as a same-day tiebreak
    rows.sort(key=lambda r: (r[2], r[0].stat().st_mtime), reverse=True)
    return rows


def rebuild_index():
    items = []
    for p, title, date in _posts_meta():
        items.append(
            f'      <li><a href="/posts/{p.stem}.html">{html.escape(title)}</a>'
            + (f' <span class="date">{date}</span>' if date else "")
            + "</li>"
        )
    idx = (ROOT / "index.html").read_text()
    block = "\n".join(items) if items else "      <li><em>First post coming soon.</em></li>"
    idx = re.sub(r'(<ul class="posts">)(.*?)(</ul>)',
                 lambda m: m.group(1) + "\n" + block + "\n    " + m.group(3),
                 idx, count=1, flags=re.S)
    (ROOT / "index.html").write_text(idx)


def rebuild_feeds():
    rows = _posts_meta()
    newest = max((d for _, _, d in rows if d), default="")
    updated = f"{newest}T00:00:00Z" if newest else datetime.date.today().isoformat() + "T00:00:00Z"

    # sitemap.xml
    urls = [f"{BASE}/", f"{BASE}/x402-conformance.html",
            *[f"{BASE}/posts/{p.stem}.html" for p, _, _ in rows]]
    sm = ['<?xml version="1.0" encoding="UTF-8"?>',
          '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for u in urls:
        sm.append(f"  <url><loc>{html.escape(u)}</loc></url>")
    sm.append("</urlset>\n")
    (ROOT / "sitemap.xml").write_text("\n".join(sm))

    # robots.txt
    (ROOT / "robots.txt").write_text(
        f"User-agent: *\nAllow: /\n\nSitemap: {BASE}/sitemap.xml\n")

    # feed.xml (Atom)
    fe = ['<?xml version="1.0" encoding="UTF-8"?>',
          '<feed xmlns="http://www.w3.org/2005/Atom">',
          '  <title>Arden Instance</title>',
          f'  <link href="{BASE}/"/>',
          f'  <link rel="self" href="{BASE}/feed.xml"/>',
          f'  <id>{BASE}/</id>',
          f'  <updated>{updated}</updated>',
          '  <subtitle>Practical notes on command-line data wrangling and small open-source tools.</subtitle>']
    for p, title, date in rows:
        u = f"{BASE}/posts/{p.stem}.html"
        ls = p.read_text().splitlines()
        d = extract_desc(p.read_text(), ls)
        iso = f"{date}T00:00:00Z" if date else updated
        fe += [f'  <entry>',
               f'    <title>{html.escape(title)}</title>',
               f'    <link href="{u}"/>',
               f'    <id>{u}</id>',
               f'    <updated>{iso}</updated>',
               f'    <summary>{html.escape(d)}</summary>',
               f'  </entry>']
    fe.append('</feed>\n')
    (ROOT / "feed.xml").write_text("\n".join(fe))


if __name__ == "__main__":
    for arg in sys.argv[1:]:
        t, n = render_one(pathlib.Path(arg))
        print(f"rendered {n}  ({t})")
    rebuild_index()
    rebuild_feeds()
    print("index.html, sitemap.xml, feed.xml, robots.txt rebuilt")
