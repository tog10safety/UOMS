"""
Audit logging middleware.

Every state-changing request (POST/PUT/PATCH/DELETE) hitting `/api/` is
recorded to the AuditLog table with the acting user, IP address, HTTP
method/path, and the response status. This gives a base layer of
accountability that individual views can enrich with more specific
`description`/`metadata` via `apps.core.audit.log_action`.
"""
from apps.core.models import AuditLog

STATE_CHANGING_METHODS = {'POST', 'PUT', 'PATCH', 'DELETE'}


def get_client_ip(request):
    forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if forwarded_for:
        return forwarded_for.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR')


class AuditLogMiddleware:
    """Logs every state-changing API call after the response is generated."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)

        if request.path.startswith('/api/') and request.method in STATE_CHANGING_METHODS:
            user = request.user if getattr(request, 'user', None) and request.user.is_authenticated else None
            try:
                AuditLog.objects.create(
                    user=user,
                    action=AuditLog.Action.OTHER,
                    method=request.method,
                    path=request.path,
                    ip_address=get_client_ip(request),
                    description=f'{request.method} {request.path} -> {response.status_code}',
                    metadata={'status_code': response.status_code},
                )
            except Exception:
                # Audit logging must never break the request/response cycle.
                pass

        return response
