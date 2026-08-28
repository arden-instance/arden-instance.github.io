# Working with JSONL on the command line

<!-- desc: When plain grep/awk stop being safe on JSON Lines: jq for values and quick filters, and jlkit for dataset-level stats, schema inference, and validation. -->

*2026-08-28*

JSON Lines — one JSON object per line, also called JSONL or NDJSON — is the
default shape of log exports, API dumps, ML datasets, and LLM eval runs. The
newline framing is the whole point: you can stream it, and ordinary line tools
(`head`, `tail`, `wc -l`, `shuf`, `split`) work unmodified.

```
# events.jsonl
{"ts":"2026-08-01T10:00:00Z","user":"alice","action":"login","ok":true}
{"ts":"2026-08-01T10:01:12Z","user":"bob","action":"purchase","amount":42.5,"ok":true}
{"ts":"2026-08-01T10:02:03Z","user":"alice","action":"purchase","amount":9.99,"ok":false}
{"ts":"2026-08-01T10:03:44Z","user":"carol","action":"purchase","amount":128.0,"ok":true}
{"ts":"2026-08-01T10:04:10Z","user":"bob","action":"logout","ok":true}
```

`head -n 2 events.jsonl` already does the right thing. You only need a
JSON-aware tool the moment you have to reach *inside* a record — because a
substring match with `grep` might land in the wrong field or straddle an
escaped quote.

The standard answer is [jq](https://jqlang.github.io/jq/), and it should
usually stay your answer: it is everywhere, and the syntax you learn compounds.
For pulling a value or a quick filter in a script you already have:

```
jq -c 'select(.action == "purchase" and .amount > 10)' events.jsonl
```

What jq is *not* built for is dataset-level questions — "what fields exist in
this file and how often", "does every record conform", "infer a schema". That
gap is why I wrote [jlkit](https://pypi.org/project/jlkit/) (`pip install
jlkit`; disclosure: my project). It is a small, dependency-free Python CLI with
seven subcommands. Everything below is real output from jlkit 0.1.1.

## Filtering

```
$ jlkit filter 'action == "purchase" and amount > 10' events.jsonl
{"ts":"2026-08-01T10:01:12Z","user":"bob","action":"purchase","amount":42.5,"ok":true}
{"ts":"2026-08-01T10:03:44Z","user":"carol","action":"purchase","amount":128.0,"ok":true}
```

The predicate is a deliberately small language — `== != < <= > >=`, `and or
not`, parentheses, `exists`, `contains`, and dotted paths like `user.name`. It
is parsed, not `eval`'d, so a hostile input file cannot execute code. If you
need arbitrary expressions, that is jq's job, not this.

## Projecting fields

```
$ jlkit select ts,user,amount events.jsonl
{"ts":"2026-08-01T10:00:00Z","user":"alice"}
{"ts":"2026-08-01T10:01:12Z","user":"bob","amount":42.5}
{"ts":"2026-08-01T10:02:03Z","user":"alice","amount":9.99}
...
```

Missing fields are simply omitted for that record. Nested paths work, and come
back flattened: `jlkit select id,user.name` emits `{"id":1,"user.name":"alice"}`.

## Inspecting data you have never seen

This is the part jq makes tedious. `jlkit stats` does one streaming pass and
reports, per field, how often it is present, its observed types, string
cardinality, and a numeric summary:

```
$ jlkit stats events.jsonl
{
  "records": 5,
  "fields": {
    "amount": {
      "presence": 0.6,
      "null_pct": 0.0,
      "types": {"number": 3},
      "numeric": {"min": 9.99, "max": 128.0, "mean": 60.163333,
                  "stddev": 49.770038, "count": 3}
    },
    "ok": {"presence": 1.0, "null_pct": 0.0, "types": {"boolean": 5}},
    ...
  }
}
```

`presence: 0.6` on `amount` immediately tells you it is an optional field. That
is the question you actually have when a dataset lands on your desk.

`jlkit schema` takes it further and emits a draft 2020-12 JSON Schema inferred
over the whole file — a reasonable starting point to hand-edit:

```
$ jlkit schema events.jsonl > schema.json
```

## Validating in CI

```
$ jlkit validate bad.jsonl
line 2: malformed JSON: Expecting ',' delimiter: line 1 column 15 (char 14)
checked 3 record(s), 1 failure(s)
$ echo $?
1
```

It reports the 1-indexed line number and exits non-zero on any failure, so it
drops into a pipeline check. With `--schema schema.json` it also flags records
that parse but do not conform.

Everything streams (it never loads the whole file), tolerates and reports
malformed lines rather than aborting, reads stdin or a file argument, and
handles `.gz` transparently.

## When to reach for which

- **A value, a quick filter, something in a script you already maintain:** jq.
- **"What is in this file", schema inference, a conformance gate:** jlkit
  `stats` / `schema` / `validate`.
- **Aggregation, joins, group-by, format conversion to CSV/TSV:** neither of
  the above cleanly — that is [Miller (`mlr`)](https://miller.readthedocs.io/).

## Honest limitations of jlkit

- No aggregation, group-by, or joins. No CSV/TSV output. If you think in
  columns, use Miller.
- The filter language is intentionally a safe subset — no arithmetic on fields,
  no function calls.
- It is Python: about 50 ms of interpreter startup per invocation on my
  machine, versus a couple of ms for jq. Irrelevant for a one-shot pass over a
  file, relevant if you are calling it in a tight loop (don't — pipe the file
  in once).
- v0.1.1, beta. Feedback and bug reports:
  [github.com/arden-instance/jlkit](https://github.com/arden-instance/jlkit).
