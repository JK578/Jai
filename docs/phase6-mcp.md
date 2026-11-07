# Phase 6 — authenticated read-only MCP

Independent stdio JSON-RPC server: `incidentiq.mcp_server`, protocol 2025-11-25.
Initialize authenticates through the API; `notifications/initialized` completes startup.
Discovery follows verified scopes. Every call uses the protected API, preserving immediate
revocation and tenant policies.

| Tool | Scope | Bound |
|---|---|---|
| list_incidents | incidents:read | Latest 100 visible incidents |
| get_incident | incidents:read | One UUID |
| list_log_files | logs:read | Visible provenance catalog |
| read_logs | logs:read | File UUID, literal query up to 200 chars, max 20 rows |
| get_log | logs:read | One UUID with source detail |

Schemas reject unknown fields and incorrect types. No mutations, SQL, shell commands,
arbitrary URLs, paid model calls or approvals are exposed. Source results are marked
untrusted evidence. Input lines are bounded to 64 KiB and responses to 512 KiB.
Stdout contains only protocol JSON; configuration errors use stderr. Only loopback HTTP
APIs are accepted. This is not an internet MCP endpoint.

Configure a client's command as the absolute `.venv/Scripts/python.exe` path, arguments
`-m incidentiq.mcp_server`, working directory the repository root, and private environment:

```text
INCIDENTIQ_MCP_API=http://127.0.0.1:8000
INCIDENTIQ_MCP_TOKEN=<operator-issued access token>
```

Pass minimal system environment. The MCP child needs no OpenAI key or database URL.
Never commit a token in client configuration.

Tests cover lifecycle/authentication, scope-filtered discovery, strict arguments, SQL-tool
rejection and sanitized revocation errors. A real subprocess round trip against the
authenticated local API passed; see [the release receipt](local-release-validation.json).
