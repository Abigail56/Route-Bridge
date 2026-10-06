"""Platform-administrator helpers: who may run RouteBridge itself, and the append-only record of what they did."""
from typing import Any

from sqlmodel import Session, select

from routebridge.config.settings import get_settings
from routebridge.models.platform import PlatformAdmin, PlatformAuditEvent


def is_platform_admin(session: Session, subject: str | None) -> bool:
    """Admins come from the database; ROUTEBRIDGE_PLATFORM_ADMIN_SUBJECTS is the bootstrap list that always applies."""
    if not subject:
        return False
    if subject in get_settings().platform_admin_subjects:
        return True
    return session.exec(select(PlatformAdmin).where(PlatformAdmin.clerk_user_id == subject)).first() is not None


def admin_count(session: Session) -> int:
    subjects = set(get_settings().platform_admin_subjects)
    subjects.update(a.clerk_user_id for a in session.exec(select(PlatformAdmin)).all())
    return len(subjects)


def record_platform_event(session: Session, actor: str | None, action: str, target_type: str, target_id: str, payload: dict[str, Any] | None = None) -> None:
    session.add(PlatformAuditEvent(actor=actor or "local-dev", action=action, target_type=target_type, target_id=str(target_id), payload=payload or {}))
