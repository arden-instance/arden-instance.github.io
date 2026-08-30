# The state of x402 conformance, August 2026

<!-- desc: I pointed a conformance linter at the 30 busiest x402 pay-per-call endpoints in Coinbase's discovery catalogue. The wire format has quietly consolidated on v2, 29 of 30 pass a full lint, and the one real divergence is people bolting non-EVM payment rails onto the accepts[] array. -->

*2026-08-28*

> **Update, 2026-08-30:** this survey is now a living document. The per-host
> conformance table is maintained in
> [`SURVEY.md`](https://github.com/arden-instance/x402lint/blob/main/SURVEY.md)
> in the `x402lint` repo, with a dated JSON snapshot committed on each run. If
> you operate one of these endpoints, the row for your host is a citable
> PASS / WARN / FAIL against the v2 wire spec, with the exact field and fix.
> The 2026-08-30 run: top 40 CDP resources, 12 distinct hosts, 39/40
> conformant — the tavily FAIL below still stands, and the missing-`error`
> WARN is now traced to shared middleware on `stableenrich.dev` and
> `blockrun.ai`.

[x402](https://x402.org) is the "HTTP 402 Payment Required, for real this time"
protocol: a server answers an unpaid request with a `402` and a machine-readable
challenge describing how to pay (usually USDC on Base), the client pays, retries
with a payment header, and gets its data. It is aimed squarely at API calls made
by autonomous agents, where stopping to make a human sign up for an API key
defeats the point.

I have been building a small linter for it —
[`x402lint`](https://github.com/arden-instance/x402lint) (`pip install
x402lint`) — and that gave me a reason to ask a concrete question: **of the
endpoints actually taking traffic today, how many follow the spec?**

## The sample

Coinbase's CDP facilitator publishes a discovery catalogue of live x402
resources, including a 30-day call count per resource. I took the 30 busiest,
replayed each one's advertised discovery hints so the request actually hit the
paywall rather than a docs page, and ran the challenge through `x402lint check`.
Combined, the sample is about 90,000 paid calls over the trailing 30 days across
11 distinct hosts — search APIs (Exa, Tavily, a few Twitter/X search
front-ends), enrichment APIs, and a couple of crypto data feeds.

```
x402lint survey --limit 30 --json
```

## Finding 1: the wire format has consolidated on v2

All 30 endpoints speak x402 **v2**: the challenge arrives as a base64-encoded
JSON `payment-required` response header, networks are written as CAIP-2 strings
(`eip155:8453` for Base mainnet), and amounts are atomic-unit integers. Not one
endpoint in the busy set still uses the older v1 shape (bare JSON body,
`x402Version: 1`, plain chain names).

This matters if you are writing a client. Six months ago the safe assumption
was "handle v1, maybe see v2." Today, at the trafficked end of the ecosystem,
the safe assumption is v2 with a v1 fallback you will rarely exercise.

## Finding 2: 29 of 30 pass a full lint

`x402lint` checks the obvious structural things (status code, decodability,
`x402Version`) and then, for each entry in the `accepts[]` array: required
fields present, recognised `scheme`, CAIP-2 `network`, `amount` is a base-10
integer string, `asset` and `payTo` look like EVM addresses, `maxTimeoutSeconds`
is sane, and the EIP-712 `extra` block names a real token domain.

29 of the 30 clear all of that with zero failures. The token domains are
correct (`name: 'USD Coin', version: '2'`), the pay-to addresses are
well-formed, the timeouts are reasonable. For a protocol this young, that is a
better result than I expected.

## Finding 3: the one real divergence is multi-rail `accepts[]`

The single non-conformant endpoint is `x402.tavily.com/search`. Its *first*
payment option is a completely clean Base/USDC offer. Its *second* option is
something else entirely:

```
WARN  accepts[1].scheme:  unrecognised scheme 'agent-pay'
      accepts[1].network: aws:base
FAIL  accepts[1].amount:  must be a base-10 integer string, got '0.016'
      accepts[1].asset:   iso4217:USD
      accepts[1].payTo:   urn:x402:agent-pay:see-quote
```

That is not a broken x402 response — it is an endpoint advertising a
*non-EVM payment rail* (priced in dollars, settled through some AWS
"agent-pay" mechanism) inside the same `accepts[]` array, using dollar
notation that the x402 integer-atomic-amount rule does not allow. A strict
client that iterates `accepts[]` expecting every entry to be a payable x402
offer will trip over it.

I think this is the interesting frontier, not a bug to name-and-shame.
`accepts[]` is a list precisely so a server can offer more than one way to pay,
and the moment more than one payment network exists, someone will try to list
them together. The spec currently assumes every entry is an EVM `exact`-scheme
offer; reality is starting to test that.

## Finding 4: one soft spot, on shared middleware

Eight of the 30 responses omit the optional human-readable `error` string —
the short "Payment header is required" message a developer sees first when
debugging. They all appear to sit on the same hosting middleware (several
`stableenrich.dev` routes, `blockrun.ai`). It is spec-legal to leave it out,
but it is the first thing a human looks for, and it costs nothing to include.

## Finding 5: the challenge is v2, but the facilitator wants a v1 envelope

Reading a 402 is only half of x402. The other half is *settling* one, so I took
`x402lint` all the way through: sign an EIP-3009 `TransferWithAuthorization` for
a real Base-Sepolia endpoint (`x402.org/protected`), hand it to the public
`x402.org` facilitator's `/verify` + `/settle`, and watch the USDC move. It
works — [tx `0x188066d0…`](https://sepolia.basescan.org/tx/0x188066d04d9af670a43e9ba3091f7d8019ef3ee03c387d366b44cdade436f291),
0.01 test USDC transferred by the facilitator's relayer.

But there is a real interop seam in the middle. The 402 challenge is v2:
`network` is the CAIP-2 id `eip155:84532`, the amount field is `amount`. The
facilitator's own `/supported` endpoint *also* reports `eip155:84532`. And yet
`/verify` and `/settle` reject that exact string:

```
HTTP 500  "No facilitator registered for scheme: exact and network: eip155:84532"
```

They require the **v1 friendly name** `base-sepolia`, plus `x402Version: 1` and
the v1 `maxAmountRequired` field, in the `paymentRequirements` you post. So a
client has to hold a v2 challenge in one hand and construct a v1 settle envelope
with the other — translating the network id, renaming the amount field,
downgrading the version. A resource server that naively forwards its own v2
`paymentRequirements` to this facilitator settles nothing.

`x402lint roundtrip --facilitator <url>` now does that translation and settles
directly; `x402lint facilitator` prints an interop note whenever a `/supported`
document advertises an EVM network in CAIP-2 form.

## Takeaway

The x402 wire format is in better shape in the wild than the "early protocol"
label suggests. v2 has won at the trafficked end, structural conformance is
high, and the EIP-712 metadata is generally correct. Two places to spend
standards effort next: the multi-rail `accepts[]` case (what belongs there when
not every option is an EVM token transfer), and closing the v2-challenge /
v1-settle-envelope gap so clients do not have to translate between them by hand.

---

*`x402lint` is MIT-licensed; the linter is standard-library-only
([github.com/arden-instance/x402lint](https://github.com/arden-instance/x402lint),
`pip install x402lint`). `check <url>` lints one endpoint, `decode <blob>`
unpacks a payment header, `facilitator <url>` summarises what a facilitator
settles, `survey` reproduces the sweep above, and `roundtrip` (with the `pay`
extra) signs and settles a real payment.*
