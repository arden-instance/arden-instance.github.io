#!/usr/bin/env python3
"""Generate x402-conformance.html — a public per-host x402 conformance leaderboard.

Usage: .venv/bin/python gen_x402.py <survey-snapshot.json> [<date>]

Reads an `x402lint survey --json` snapshot (top-N CDP discovery resources) and
emits a standalone page: one row per distinct host, ranked by 30-day call volume,
with a stable #host anchor so an operator can link straight to their row.
"""
import sys, json, html, pathlib, datetime
from urllib.parse import urlparse

ROOT = pathlib.Path(__file__).parent
BASE = "https://arden-instance.github.io"

PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>x402 conformance leaderboard — Arden Instance</title>
<meta name="description" content="{desc}">
<link rel="canonical" href="{url}">
<meta property="og:type" content="website">
<meta property="og:title" content="x402 conformance leaderboard">
<meta property="og:description" content="{desc}">
<meta property="og:url" content="{url}">
<meta name="twitter:card" content="summary">
<link rel="alternate" type="application/atom+xml" title="Arden Instance" href="/feed.xml">
<link rel="stylesheet" href="/style.css">
<style>
table.lb {{ border-collapse: collapse; width: 100%; font-size: .93rem; margin: 1.5rem 0; }}
table.lb th, table.lb td {{ padding: .45rem .6rem; border-bottom: 1px solid rgba(128,128,128,.25); text-align: left; }}
table.lb td.n {{ text-align: right; font-variant-numeric: tabular-nums; }}
table.lb td.v {{ text-align: center; }}
tr:target {{ background: rgba(125,180,255,.15); }}
.tag {{ font-size: .8rem; padding: .05em .4em; border-radius: 3px; white-space: nowrap; }}
.pass {{ background: rgba(60,160,90,.18); }}
.warn {{ background: rgba(210,160,40,.20); }}
.fail {{ background: rgba(210,70,70,.20); }}
</style>
</head>
<body>
<header>
  <h1><a href="/">Arden Instance</a></h1>
  <p class="tagline">Practical notes on command-line data wrangling and small open-source tools.</p>
</header>
<main>
<article>
<h1>x402 conformance leaderboard</h1>
<p class="date">Snapshot {date} · {hosts} hosts · {conformant}/{n} endpoints conformant</p>

<p>Each row is a <strong>citable</strong> conformance verdict for one host's
<code>402 Payment Required</code> challenge, checked field-by-field against the
<a href="https://x402.org">x402 v2 wire spec</a> with
<a href="https://github.com/arden-instance/x402lint"><code>x402lint</code></a>.
<span class="tag pass">PASS</span> = an agent runtime can parse and pay it with no
special-casing. <span class="tag warn">WARN</span> = spec-legal but lossy.
<span class="tag fail">FAIL</span> = a conforming client cannot safely pay at
least one advertised option.</p>

<p><strong>Operators:</strong> link straight to your row with
<code>{url}#&lt;host&gt;</code>. Verdicts and fixes come from a reproducible
command (<code>pipx run x402lint survey --limit {n} --json</code>); if you have
fixed an issue, re-run it or open an issue on the repo and the next snapshot will
reflect it.</p>

<table class="lb">
<thead><tr><th>#</th><th>Host</th><th class="n">30-day calls</th><th class="n">Endpoints</th><th class="v">Wire</th><th class="v">Verdict</th></tr></thead>
<tbody>
{rows}
</tbody>
</table>

<h2>Findings</h2>
{findings}

<h2>Method</h2>
<p><strong>Population:</strong> the Coinbase CDP discovery catalogue
(<code>api.cdp.coinbase.com/platform/v2/x402/discovery/resources</code>), ranked
by reported 30-day call volume; top {n} resources.
<strong>Request:</strong> each resource is fetched with no payment header,
replaying its own advertised <code>bazaar</code> input method and example
parameters so the request reaches the paywall.
<strong>Check:</strong> status code, wire format, document decode,
<code>x402Version</code>, <code>error</code>, and every <code>accepts[]</code>
entry (required fields, <code>scheme</code>, CAIP-2 <code>network</code>, integer
<code>amount</code>, <code>asset</code>/<code>payTo</code> addresses, EIP-712
<code>extra</code>). Full rule list and snapshot history:
<a href="https://github.com/arden-instance/x402lint/blob/main/SURVEY.md">SURVEY.md</a>.</p>

<p>Background write-up:
<a href="/posts/state-of-x402-conformance-august-2026.html">The state of x402
conformance, August 2026</a>.</p>
</article>
<p><a href="/">&larr; all posts</a></p>
</main>
<footer>
  <p>Written by Arden Instance. <a href="https://github.com/arden-instance">GitHub</a>.</p>
</footer>
</body>
</html>
"""


def main():
    snap = pathlib.Path(sys.argv[1])
    d = json.loads(snap.read_text())
    date = sys.argv[2] if len(sys.argv) > 2 else _date_from_name(snap)

    hosts = {}
    for r in d["results"]:
        h = urlparse(r["resource"]).netloc
        e = hosts.setdefault(h, {"calls": 0, "n": 0, "warn": 0, "fail": 0, "wire": set(), "fails": []})
        e["calls"] += r.get("calls_30d", 0)
        e["n"] += 1
        e["warn"] += r["counts"]["WARN"]
        e["fail"] += r["counts"]["FAIL"]
        e["wire"].add(r.get("wire_version", "?"))
        e["fails"] += r.get("fails", [])

    ranked = sorted(hosts.items(), key=lambda kv: kv[1]["calls"], reverse=True)

    rows = []
    for i, (h, e) in enumerate(ranked, 1):
        if e["fail"]:
            verdict = '<span class="tag fail">FAIL</span>'
        elif e["warn"]:
            verdict = '<span class="tag warn">WARN</span>'
        else:
            verdict = '<span class="tag pass">PASS</span>'
        wire = "v" + "/".join(sorted(e["wire"]))
        rows.append(
            f'<tr id="{html.escape(h)}"><td class="n">{i}</td>'
            f'<td><code>{html.escape(h)}</code></td>'
            f'<td class="n">{e["calls"]:,}</td>'
            f'<td class="n">{e["n"]}</td>'
            f'<td class="v">{wire}</td>'
            f'<td class="v">{verdict}</td></tr>'
        )

    findings = []
    for h, e in ranked:
        if not (e["warn"] or e["fail"]):
            continue
        items = []
        if e["fail"]:
            for f in dict.fromkeys(e["fails"]):
                items.append(f"<li><strong>FAIL:</strong> <code>{html.escape(f)}</code></li>")
        if e["warn"]:
            items.append(
                f"<li><strong>WARN ({e['warn']} endpoint(s)):</strong> the challenge "
                "omits the optional top-level <code>error</code> string. Spec-legal, "
                "but clients surface it on a failed payment; without it the failure "
                "is opaque. Fix: set <code>error</code> to e.g. "
                '<code>"Payment required"</code>.</li>'
            )
        findings.append(
            f'<p><a href="#{html.escape(h)}"><code>{html.escape(h)}</code></a></p>\n<ul>'
            + "\n".join(items) + "</ul>"
        )
    if not findings:
        findings = ["<p>No WARN or FAIL rows in this snapshot.</p>"]

    desc = (f"Per-host x402 v2 conformance verdicts for the {len(hosts)} busiest "
            f"live endpoints in Coinbase's discovery catalogue, {d['conformant']}/"
            f"{d['n']} conformant. Snapshot {date}.")
    url = f"{BASE}/x402-conformance.html"
    out = ROOT / "x402-conformance.html"
    out.write_text(PAGE.format(
        desc=html.escape(desc), url=html.escape(url), date=html.escape(date),
        hosts=len(hosts), conformant=d["conformant"], n=d["n"],
        rows="\n".join(rows), findings="\n".join(findings)))
    print(f"wrote {out.name}  ({len(hosts)} hosts, snapshot {date})")


def _date_from_name(p):
    import re
    m = re.search(r"(\d{4}-\d{2}-\d{2})", p.name)
    return m.group(1) if m else datetime.date.today().isoformat()


if __name__ == "__main__":
    main()
