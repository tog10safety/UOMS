"""Root URL configuration for the UOMS project."""
from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularRedocView,
    SpectacularSwaggerView,
)

urlpatterns = [
    path('admin/', admin.site.urls),

    # Auth & user/role management
    path('api/v1/auth/', include('apps.accounts.urls')),

    # Domain modules
    path('api/v1/personnel/', include('apps.personnel.urls')),
    path('api/v1/vehicles/', include('apps.vehicles.urls')),
    path('api/v1/aircraft/', include('apps.aircraft.urls')),
    path('api/v1/missions/', include('apps.missions.urls')),
    path('api/v1/mrm/', include('apps.mrm.urls')),
    path('api/v1/', include('apps.core.urls')),
    path('api/v1/armory/', include('apps.armory.urls')),
    path('api/v1/inventory/', include('apps.inventory.urls')),
    path('api/v1/gis/', include('apps.gis.urls')),
    path('api/v1/reports/', include('apps.reports.urls')),
    path('api/v1/dashboard/', include('apps.dashboard.urls')),

    # API schema / documentation
    path('api/schema/', SpectacularAPIView.as_view(), name='schema'),
    path('api/docs/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
    path('api/redoc/', SpectacularRedocView.as_view(url_name='schema'), name='redoc'),
]
