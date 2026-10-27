from django.contrib import admin

from apps.core.models import AuditLog


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ('created_at', 'user', 'action', 'method', 'path', 'ip_address')
    list_filter = ('action', 'method')
    search_fields = ('user__username', 'path', 'description', 'model_name', 'object_id')
    readonly_fields = [f.name for f in AuditLog._meta.fields]
    ordering = ('-created_at',)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser
