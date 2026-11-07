"""Revocable local tokens and transaction-local tenant scope for the runtime role."""

import hashlib
import hmac
import json
import time
from contextlib import contextmanager
from pathlib import Path
from uuid import UUID

from sqlalchemy import text

from incidentiq.domain.access import AccessDenied, Principal


class TokenRegistry:
    def __init__(self, path: Path):
        self.path = path

    def authenticate(self, token: str) -> Principal:
        if not 32 <= len(token) <= 256:
            raise AccessDenied("authentication_required")
        digest = hashlib.sha256(token.encode()).hexdigest()
        try:
            entries = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(entries, list) or len(entries) > 100:
                raise ValueError
            matched = None
            for entry in entries:
                if hmac.compare_digest(entry["token_sha256"], digest):
                    matched = entry
            if matched is None or matched.get("revoked") or matched["expires_at"] <= time.time():
                raise AccessDenied("authentication_required")
            return Principal(
                UUID(matched["user_id"]), UUID(matched["tenant_id"]), frozenset(matched["scopes"])
            )
        except AccessDenied:
            raise
        except Exception:
            raise AccessDenied("authentication_required") from None


class ScopedSessions:
    def __init__(self, factory, principal: Principal):
        self.factory, self.principal = factory, principal

    def configure(self, session):
        session.execute(
            text("SELECT set_config('incidentiq.tenant_id', :tenant, true)"),
            {"tenant": str(self.principal.tenant_id)},
        )

    @contextmanager
    def __call__(self):
        with self.factory() as session:
            self.configure(session)
            yield session

    @contextmanager
    def begin(self):
        with self.factory.begin() as session:
            self.configure(session)
            yield session
