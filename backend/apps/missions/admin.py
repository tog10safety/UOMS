from django.contrib import admin

from .models import HazardAssessment, Mission, MissionApprovalLog


class HazardAssessmentInline(admin.TabularInline):
    model = HazardAssessment

    # Legacy quick assessments are frozen once the mission's risk is owned by an MRM form.
    def has_add_permission(self, request, obj=None):
        return obj is None or obj.active_mrm is None

    def has_change_permission(self, request, obj=None):
        return obj is None or obj.active_mrm is None

    def has_delete_permission(self, request, obj=None):
        return obj is None or obj.active_mrm is None

    extra = 1
    readonly_fields = ('initial_risk_level', 'residual_risk_level')
    fields = (
        'hazard_description', 'category', 'probability', 'severity', 'initial_risk_level',
        'existing_controls', 'additional_controls', 'residual_probability', 'residual_severity',
        'residual_risk_level', 'is_active',
    )


class MissionApprovalLogInline(admin.TabularInline):
    model = MissionApprovalLog
    extra = 0
    readonly_fields = ('action', 'actor', 'comments', 'created_at')
    can_delete = False


@admin.register(Mission)
class MissionAdmin(admin.ModelAdmin):
    list_display = ('name', 'status', 'risk_review_status', 'unit', 'mission_commander', 'start_date', 'is_active')
    list_filter = ('status', 'risk_review_status', 'unit', 'is_active')
    search_fields = ('name', 'description')
    autocomplete_fields = ('unit', 'mission_commander')
    # risk-review fields are a read-only projection of the MRM form (see apps.mrm / check_mrm_consistency)
    readonly_fields = ('risk_review_status', 'submitted_by', 'submitted_at', 'reviewed_by', 'reviewed_at', 'review_comments')
    inlines = [HazardAssessmentInline, MissionApprovalLogInline]


@admin.register(HazardAssessment)
class HazardAssessmentAdmin(admin.ModelAdmin):
    list_display = ('mission', 'category', 'probability', 'severity', 'initial_risk_level', 'residual_risk_level')
    list_filter = ('category', 'initial_risk_level')
    readonly_fields = ('initial_risk_level', 'residual_risk_level')
    autocomplete_fields = ('mission',)


@admin.register(MissionApprovalLog)
class MissionApprovalLogAdmin(admin.ModelAdmin):
    list_display = ('mission', 'action', 'actor', 'created_at')
    list_filter = ('action',)
    readonly_fields = [f.name for f in MissionApprovalLog._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
