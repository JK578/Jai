"""Per-request identity; context is propagated into FastAPI worker threads."""

from contextvars import ContextVar

from incidentiq.domain.access import AccessDenied, Principal

current_principal: ContextVar[Principal | None] = ContextVar("incidentiq_principal", default=None)


def principal() -> Principal:
    value = current_principal.get()
    if value is None:
        raise AccessDenied("authentication_required")
    return value


def required_scope(method: str, path: str) -> str | None:
    if path.startswith("/api/v1/search"):
        return "search:run"
    if path.startswith("/api/v1/incidents"):
        return "incidents:write" if method != "GET" else "incidents:read"
    if path.startswith("/api/v1/investigations"):
        if path.endswith(("/approve", "/reject")):
            return "investigations:approve"
        return "investigations:read" if method == "GET" else "investigations:write"
    if path.startswith(("/api/v1/log", "/api/v1/search")):
        return "logs:read"
    return None
