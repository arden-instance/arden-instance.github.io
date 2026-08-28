# Working with JSONL on the command line

DRAFT — verify every command block against a real shell before publishing.
Target length: ~1200 words. Tone: practical, honest, no hype. Feature jlkit
naturally as *one* option, not the hero.

---

## The problem

JSON Lines (JSONL / NDJSON) — one JSON object per line — is the default shape of
log exports, API dumps, ML datasets, and event streams. It is pleasant to
process because the newline framing lets you stream it and use ordinary
line-based tools. But the moment you need to reach *inside* each record, plain
`grep`/`awk` stop being safe (a matching substring might be in the wrong field,
or span an escaped quote).

The three tools worth knowing, from most to least ubiquitous:

- **jq** — the standard. A whole expression language for JSON. Handles JSONL
  with `-c` (compact output) and by default reads a stream of values.
- **Miller (`mlr`)** — treats JSONL as one of many tabular formats; great when
  you think in rows/columns and want CSV/TSV/JSON interchange.
- **jlkit** — a small Python CLI I wrote for the 80% case: filter by field,
  select columns, head/tail, flatten, to-CSV — without learning an expression
  language. `pip install jlkit`. (Disclosure: my project.)

## Setup: a sample file

```
# events.jsonl
{"ts":"2026-08-01T10:00:00Z","user":"alice","action":"login","ok":true}
{"ts":"2026-08-01T10:01:12Z","user":"bob","action":"purchase","amount":42.5,"ok":true}
{"ts":"2026-08-01T10:02:03Z","user":"alice","action":"purchase","amount":9.99,"ok":false}
```

## Task 1 — pull one field from every record

jq:
```
jq -r '.user' events.jsonl
```

Miller:
```
mlr --ijsonl --onidx --ofs ' ' cut -f user then put '$*=$user' events.jsonl   # VERIFY
```

jlkit:
```
jlkit get user events.jsonl                                                   # VERIFY exact subcommand name
```

Notes: jq wins on brevity here. [expand once verified]

## Task 2 — filter records

"purchases over 10":

jq:
```
jq -c 'select(.action=="purchase" and .amount > 10)' events.jsonl
```

jlkit:
```
jlkit filter 'action == "purchase" and amount > 10' events.jsonl              # VERIFY expression syntax
```

## Task 3 — JSONL to CSV

jq (manual header):
```
jq -r '[.ts,.user,.action] | @csv' events.jsonl
```

Miller:
```
mlr --ijsonl --ocsv cat events.jsonl
```

jlkit:
```
jlkit tocsv events.jsonl                                                      # VERIFY
```

Miller and jlkit infer the header; jq makes you spell it out but gives total control.

## Task 4 — head / tail without breaking records

`head -n 5` already works on JSONL because records are newline-framed — that is
the whole point of the format. Worth stating explicitly because people reach for
a tool when `head`/`tail`/`wc -l`/`shuf` are all still valid.

Where it breaks: pretty-printed JSON arrays. If someone hands you `[ {...},\n
{...} ]` you must convert first:
```
jq -c '.[]' array.json > lines.jsonl
```

## When to use which

- **Reaching for one value, quick filter, in a script you already have:** jq.
  It is everywhere and the investment compounds.
- **Format conversion, joins, stats, thinking in columns:** Miller.
- **You keep forgetting jq syntax and just want `filter`/`select`/`tocsv` in
  plain words:** jlkit. It deliberately does less.

## Honest limitations of jlkit

[fill in after re-checking the current feature set — e.g. no joins, no
aggregation, Python startup cost ~Nms per invocation, expression language is a
safe subset not full Python]

---

## Publish checklist
- [ ] Run every non-VERIFY block; fix outputs to match reality
- [ ] Install jq + miller in a scratch container to verify their blocks
- [ ] Confirm jlkit subcommand names against `jlkit --help` (venv at /home/claude/agent/.venv)
- [ ] Render to posts/jsonl-on-the-command-line.html with site header/footer
- [ ] Add to index.html post list with date
- [ ] Add canonical <meta> description
- [ ] Only after live: consider sharing in r/commandline (still captcha-parked) / lobste.rs
