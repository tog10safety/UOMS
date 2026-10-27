from django.contrib import admin

from .models import Aircraft, Flight, FlightCrewAssignment, FlightWaypoint


@admin.register(Aircraft)
class AircraftAdmin(admin.ModelAdmin):
    list_display = ('tail_number', 'aircraft_type', 'flying_status', 'base_unit', 'is_active')
    list_filter = ('flying_status', 'is_active')
    search_fields = ('tail_number', 'aircraft_type', 'manufacturer')
    autocomplete_fields = ('base_unit',)


class FlightCrewAssignmentInline(admin.TabularInline):
    model = FlightCrewAssignment
    extra = 1
    autocomplete_fields = ('personnel',)


class FlightWaypointInline(admin.TabularInline):
    model = FlightWaypoint
    extra = 1


@admin.register(Flight)
class FlightAdmin(admin.ModelAdmin):
    list_display = ('flight_number', 'aircraft', 'origin', 'destination', 'status', 'scheduled_departure')
    list_filter = ('status',)
    search_fields = ('flight_number', 'origin', 'destination', 'caap_flight_plan_number')
    autocomplete_fields = ('aircraft', 'mission', 'unit')
    inlines = [FlightCrewAssignmentInline, FlightWaypointInline]


@admin.register(FlightCrewAssignment)
class FlightCrewAssignmentAdmin(admin.ModelAdmin):
    list_display = ('flight', 'personnel', 'crew_role')
    autocomplete_fields = ('flight', 'personnel')
