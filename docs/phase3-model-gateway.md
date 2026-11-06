# Phase 3 model gateway

Implemented and offline-verified on 2026-11-06. The provider-independent application
gateway accepts immutable text requests and returns text plus input/output token usage.
Mock and OpenAI adapters implement the same protocol and pass shared contract tests.
OpenAI is exercised with HTTPX MockTransport; no paid inference or model access is claimed.

The adapter sends a text-only POST to the fixed HTTPS Responses API, with `store=false`
and a bounded `max_output_tokens`. It extracts message output text rather than assuming
the first output item is a message. See the official [text generation guide](https://developers.openai.com/api/docs/guides/text)
and [Responses reference](https://developers.openai.com/api/reference/resources/responses/methods/create).
HTTPX 0.28.1 is promoted from a development dependency to runtime; its already-locked
version and transitive dependencies are unchanged. No OpenAI SDK is needed for this
small HTTP boundary.

## Run locally

Development selection (2026-11-06): `gpt-5.6-luna` with reasoning effort `none` and
256 output tokens. [Official model documentation](https://developers.openai.com/api/docs/models/gpt-5.6-luna)
lists $0.20 per million input tokens and $1.20 per million output tokens. The conservative
integer accounting rates are 1 and 2 micro-USD per token. The configured 20,000 micro-USD
budget is $0.02 per CLI invocation, not a shared cap on the user's $5 credit balance.
For example, 1,000 input plus 256 output tokens costs approximately $0.000507 at listed
rates (before any applicable taxes or other charges). Model access still needs a live check.

Paste your key only into `OPENAI_API_KEY=` in ignored `apps/api/api.env`. The local
non-secret settings are prepared there; never paste the key into chat or tracked files.

From the repository root, the mock probe works without credentials:

```powershell
'Synthetic evidence: HTTP errors increased after a deployment.' | .\.venv\Scripts\python.exe -m scripts.model_probe
```

For real inference, configure the commented variables from `apps/api/.env.example`
in ignored `apps/api/api.env`. Set OPENAI_API_KEY, INCIDENTIQ_MODEL, input/output
micro-USD rates and the invocation budget explicitly. Verify the chosen model supports
text Responses and check its current pricing. One micro-USD is one millionth of a US
dollar. Convert each per-token price to micro-USD and round upward to a positive integer;
use the uncached input rate. Missing/invalid configuration fails before network access.
No model or current provider prices are silently assumed.

```powershell
'Synthetic evidence: HTTP errors increased after a deployment.' | .\.venv\Scripts\python.exe -m scripts.model_probe --provider openai
```

This command submits stdin to OpenAI and may incur charges. Its output is unverified
model text, not a root-cause finding. The CLI never reads incidents/logs from the database.
Credentials, prompts and generated text are excluded from object reprs and are not
logged by this implementation. Output text is intentionally printed to the local terminal.

## Boundaries and limits

- Input is capped at 16,000 combined UTF-8 bytes; output allowance is 16–2,048 tokens.
  The CLI requests 256 output tokens. Responses are capped at 256 KiB and returned text
  at 64 KiB. Refusals, incomplete responses, invalid usage and empty text fail safely.
- Cost accounting uses integer arithmetic and a lock. Before I/O, reserve the combined
  UTF-8 byte count plus 256 framing tokens at the input rate, plus the full output cap.
  This is a conservative allowance for plain text, not a provider tokenizer or billing
  guarantee. Usage exceeding the allowance is rejected and the reservation retained.
- Success refunds the difference between reserved and reported usage at configured
  rates. Errors and timeouts retain the full reservation because billing is uncertain.
  There are no automatic retries, redirects, environment proxies, custom provider URLs,
  conversation history, tools or streaming model output.
- HTTPX enforces connect/read/write/pool inactivity timeouts, default 20 seconds and
  configurable up to 60. An elapsed-time check between response chunks also rejects
  late responses. This is not a strict wall-clock cancellation guarantee: an in-progress
  I/O operation can take its configured timeout before control returns.
- Budget is per gateway instance and in memory. CLI invocations start a new budget;
  this is not a durable daily, account-wide or multi-process spending cap. Configure
  provider-side spending controls separately. Incorrect/stale configured rates cannot
  establish a real dollar cap.

Inference is available as a backend library and explicit CLI only. No API route, UI,
startup inference, database migration, retrieval or investigation workflow is introduced.
Authentication remains a separate milestone; later HTTP integration must establish
identity and durable budget scope before exposing paid inference.

## Verification

- Full offline backend regression: 116 passed, 5 database tests deselected.
- Ruff lint passed; formatting passed for 48 files; pip dependency consistency passed.
- Explicit mock CLI smoke check passed without a provider request.
- 26 new tests cover shared adapter contract, exact wire payload, usage/cost refunds,
  concurrent reservations, no-call budget rejection, retained reservations on failures,
  timeout/error redaction, no retry/redirect, response limits, malformed responses,
  refusal/incomplete handling and invalid request/pricing limits.
- Existing Starlette/HTTPX TestClient deprecation warning remains.

Live update 2026-11-06: one synthetic request using `gpt-5.6-luna` with reasoning
disabled succeeded through the CLI after restoring missing non-secret model settings.
The saved key was detected without displaying it. The sandbox attempt failed with
`model_unavailable`; the permitted outside-sandbox request returned a short, cautious
investigation suggestion. This confirms credential/model access and the real response
parsing path. Actual billed cost and remaining credit balance were not measured;
end-to-end network timeout behavior remains unverified. No live database tests or
ingestion drills were rerun for this backend-only milestone.
