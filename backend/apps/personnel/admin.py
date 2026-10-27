from django.contrib import admin

from .models import Personnel, Position, Qualification, Rank, Section, Unit


@admin.register(Rank)
class RankAdmin(admin.ModelAdmin):
    list_display = ('abbreviation', 'name', 'order', 'is_active')
    search_fields = ('abbreviation', 'name')
    ordering = ('order',)


@admin.register(Unit)
class UnitAdmin(admin.ModelAdmin):
    list_display = ('code', 'name', 'category', 'parent_unit', 'is_active')
    list_filter = ('category', 'is_active')
    search_fields = ('code', 'name')
    autocomplete_fields = ('parent_unit',)


@admin.register(Section)
class SectionAdmin(admin.ModelAdmin):
    list_display = ('name', 'code', 'unit', 'is_active')
    list_filter = ('unit',)
    search_fields = ('name', 'code')
    autocomplete_fields = ('unit',)


@admin.register(Position)
class PositionAdmin(admin.ModelAdmin):
    list_display = ('title', 'is_active')
    search_fields = ('title',)


@admin.register(Qualification)
class QualificationAdmin(admin.ModelAdmin):
    list_display = ('name', 'validity_period_days', 'is_active')


@admin.register(Personnel)
class PersonnelAdmin(admin.ModelAdmin):
    list_display = ('service_number', 'last_name', 'first_name', 'rank', 'unit', 'status', 'is_active')
    list_filter = ('status', 'unit', 'rank', 'is_active')
    search_fields = ('service_number', 'first_name', 'last_name', 'email')
    autocomplete_fields = ('rank', 'unit', 'position')
    filter_horizontal = ('qualifications',)
