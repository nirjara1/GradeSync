from __future__ import annotations

from typing import Any

from .models import AuditEvent


def log_audit(
    action: str,
    *,
    detail: str = "",
    object_repr: str = "",
    actor: Any = None,
) -> None:
    AuditEvent.objects.create(
        action=action[:64],
        detail=detail[:4000] if detail else "",
        object_repr=object_repr[:255] if object_repr else "",
        actor=actor if getattr(actor, "is_authenticated", False) else None,
    )
