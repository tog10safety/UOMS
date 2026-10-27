from django.contrib import admin

from .models import AORBoundary, Checkpoint, LandingZone, MapHazard, MapLayer, Route


@admin.register(AORBoundary)
class AORBoundaryAdmin(admin.ModelAdmin):
    list_display = ('name', 'unit', 'is_active')
    search_fields = ('name',)
    autocomplete_fields = ('unit',)


@admin.register(Checkpoint)
class CheckpointAdmin(admin.ModelAdmin):
    list_display = ('name', 'checkpoint_type', 'unit', 'is_operational', 'is_active')
    list_filter = ('checkpoint_type', 'is_operational')
    search_fields = ('name',)
    autocomplete_fields = ('unit',)


@admin.register(LandingZone)
class LandingZoneAdmin(admin.ModelAdmin):
    list_display = ('name', 'lz_type', 'status', 'unit', 'is_active')
    list_filter = ('lz_type', 'status')
    search_fields = ('name',)
    autocomplete_fields = ('unit',)


@admin.register(MapHazard)
class MapHazardAdmin(admin.ModelAdmin):
    list_display = ('name', 'hazard_type', 'severity', 'is_resolved', 'is_active')
    list_filter = ('hazard_type', 'severity', 'is_resolved')
    search_fields = ('name',)
    autocomplete_fields = ('reported_by',)


@admin.register(Route)
class RouteAdmin(admin.ModelAdmin):
    list_display = ('name', 'route_type', 'unit', 'is_active')
    list_filter = ('route_type',)
    search_fields = ('name',)
    autocomplete_fields = ('unit',)


@admin.register(MapLayer)
class MapLayerAdmin(admin.ModelAdmin):
    list_display = ('name', 'layer_type', 'is_visible_by_default', 'is_active')
