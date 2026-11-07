"""Local high-entropy token identities and explicit application permissions."""

from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True)
class Principal:
    user_id: UUID
    tenant_id: UUID
    scopes: frozenset[str]

    def permits(self, scope: str) -> bool:
        return scope in self.scopes


class AccessDenied(Exception):
    pass
