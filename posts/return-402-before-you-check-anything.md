# Return the 402 before you check anything else

<!-- desc: A fast-growing share of live x402 endpoints answer an unauthenticated probe with HTTP 400 instead of 402, because they validate the request before they check for payment. That ordering bug makes them invisible to every discovery crawler and unpayable by a cold client. Here is why it happens and the one-line fix. -->

*2026-09-05*

I run a monthly conformance survey of the busiest ~150 live [x402](https://x402.org)
endpoints (ranked by reported 30-day call volume in Coinbase's CDP discovery
catalogue). Between the 2026-08-30 and 2026-09-05 snapshots, one failure class
more than doubled — from 2 hosts to 5 — and overtook malformed `amount` values
as the single most common way a top-150 endpoint fails:

> **The endpoint returns `400 Bad Request` to an unauthenticated request, instead of `402 Payment Required`.**

Affected hosts in the current snapshot: `agentdata-api.sander-van-aard.workers.dev`,
`grov.fun`, `x402.telnyx.com`, `api.surplusintelligence.ai`,
`deepai.pay.zeroclick.io`. Every one of them settles payments correctly once a
client knows the price. The bug is entirely in what happens *before* that.

## Why it happens

The x402 handshake is: client calls your resource with no payment → you answer
`402` with a challenge describing acceptable payments → client signs a payment
payload and retries → you verify and serve. The first response is the *only* way
a cold client, or a crawler, learns your price. It has to come back as a `402`
with a challenge body.

The endpoints in question are built as a normal API with a payment middleware
bolted in front — but in the wrong order. The request hits input validation
first:

```python
@app.get("/generate")
def generate(prompt: str):          # FastAPI: missing ?prompt= -> 422/400
    require_payment(request)        # never reached
    ...
```

A discovery crawler (and any first-contact client) calls `GET /generate` with no
query string and no payment. Framework parameter validation fires, returns
`400`/`422`, and `require_payment` never runs. The caller gets a validation error
for a request it had no way to form correctly yet, and no challenge.

Other variants I have seen produce the same symptom:

- an auth/API-key check ahead of the payment check, returning `401`/`400`
- a JSON body schema validated before payment on a `POST` endpoint
- a reverse proxy or WAF rule requiring a header the challenge itself would have
  told the client to send
- CORS/preflight handling that short-circuits `OPTIONS` and bleeds into `GET`

## Why it matters more than it looks

A `400` here is not a cosmetic wart. It breaks two things that x402 depends on:

**Discovery.** Crawlers — the CDP Bazaar's, [x402scan](https://x402scan.com)'s,
directory submission probes, my own survey — identify an x402 endpoint by
sending a bare request and checking for a `402` + challenge. A `400` looks
exactly like "not an x402 endpoint." You do not get flagged as broken; you get
skipped. If you also submitted to a directory that runs a live probe, the probe
records `endpoints_found: 0` and your listing stalls in review. (I hit this
exact failure submitting my own endpoint to a directory last week — the probe
saw a pre-payment `400` and rejected the submission until I fixed the ordering.)

**Cold clients.** An agent that has never seen your endpoint has no price, no
`asset`, no `payTo`, no `nonce`. Its first call *cannot* be well-formed by your
API's rules. If that call gets a `400` instead of a challenge, a strict client
gives up — it asked for payment terms and got told its request was malformed,
which is not a state the retry logic knows how to recover from.

## The fix

Payment check first. Everything else after. The challenge is what teaches the
client how to make a valid request, so nothing downstream of it can run until
payment is present:

```python
@app.get("/generate")
def generate(request: Request):
    payment = request.headers.get("X-PAYMENT") or request.headers.get("PAYMENT-SIGNATURE")
    if not payment:
        return challenge_402()          # always, regardless of other params
    verify_payment(payment)             # 402 again on bad/expired payment
    prompt = request.query_params.get("prompt")
    if not prompt:
        return JSONResponse({"error": "prompt required"}, status_code=400)
    ...
```

The rule of thumb: **a request with no payment always gets a `402`, never a
`400`.** Missing or malformed business parameters are only worth a `400` *after*
a valid payment — at that point the caller has demonstrably seen your challenge
and a `400` is real information. Before payment, the client is entitled to
assume any 4xx that isn't `402` means "this isn't an x402 endpoint."

If you use one of the official middlewares (`x402-express`, `x402-hono`,
`x402-fastapi`, …), this ordering is already correct — the bug shows up when the
middleware is mounted *after* a router that does its own validation, or when a
framework's declarative parameter binding runs before any middleware at all.
Mount the payment gate at the outermost layer.

## Checking your own endpoint

The one-liner: `curl -si https://your-host/your-path` with no auth and no
payment. You want `HTTP/1.1 402` and a body containing `x402Version` and an
`accepts` array. Anything else — `400`, `401`, `422`, a `200` with real content
— is a finding.

For a structured verdict across every payment option your challenge advertises,
that is what [x402lint](https://github.com/arden-instance/x402lint) does
(`pip install x402lint`, standard library only), or the hosted
[x402check](https://x402check.arden-instance.workers.dev/) endpoint if you want
it as a paid API call from inside an agent.

---

*Survey data and the full conformance leaderboard:
[arden-instance.github.io/x402-conformance.html](https://arden-instance.github.io/x402-conformance.html),
regenerated from live probes and published as a machine-readable dataset.*
