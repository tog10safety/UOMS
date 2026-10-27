from django.urls import path

from .views import ReportDataView, ReportExportView, ReportListView

urlpatterns = [
    path('', ReportListView.as_view(), name='report-list'),
    path('<str:report_type>/', ReportDataView.as_view(), name='report-data'),
    path('<str:report_type>/export/', ReportExportView.as_view(), name='report-export'),
]
