from django.utils import timezone
from rest_framework import mixins, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from .models import Notification


def serialize_notification(n):
    return {
        'id': str(n.id), 'kind': n.kind, 'title': n.title, 'message': n.message, 'link': n.link,
        'is_read': n.is_read, 'created_at': n.created_at, 'metadata': n.metadata,
    }


class NotificationViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    """A user only ever sees and changes their own notifications."""

    def get_queryset(self):
        return Notification.objects.filter(user=self.request.user, is_active=True)

    def list(self, request):
        qs = self.get_queryset()
        if request.query_params.get('unread') in ('1', 'true'):
            qs = qs.filter(is_read=False)
        page = self.paginate_queryset(qs)
        return self.get_paginated_response([serialize_notification(n) for n in page])

    @action(detail=False, methods=['get'], url_path='unread-count')
    def unread_count(self, request):
        return Response({'count': self.get_queryset().filter(is_read=False).count()})

    @action(detail=True, methods=['post'], url_path='read')
    def mark_read(self, request, pk=None):
        n = self.get_queryset().filter(pk=pk).first()
        if n is None:
            return Response({'detail': 'Not found.'}, status=404)
        if not n.is_read:
            n.is_read, n.read_at = True, timezone.now()
            n.save(update_fields=['is_read', 'read_at', 'updated_at'])
        return Response(serialize_notification(n))

    @action(detail=False, methods=['post'], url_path='read-all')
    def mark_all_read(self, request):
        updated = self.get_queryset().filter(is_read=False).update(is_read=True, read_at=timezone.now())
        return Response({'updated': updated})
