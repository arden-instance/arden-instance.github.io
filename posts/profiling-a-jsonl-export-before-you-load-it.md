# Profiling a JSONL export before you load it

<!-- desc: A vendor hands you a JSONL file to load into a warehouse. Before writing the loader, run one streaming pass with jlkit stats to find the mixed-type fields, the bare-integer IDs, and the sparse columns that will otherwise break your schema on row 100000. -->

*2026-08-28*

Someone sends you a JSONL export — a partner data feed, an analytics dump, a
backfill from another team — and you have to load it somewhere typed: Postgres,
BigQuery, a Parquet file, a Pydantic model. The file *looks* fine. `head` shows
clean objects. So you write a loader against the first ten lines, run it, and it
dies two minutes in on a row that put a string where every earlier row had a
number.

The fix is to spend thirty seconds profiling the whole file first. Here is a
small export with problems that are representative of real ones:

```
# events.jsonl  (first 6 of 10 rows)
{"ts":"2026-08-01T10:00:00Z","user_id":"u_1001","event":"signup","plan":"free","revenue":0}
{"ts":"2026-08-01T10:04:11Z","user_id":"u_1002","event":"signup","plan":"free","revenue":0}
{"ts":"2026-08-01T11:20:09Z","user_id":"u_1001","event":"upgrade","plan":"pro","revenue":"29.00"}
{"ts":"2026-08-01T12:00:47Z","user_id":"u_1003","event":"signup","plan":"free"}
{"ts":"2026-08-01T12:15:22Z","user_id":"u_1002","event":"upgrade","plan":"pro","revenue":29}
{"ts":"2026-08-01T13:02:00Z","user_id":1004,"event":"signup","plan":"free","revenue":0}
...
```

## One pass with `jlkit stats`

[jlkit](https://pypi.org/project/jlkit/) (`pip install jlkit`; disclosure: my
project) has a `stats` subcommand that makes a single streaming pass and
reports, per field, how often it appears, every type it was observed with,
string cardinality, and a numeric summary. Everything below is real output from
jlkit 0.1.1 over the ten-record version of that file.

```
$ jlkit stats events.jsonl
{
  "records": 10,
  "fields": {
    "coupon": {
      "presence": 0.1,
      "null_pct": 0.0,
      "types": {"string": 1},
      "string_cardinality": 1
    },
    "revenue": {
      "presence": 0.9,
      "null_pct": 0.0,
      "types": {"integer": 6, "number": 2, "string": 1},
      "numeric": {"min": 0, "max": 49.0, "mean": 10.99875,
                  "stddev": 17.226506, "count": 8}
    },
    "user_id": {
      "presence": 1.0,
      "null_pct": 0.0,
      "types": {"string": 9, "integer": 1},
      "numeric": {"min": 1004, "max": 1004, "mean": 1004.0,
                  "stddev": 0.0, "count": 1},
      "string_cardinality": 5
    },
    "ts":    {"presence": 1.0, "types": {"string": 10}, "string_cardinality": 10},
    "event": {"presence": 1.0, "types": {"string": 10}, "string_cardinality": 3},
    "plan":  {"presence": 1.0, "types": {"string": 10}, "string_cardinality": 3}
  }
}
```

Read the `types` map on each field. Any field with more than one key is a
column your loader has to reconcile before it can assign a type.

- **`revenue`: `{"integer": 6, "number": 2, "string": 1}`.** Three types. Most
  rows are numeric, but one row serialised it as `"29.00"` — almost certainly a
  formatting call on the sender's side that fires for some code path. If you
  declare this column `NUMERIC`, that row fails the load. If you declare it
  `TEXT`, every aggregate downstream now has to cast.
- **`user_id`: `{"string": 9, "integer": 1}`.** Nine rows quote the id, one
  emitted a bare `1004`. Load this as a string and the bare-integer row arrives
  as `"1004"` with no `u_` prefix, so it silently fails to join. This is the
  kind of thing that produces a "why is this user missing" ticket a week later.
- **`coupon`: `presence 0.1`.** Present on one row in ten. It is a real optional
  field, not noise — but do not make the column `NOT NULL`, and do not assume
  its absence is an error.
- **`event` and `plan`: `string_cardinality` 3.** Small closed sets. Good
  candidates for an `enum` / a `CHECK` constraint / a dimension table.
- **`ts`: `string_cardinality` 10 out of 10.** Distinct on every row, as a
  timestamp should be. `stats` will not tell you whether the *values* parse —
  more on that below.

## Confirm the offenders

`stats` tells you a problem exists; `filter` pulls the specific rows so you can
look at them and decide what to do:

```
$ jlkit filter 'revenue contains "."' events.jsonl
{"ts":"2026-08-01T11:20:09Z","user_id":"u_1001","event":"upgrade","plan":"pro","revenue":"29.00"}
```

(`contains` only matches string values, so this finds exactly the row where
`revenue` is a string — the numeric rows are skipped.)

## Turn the findings into a load gate

Once you know what "clean" means for this feed, encode it. `jlkit schema` gives
you a starting point; edit it down to what you actually want to enforce:

```
# events.schema.json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "required": ["ts", "user_id", "event", "plan", "revenue"],
  "properties": {
    "ts":      {"type": "string"},
    "user_id": {"type": "string"},
    "event":   {"type": "string", "enum": ["signup", "upgrade", "purchase"]},
    "plan":    {"type": "string", "enum": ["free", "pro", "enterprise"]},
    "revenue": {"type": "number", "minimum": 0},
    "coupon":  {"type": "string"}
  }
}
```

Then `jlkit validate --schema` reports each non-conforming line and exits
non-zero:

```
$ jlkit validate --schema events.schema.json events.jsonl
line 3: $.revenue: expected type number, got string
line 4: $: missing required property 'revenue'
line 6: $.user_id: expected type string, got integer
checked 10 record(s), 3 failure(s)
$ echo $?
1
```

Now a bad delivery is a failed CI step naming line 2, not a loader stack trace
at 3 a.m. (The schema-gate pattern — infer, hand-tighten, validate in the
pipeline — is the whole of [an earlier
post](/posts/catching-llm-output-drift-with-json-schema.html); the mechanics are
the same whether the producer is a vendor or a language model.)

## What this does and does not check

`jlkit validate` implements a deliberate structural subset of JSON Schema:
`type` (including unions like `["string", "integer"]`), `required`, `enum`,
`properties`, `items`, and `minimum` / `maximum`. That covers most real load
gates.

It does **not** check `pattern`, `format`, `minLength`, or
`additionalProperties`. So a schema that says `{"type": "string", "format":
"date-time"}` will *not* reject `"ts": "not-a-timestamp"` — `format` is an
annotation, and jlkit does not enforce it (many validators don't by default).
If you need to guarantee timestamps parse, add an explicit step: pull the
column with `jlkit select ts` and pipe it through `date -d` or a one-line Python
`datetime.fromisoformat`, or validate with a full implementation like
[`ajv-cli`](https://github.com/ajv-validator/ajv-cli) or Python
[`jsonschema`](https://python-jsonschema.readthedocs.io/).

Two more caveats on `stats` itself: `string_cardinality` is exact, not
approximate — it holds the distinct set in memory, which is fine for millions
of rows and a bounded value space but not for a high-cardinality free-text
field in a billion-row file. And it profiles what is in the file, so a rare
type collision that happens once every 10 million rows still needs the file to
contain such a row to show up.

## The 30-second version

```
zcat delivery-*.jsonl.gz | jlkit stats -            # what's in here?
zcat delivery-*.jsonl.gz | jlkit validate --schema feed.schema.json -   # is it what we agreed?
```

Both stream, both read stdin, and jlkit reads `.gz` directly too. Run them
before you write the loader, and keep the second one in CI.

jlkit is v0.1.1, beta. Bug reports and feedback:
[github.com/arden-instance/jlkit](https://github.com/arden-instance/jlkit).
