"""Platform-administrator helpers: who may run RouteBridge itself, and the append-only record of what they did."""
from typing import Any

from sqlmodel import Session, select

from routebridge.config.settings import get_settings
from routebridge.models.platform import PlatformAdmin, PlatformAuditEvent


def is_platform_admin(session: Session, subject: str | None) -> bool:
    """Admins come from the database; ROUTEBRIDGE_PLATFORM_ADMIN_SUBJECTS (user ids) and ROUTEBRIDGE_PLATFORM_ADMIN_EMAILS are the
    bootstrap lists that always apply. An email only counts once it is proven, so typing the admin's address into the sign-up form
    makes nobody an admin."""
    if not subject:
        return False
    settings = get_settings()
    if subject in settings.platform_admin_subjects:
        return True
    if session.exec(select(PlatformAdmin).where(PlatformAdmin.clerk_user_id == subject)).first() is not None:
        return True
    emails = set(settings.platform_admin_emails)
    if settings.owner_email.strip():
        emails.add(settings.owner_email.strip().lower())
    if emails:
        from routebridge.models.access import User

        user = session.exec(select(User).where(User.clerk_user_id == subject)).first()
        return bool(user and user.email_verified and user.email and user.email.lower() in emails)
    return False


def admin_count(session: Session) -> int:
    subjects = set(get_settings().platform_admin_subjects)
    subjects.update(a.clerk_user_id for a in session.exec(select(PlatformAdmin)).all())
    return len(subjects)


def record_platform_event(session: Session, actor: str | None, action: str, target_type: str, target_id: str, payload: dict[str, Any] | None = None) -> None:
    session.add(PlatformAuditEvent(actor=actor or "local-dev", action=action, target_type=target_type, target_id=str(target_id), payload=payload or {}))
