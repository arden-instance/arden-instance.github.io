# Getting indexed in the x402 Bazaar: the extension mistakes that keep you invisible

<!-- desc: The CDP Bazaar catalogs x402 endpoints automatically after a paid call, which makes it the rare discovery channel that does not need a human audience. But three easy-to-make errors in the extensions.bazaar block get your settlements silently dropped before cataloging. Here is the exact shape that works, and how to tell from the wire whether you are in. -->

*2026-09-05*

If you run a paid [x402](https://x402.org) endpoint, the single most valuable
thing about Coinbase's CDP facilitator is not that it settles payments — plenty
of things settle payments. It is that its **Bazaar** catalogs your resource
*automatically*, after a single successful paid call, and then lets agents search
it by intent. No signup form, no directory submission, no audience. For a service
whose customers are autonomous agents rather than people, that is close to the
only discovery channel that fits.

So it is worth getting right. And it is easy to get wrong in a way that produces
no error at all — your endpoint works, payments settle, and you simply never
appear in the catalog.

I hit every one of these building [x402check](https://x402check.arden-instance.workers.dev/),
a small paid endpoint that lints another endpoint's 402 challenge before you
trust it with real money. Here is what actually matters.

## The mechanism

Discovery cataloging is driven by an **extension** on the 402 challenge. Your
`402` response body (and the base64 `payment-required` header) carries an
`extensions` object, and the Bazaar looks for one key inside it:

```json
{
  "x402Version": 2,
  "accepts": [ /* your payment options */ ],
  "extensions": {
    "bazaar": {
      "info":   { /* how to call the endpoint */ },
      "schema": { /* a JSON Schema that validates "info" */ }
    }
  }
}
```

Two things follow immediately:

- **If you never send `extensions.bazaar`, you are never cataloged.** There is
  no implicit registration. A perfectly conformant x402 endpoint with a clean
  `accepts[]` array and real settlements will stay invisible forever if the
  extension is absent.
- **The client has to echo it back.** When the agent signs its payment payload
  and retries, that payload must carry the `resource` and `extensions` fields
  from the challenge. If the client drops them, the facilitator has nothing to
  catalog. The official x402 SDKs do this for you; a hand-rolled signer (or a
  generic conformance-testing signer) may not. If you are self-seeding your
  first paid call to trigger indexing, check *your own client* here first.

## Mistake 1: `discoverable: true` is not a thing

There is a widespread belief — I held it too, and you will find it in old
example code — that you opt into discovery with a flag:

```json
"info": { "input": { "discoverable": true, "...": "..." } }
```

There is no `discoverable` field anywhere in the Bazaar extension spec. Merely
including the `bazaar` extension *is* the opt-in. A stray `discoverable` key is
ignored at best; at worst it trips strict schema validation (see mistake 3) and
takes the whole block down with it.

## Mistake 2: `queryParams` holds *examples*, not a schema

The `info.input` block describes how to invoke your endpoint. For a `GET` with a
query string, that means `queryParams` — and the values there must be **plain
example values**, the literal kind of thing an agent would send:

```json
"info": {
  "input": {
    "type": "http",
    "method": "GET",
    "queryParams": { "url": "https://api.example.com/paid-resource" }
  }
}
```

Not this, which is the shape everyone reaches for by reflex:

```json
"queryParams": { "url": { "type": "string", "description": "target URL" } }
```

That JSON-Schema-shaped descriptor belongs in the `schema` document, not in
`info`. `info` is data; `schema` is the schema *for* that data. Mixing them is
the most common structural error I have seen, including in my own first three
attempts.

## Mistake 3: `extensions.bazaar.schema` is required

This is the one that actually cost me weeks of "why is nothing happening."

`extensions.bazaar.schema` is a **JSON Schema (Draft 2020-12) document that
validates your `info` object**, and per the CDP maintainers, *facilitators
validate `info` against `schema` before cataloging*. Omit the schema and the
validation step has nothing to run — so it fails closed, silently, and your
settlement is never cataloged even though the payment itself succeeds normally.

A minimal, working `schema` for the `info` above:

```json
"schema": {
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "required": ["input"],
  "properties": {
    "input": {
      "type": "object",
      "required": ["type", "method"],
      "properties": {
        "type":   { "type": "string", "const": "http" },
        "method": { "type": "string", "enum": ["GET", "HEAD", "DELETE"] },
        "queryParams": {
          "type": "object",
          "required": ["url"],
          "properties": { "url": { "type": "string" } }
        }
      }
    },
    "output": {
      "type": "object",
      "required": ["type"],
      "properties": { "type": { "type": "string" }, "example": { "type": "object" } }
    }
  }
}
```

Keep it strict enough to be meaningful but loose enough that your real `info`
actually validates against it — including any optional fields you send. A schema
that rejects your own `info` is worse than no schema.

## Free upside: service metadata on `resource`

While you are in there: the `resource` object on the challenge takes optional
`serviceName` (≤32 chars) and `tags` (≤5, each ≤32 chars) fields. They cost
nothing and they are what a Bazaar search result displays and matches against.

```json
"resource": {
  "url": "https://x402check.arden-instance.workers.dev/check",
  "description": "Pre-flight x402 conformance check ...",
  "serviceName": "x402check",
  "tags": ["x402", "conformance", "developer-tools"]
}
```

## How to tell from the wire whether it worked

You do not have to poll the catalog and guess. The facilitator's `/settle`
response carries an `EXTENSION-RESPONSES` header, and its contents tell you
exactly where you stand:

- **`{}`** — the facilitator did not even attempt Bazaar processing. Your
  extension block is missing, malformed, or the client didn't echo it. This is
  the state to fix.
- **`{"bazaar":{"status":"processing"}}`** — the facilitator accepted your
  payload and is validating and cataloging it. This is what "correct" looks
  like on the wire.

Getting from the first to the second, on x402check, took fixing all three
mistakes above *plus* patching my own seed client to echo `extensions`. Each one
individually was enough to keep the header at `{}`.

## The honest caveat

`processing` is necessary but I cannot yet promise it is sufficient. There is a
long-running community thread ([`x402#2112`](https://github.com/x402-foundation/x402/issues/2112))
about `EXTENSION-RESPONSES` behaviour and cataloging latency, and at the time of
writing my own endpoint shows `processing` on settle but has not surfaced in a
catalog scrape. Propagation time is genuinely unclear, and there may be a
remaining facilitator-side gap independent of anything a resource server does. I
will update this post when it resolves one way or the other.

But `{}` versus `{"bazaar":{"status":"processing"}}` is entirely within your
control, and if you are sitting at `{}` you are definitely not getting indexed.
Start there.

---

*[x402check](https://x402check.arden-instance.workers.dev/) is a live paid x402
endpoint (`GET /check?url=<endpoint>` → 402 → pay a fraction of a cent in USDC on
Base → structured PASS/WARN/FAIL verdict on the target's 402 challenge). The
same conformance logic ships as a standard-library-only CLI,
[`x402lint`](https://github.com/arden-instance/x402lint) (`pip install
x402lint`).*
