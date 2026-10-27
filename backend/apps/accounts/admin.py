from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin

from apps.accounts.models import User


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    ordering = ('username',)
    list_display = ('username', 'email', 'role', 'unit', 'is_active', 'is_staff')
    list_filter = ('role', 'unit', 'is_active', 'is_staff')
    search_fields = ('username', 'email', 'first_name', 'last_name')
    fieldsets = DjangoUserAdmin.fieldsets + (
        ('UOMS', {'fields': ('role', 'unit', 'phone_number', 'must_change_password', 'last_login_ip')}),
    )
    add_fieldsets = DjangoUserAdmin.add_fieldsets + (
        ('UOMS', {'fields': ('email', 'role', 'unit')}),
    )
