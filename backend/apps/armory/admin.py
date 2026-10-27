from django.contrib import admin

from .models import AmmunitionIssuance, AmmunitionStock, ArmoryInspection, Firearm, FirearmIssuance


@admin.register(Firearm)
class FirearmAdmin(admin.ModelAdmin):
    list_display = ('serial_number', 'firearm_type', 'status', 'unit', 'accountable_personnel', 'is_active')
    list_filter = ('status', 'unit', 'is_active')
    search_fields = ('serial_number', 'firearm_type', 'make', 'model')
    autocomplete_fields = ('unit', 'accountable_personnel')


@admin.register(AmmunitionStock)
class AmmunitionStockAdmin(admin.ModelAdmin):
    list_display = ('ammunition_type', 'lot_number', 'unit', 'quantity_on_hand', 'unit_of_measure', 'expiration_date')
    list_filter = ('ammunition_type', 'unit')
    search_fields = ('ammunition_type', 'lot_number')
    autocomplete_fields = ('unit',)


@admin.register(FirearmIssuance)
class FirearmIssuanceAdmin(admin.ModelAdmin):
    list_display = ('firearm', 'issued_to', 'status', 'issue_date', 'return_date')
    list_filter = ('status',)
    autocomplete_fields = ('firearm', 'issued_to', 'issued_by')


@admin.register(AmmunitionIssuance)
class AmmunitionIssuanceAdmin(admin.ModelAdmin):
    list_display = ('ammunition_stock', 'issued_to', 'quantity', 'issue_date')
    autocomplete_fields = ('ammunition_stock', 'issued_to', 'issued_by')


@admin.register(ArmoryInspection)
class ArmoryInspectionAdmin(admin.ModelAdmin):
    list_display = ('firearm', 'inspection_date', 'inspected_by', 'result')
    list_filter = ('result',)
    autocomplete_fields = ('firearm', 'inspected_by')
