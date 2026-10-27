from django.contrib import admin

from .models import (
    FeedbackNotification, Hazard, MissionHazard, MRMEvent, MRMFeedback, MRMForm, MRMPersonnel,
    SafetyOfficerAssignment, UnitLogo,
)


class MissionHazardInline(admin.TabularInline):
    model = MissionHazard
    extra = 0
    raw_id_fields = ('hazard',)


@admin.register(MRMForm)
class MRMFormAdmin(admin.ModelAdmin):
    list_display = ('mrm_number', 'activity_mission', 'unit', 'status', 'review_status', 'authority_level',
                    'total_percent', 'authority_approved', 'created_at')
    list_filter = ('status', 'review_status', 'authority_level', 'authority_approved', 'unit')
    search_fields = ('mrm_number', 'activity_mission', 'creator_name')
    inlines = [MissionHazardInline]
    raw_id_fields = ('mission', 'created_by', 'reviewed_by', 'authority_assigned_to', 'last_edited_by')


@admin.register(Hazard)
class HazardAdmin(admin.ModelAdmin):
    list_display = ('activity_code', 'hazard_description', 'unit', 'before_risk_rating', 'after_risk_rating', 'is_active')
    list_filter = ('unit', 'activity_code', 'is_active')
    search_fields = ('hazard_description', 'activity_code')


admin.site.register(MRMFeedback)
admin.site.register(MRMPersonnel)
admin.site.register(FeedbackNotification)
admin.site.register(MRMEvent)
admin.site.register(SafetyOfficerAssignment)
admin.site.register(UnitLogo)
