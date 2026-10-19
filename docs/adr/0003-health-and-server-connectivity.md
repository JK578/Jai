# ADR 0003: Separate health semantics; server-side connectivity

Status: Accepted

Decision: Liveness answers independently of readiness. Readiness is 503 before application
startup or when disabled by configuration; external dependencies do not yet exist.
Future required infrastructure checks need bounded timeouts and must not enter liveness.

Next.js calls readiness on its server using BACKEND_URL, with no caching and a 3-second
timeout. Render distinct ready, not-ready and unavailable states. No browser API calls
or CORS policy are needed for this slice. Retry is a page refresh, avoiding background polling.

Tradeoff: This checks the web-server-to-API connection, not a direct browser-to-API path.
It adds one bounded request per page render. There is no authentication or user data yet.
