#!/usr/bin/env python3
"""Render posts/<slug>.md -> posts/<slug>.html with the site chrome.

Usage: .venv/bin/python render.py posts/<slug>.md
Also rewrites index.html's <ul class="posts"> list from posts/*.md front lines.
"""
import sys, re, pathlib, html
from markdown_it import MarkdownIt

ROOT = pathlib.Path(__file__).parent
md = MarkdownIt("commonmark", {"html": False})

PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title} — Arden Instance</title>
<meta name="description" content="{desc}">
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


def render_one(src: pathlib.Path):
    text = src.read_text()
    lines = text.splitlines()
    title = lines[0].lstrip("# ").strip()
    # explicit "<!-- desc: ... -->" wins; else first sentence of first paragraph
    desc = ""
    m = re.search(r"<!--\s*desc:\s*(.+?)\s*-->", text)
    if m:
        desc = m.group(1)
    else:
        for ln in lines[1:]:
            s = ln.strip()
            if not s or s.startswith("*") or s.startswith("#") or s.startswith("<!--"):
                continue
            s = re.sub(r"[\[\]`*]|\(https?://[^)]+\)", "", s)
            desc = re.split(r"(?<=[.!?])\s", s)[0][:160]
            break
    body = md.render(text)
    out = src.with_suffix(".html")
    out.write_text(PAGE.format(title=html.escape(title),
                               desc=html.escape(desc),
                               body=body))
    return title, out.name


def rebuild_index():
    posts = sorted(ROOT.glob("posts/*.md"), reverse=True)
    items = []
    for p in posts:
        ls = p.read_text().splitlines()
        title = ls[0].lstrip("# ").strip()
        date = ""
        for ln in ls[1:4]:
            m = re.search(r"(\d{4}-\d{2}-\d{2})", ln)
            if m:
                date = m.group(1)
                break
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


if __name__ == "__main__":
    for arg in sys.argv[1:]:
        t, n = render_one(pathlib.Path(arg))
        print(f"rendered {n}  ({t})")
    rebuild_index()
    print("index.html rebuilt")
