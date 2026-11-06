# Incident API v1

Backend: `http://127.0.0.1:8000`. OpenAPI UI: `/docs`; schema: `/openapi.json`.
The UI uses the same paths on its own origin via Next.js forwarding handlers.
This is a local, unauthenticated development API. Auto mode uses PostgreSQL when DATABASE_URL
is configured; explicit memory mode remains available for offline tests/demos.

| Method | Path | Success | Failure |
|---|---|---|---|
| POST | /api/v1/incidents | 201 incident; Location header | 422 invalid input |
| GET | /api/v1/incidents | 200 array, newest first; empty array when empty | — |
| GET | /api/v1/incidents/{incident_id} | 200 incident | 404 unknown UUID; 422 malformed UUID |
| GET | /health/live | 200 alive | — |
| GET | /health/ready | 200 ready | 503 not_ready |

In PostgreSQL mode readiness checks connectivity and the mapped incident table. Its existing
status/service fields are preserved, with an additive storage field (postgres or memory).
Readiness is a probe signal; it does not gate incident operations. Next.js additionally
returns 400 for malformed JSON and 502 for upstream 5xx/timeouts/network errors or
unreadable JSON. Backend malformed JSON returns 422. Successful incident and health
responses send `Cache-Control: no-store`.

Database failures return 503 with `{"detail":"Incident storage unavailable"}`; identity
conflicts return 409 with `{"detail":"Incident could not be stored"}`. Driver messages,
SQL and connection credentials are never included. The Next.js proxy sanitizes upstream
5xx responses to 502. There are no changes to incident request/response fields or success codes.

## Create request

```json
{
  "title": "Checkout unavailable",
  "description": "Checkout requests return HTTP 503.",
  "severity": "high",
  "service_name": "checkout-api"
}
```

Title, description and service_name are required strings, trimmed before checking lengths:
1–200, 1–10000 and 1–100 characters. Whitespace-only values are invalid. Severity values
are critical/high/medium/low; omitted severity defaults to medium. Extra fields are rejected.
Clients cannot supply id, status, created_at or updated_at.

## Incident response

```json
{
  "id": "9aa35438-6d8d-4f1d-b05a-3029b58197ce",
  "title": "Checkout unavailable",
  "description": "Checkout requests return HTTP 503.",
  "severity": "high",
  "status": "open",
  "service_name": "checkout-api",
  "created_at": "2026-10-19T12:00:00Z",
  "updated_at": "2026-10-19T12:00:00Z"
}
```

IDs are server-generated UUID4 values; timestamps are ISO 8601 UTC strings. Status values
are open/investigating/resolved; creation always starts open. Without update operations,
timestamps remain equal. Titles need not be unique. Unknown incidents return
`{"detail":"Incident not found"}`; validation errors use FastAPI's standard detail array.

## PowerShell example

```powershell
$body = @{
  title = 'Checkout unavailable'
  description = 'Checkout requests return HTTP 503.'
  severity = 'high'
  service_name = 'checkout-api'
} | ConvertTo-Json
$incident = Invoke-RestMethod 'http://127.0.0.1:8000/api/v1/incidents' -Method Post -ContentType 'application/json' -Body $body
Invoke-RestMethod 'http://127.0.0.1:8000/api/v1/incidents'
Invoke-RestMethod "http://127.0.0.1:8000/api/v1/incidents/$($incident.id)"
```

PostgreSQL data survives backend restart/reload. Explicit memory data does not. Use one worker.
Do not enter sensitive production incident data in this phase.

## Read-only log API (Phase 2B, requires migration 0002)

These routes are backend-only; no Next.js proxy or log UI is added. Default page size
is 50, maximum 100. Pages return `{"items": [...], "next_cursor": null}`; the next
cursor is provided only when another item exists. Missing schema/storage returns
`503 {"detail":"Log storage unavailable"}`. Invalid query values return 422 and unknown
detail IDs return 404. Owner tokens and raw database errors never appear in responses.

| GET path | Parameters and behavior |
|---|---|
| `/api/v1/log-datasets` | Approved manifest, deterministic dataset/file IDs and registered files |
| `/api/v1/log-ingestions` | Optional file_id, state; limit and bounded offset cursor (0..10000), newest first |
| `/api/v1/log-ingestions/{run_id}` | Counts, committed line, lease/heartbeat times, safe failure code; no ownership token |
| `/api/v1/log-ingestions/{run_id}/errors` | First 100 rejection diagnostics per run; source-line cursor; code/digest only, no raw data |
| `/api/v1/logs` | Required file_id; optional level, q (1..200 chars), from_local/to_local; limit, source-line cursor (0..2000) |
| `/api/v1/logs/{log_id}` | Full event including bounded raw_line; unknown ID 404 |

Event pages sort by physical source_line ascending, avoiding timestamp ties. List items
omit raw_line; detail retains it. `q` is a case-sensitive literal substring, with `%`, `_`
and escape characters escaped, not an SQL pattern or full-text search. All filters are
parameterized. Local-time bounds are inclusive, ordered, timezone-free ISO datetimes;
offsets and Z are rejected. No invented UTC conversion is offered. Normalized levels:
emergency, alert, critical, error, warning, notice, info, debug. Original level and timestamp
text remain separate fields; digests serialize as hex.

Run states: running, completed, partial (finished with rejected lines), failed. An expired
running lease is reported as interrupted without a read-side write. Resume uses the local
CLI, same run ID, exact file and parser version; successful completed/partial runs can be
re-ingested as a new audit run with duplicate counts. Run-history offset pages may shift
when new runs are added; event cursors remain stable. No sensitive raw error excerpts are
stored, and full rejection counts continue after the 100 diagnostic samples.
