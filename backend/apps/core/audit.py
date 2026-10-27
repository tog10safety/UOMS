"""Convenience helper for writing domain-specific audit log entries."""
from apps.core.models import AuditLog


def log_action(*, user, action, instance=None, description='', metadata=None, request=None):
    """
    Record a domain-specific audit event, e.g.:

        log_action(user=request.user, action=AuditLog.Action.APPROVE,
                   instance=mission_risk, description="Risk assessment approved")
    """
    ip_address = None
    if request is not None:
        forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        ip_address = forwarded_for.split(',')[0].strip() if forwarded_for else request.META.get('REMOTE_ADDR')

    AuditLog.objects.create(
        user=user,
        action=action,
        model_name=instance.__class__.__name__ if instance is not None else '',
        object_id=str(getattr(instance, 'pk', '')) if instance is not None else '',
        description=description,
        metadata=metadata or {},
        ip_address=ip_address,
    )
