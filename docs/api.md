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
