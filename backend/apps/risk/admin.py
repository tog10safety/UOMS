from django.contrib import admin

from .models import RiskAlert


@admin.register(RiskAlert)
class RiskAlertAdmin(admin.ModelAdmin):
    list_display = ('title', 'severity', 'mission', 'is_resolved', 'created_at')
    list_filter = ('severity', 'is_resolved')
    search_fields = ('title', 'description')
