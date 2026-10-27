"""
Notification delivery.

Notifications are created inside `transaction.on_commit`, so they are only ever sent for changes that actually
persisted — a rolled-back mission submission never notifies anyone. A delivery failure is logged and never
breaks (or rolls back) the business operation that triggered it.
"""
import logging

from django.db import IntegrityError, transaction

logger = logging.getLogger(__name__)


def _create(user_id, kind, title, message, link, dedupe_key, metadata):
    from .models import Notification

    try:
        with transaction.atomic():
            Notification.objects.create(
                user_id=user_id, kind=kind, title=title[:200], message=message, link=link[:300],
                dedupe_key=dedupe_key or '', metadata=metadata or {},
            )
    except IntegrityError:
        logger.info('Notification %s for user %s already delivered — skipped', dedupe_key, user_id)
    except Exception:  # noqa: BLE001 — never let delivery break the caller
        logger.exception('Could not deliver notification "%s" to user %s', title, user_id)


def notify(users, kind, title, message='', link='', dedupe_key='', metadata=None):
    """Queue one notification per distinct user; delivered after the current transaction commits."""
    seen = set()
    for user in users:
        if user is None or user.pk in seen or not getattr(user, 'is_active', True):
            continue
        seen.add(user.pk)
        transaction.on_commit(
            lambda uid=user.pk: _create(uid, kind, title, message, link, dedupe_key, metadata)
        )
