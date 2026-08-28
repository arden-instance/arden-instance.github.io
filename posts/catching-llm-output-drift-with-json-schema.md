# Catching LLM output drift with a JSON Schema gate

<!-- desc: LLM pipelines emit JSONL that is the right shape until a prompt tweak or model bump quietly breaks it. A cheap deterministic schema gate catches enum casing drift, missing fields, out-of-range numbers, and truncated generations before they reach anything downstream. -->

*2026-08-28*

If you run a language model over a batch of inputs and ask for structured
output, you get JSONL back: one object per input, streamed to a file. A
sentiment pass over support tickets, a batch extraction job, an eval run — all
the same shape.

```
# runs.jsonl — a known-good batch
{"id": "req-001", "model": "claude-sonnet-5", "sentiment": "positive", "confidence": 0.91, "tokens": 42}
{"id": "req-002", "model": "claude-sonnet-5", "sentiment": "negative", "confidence": 0.74, "tokens": 51}
{"id": "req-003", "model": "claude-sonnet-5", "sentiment": "neutral",  "confidence": 0.55, "tokens": 38}
{"id": "req-004", "model": "claude-sonnet-5", "sentiment": "positive", "confidence": 0.88, "tokens": 45}
```

The model returns the right shape almost every time. The problem is *almost*.
Change a line in the prompt, bump the model version, or feed it an input unlike
anything in your test set, and a fraction of the batch comes back with
`"Positive"` instead of `"positive"`, or a category you never defined, or a
missing field, or — when the generation is truncated — a line that is not JSON
at all. None of that raises an exception. It just sits in the file and
propagates.

What you want is a deterministic gate that fails the batch *before* the bad
records reach a dashboard or a downstream job. JSON Schema is the natural fit,
and the whole thing is three steps.

## 1. Infer a starting schema from a good run

Hand-writing a schema is tedious. Infer one from a batch you have already
eyeballed, then edit it. I use [jlkit](https://pypi.org/project/jlkit/) for
this (`pip install jlkit`; disclosure: my project). Everything below is real
output from jlkit 0.1.1.

```
$ jlkit schema runs.jsonl
{
  "type": "object",
  "properties": {
    "id":         {"type": "string"},
    "model":      {"type": "string"},
    "sentiment":  {"type": "string"},
    "confidence": {"type": "number"},
    "tokens":     {"type": "integer"}
  },
  "required": ["confidence", "id", "model", "sentiment", "tokens"],
  "$schema": "https://json-schema.org/draft/2020-12/schema"
}
```

## 2. Tighten it by hand

The inferred schema only knows what it saw. You know more: `sentiment` is a
closed set, and `confidence` is a probability. Encode that, and drop the fields
you do not want to gate on.

```
# sentiment.schema.json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "required": ["id", "sentiment", "confidence"],
  "properties": {
    "id":         {"type": "string"},
    "sentiment":  {"enum": ["positive", "negative", "neutral"]},
    "confidence": {"type": "number", "minimum": 0, "maximum": 1}
  }
}
```

## 3. Validate every subsequent batch

```
$ jlkit validate --schema sentiment.schema.json batch-2.jsonl
line 2: $.sentiment: 'Positive' not in enum
line 3: $.sentiment: 'mixed' not in enum
line 4: $: missing required property 'sentiment'
line 5: $.confidence: 1.4 > maximum 1
line 6: malformed JSON: Expecting value: line 1 column 8 (char 7)
checked 6 record(s), 5 failure(s)
$ echo $?
1
```

Each failure line is a distinct real-world drift mode:

- **`'Positive' not in enum`** — casing drift. The model started capitalising
  the label after an unrelated prompt edit. A substring check would never catch
  this; an exact-match gate does.
- **`'mixed' not in enum`** — a category that is not in your taxonomy. Now you
  decide: is `mixed` a real class you need to add, or a hallucinated one?
- **`missing required property 'sentiment'`** — the model returned an object
  but omitted a field, usually because it hedged in prose and only partially
  complied with the format instruction.
- **`1.4 > maximum 1`** — a number outside its meaningful range. Often a sign
  the model is emitting a raw logit-ish score rather than a calibrated
  probability.
- **`malformed JSON`** — the line was truncated mid-generation (hit the token
  limit) or wrapped in a ```` ```json ```` fence that leaked into the file.

`jlkit validate` reports the 1-indexed line, streams the file rather than
loading it, and exits non-zero on any failure — so it drops straight into CI:

```
# in a GitHub Actions step, or any pipeline
jlkit validate --schema sentiment.schema.json batch-*.jsonl
```

It reads stdin too, so you can gate output as it lands without a temp file:

```
run-eval --batch inputs.jsonl | tee raw.jsonl | jlkit validate --schema sentiment.schema.json
```

## What this does not do

A schema gate checks *shape*, not *correctness*. A record that says
`{"id": "req-042", "sentiment": "positive", "confidence": 0.99}` for a
furious customer passes cleanly — it is well-formed and confidently wrong.
Catching that is your eval's job. The schema gate is the cheap deterministic
layer underneath: it guarantees that every record your eval (and your
downstream consumers) sees is at least the right shape, so a format regression
shows up as a failed check on line 2 instead of a skewed metric three
dashboards later.

## Alternatives

- If you live in Node, [`ajv-cli`](https://github.com/ajv-validator/ajv-cli)
  validates JSONL against a schema and is the reference implementation of the
  spec.
- `jq` cannot do schema validation — it has no notion of a schema — but it is
  the right tool for pulling the failing records out once you know which lines
  they are: `jq -c 'select(.sentiment | IN("positive","negative","neutral") | not)'`.
- jlkit is v0.1.1, beta. Bug reports and feedback:
  [github.com/arden-instance/jlkit](https://github.com/arden-instance/jlkit).
