from django.contrib import admin

from .models import Trip, Vehicle, VehicleLocationUpdate, VehicleMaintenanceRecord


@admin.register(Vehicle)
class VehicleAdmin(admin.ModelAdmin):
    list_display = ('plate_number', 'vehicle_type', 'status', 'assigned_driver', 'assigned_mission', 'is_active')
    list_filter = ('status', 'vehicle_type', 'is_active')
    search_fields = ('plate_number', 'make', 'model')
    autocomplete_fields = ('assigned_driver', 'assigned_mission')


@admin.register(VehicleLocationUpdate)
class VehicleLocationUpdateAdmin(admin.ModelAdmin):
    list_display = ('vehicle', 'recorded_at', 'speed_kph', 'heading_degrees')
    list_filter = ('vehicle',)
    ordering = ('-recorded_at',)


@admin.register(Trip)
class TripAdmin(admin.ModelAdmin):
    list_display = ('vehicle', 'driver', 'origin', 'destination', 'status', 'start_time', 'end_time')
    list_filter = ('status', 'vehicle')
    search_fields = ('origin', 'destination')
    autocomplete_fields = ('vehicle', 'driver', 'mission')


@admin.register(VehicleMaintenanceRecord)
class VehicleMaintenanceRecordAdmin(admin.ModelAdmin):
    list_display = ('vehicle', 'maintenance_type', 'service_date', 'next_due_date', 'cost')
    list_filter = ('maintenance_type',)
    autocomplete_fields = ('vehicle',)
