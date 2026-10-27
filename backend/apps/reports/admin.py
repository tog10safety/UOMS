from django.contrib import admin

from .models import ReportExportLog


@admin.register(ReportExportLog)
class ReportExportLogAdmin(admin.ModelAdmin):
    list_display = ('report_type', 'format', 'generated_by', 'row_count', 'created_at')
    list_filter = ('report_type', 'format')
    readonly_fields = [f.name for f in ReportExportLog._meta.fields]
    ordering = ('-created_at',)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
