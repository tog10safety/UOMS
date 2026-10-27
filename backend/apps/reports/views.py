from django.http import HttpResponse
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.audit import log_action
from apps.core.models import AuditLog
from apps.core.permissions import HasModulePermission
from apps.core.rbac import Action, Module

from .exporters import build_pdf, build_xlsx
from .models import ReportExportLog
from .services import REPORT_REGISTRY

VALID_FORMATS = {'PDF', 'XLSX'}

REPORT_LABELS = {
    'PERSONNEL': 'Personnel Report',
    'VEHICLE': 'Vehicle Report',
    'FLIGHT': 'Flight Report',
    'MISSION': 'Mission Report',
    'RISK': 'Risk Report',
    'INVENTORY': 'Inventory Report',
}


class ReportListView(APIView):
    """GET /reports/ — lists the available report types (for a frontend picker)."""

    permission_classes = [HasModulePermission]
    permission_module = Module.REPORTS
    required_action = Action.VIEW

    def get(self, request):
        return Response([{'type': key, 'label': REPORT_LABELS[key]} for key in REPORT_REGISTRY])


class ReportDataView(APIView):
    """GET /reports/<report_type>/ — on-screen report data as JSON."""

    permission_classes = [HasModulePermission]
    permission_module = Module.REPORTS
    required_action = Action.REPORT

    def get(self, request, report_type):
        report_fn = REPORT_REGISTRY.get(report_type.upper())
        if not report_fn:
            raise NotFound(f'Unknown report type "{report_type}". Valid types: {", ".join(REPORT_REGISTRY)}.')

        title, headers, rows = report_fn()
        return Response({'title': title, 'headers': headers, 'rows': rows, 'row_count': len(rows)})


class ReportExportView(APIView):
    """
    GET /reports/<report_type>/export/?format=pdf|xlsx — downloads the
    report as a file and records a ReportExportLog + audit-log entry.
    """

    permission_classes = [HasModulePermission]
    permission_module = Module.REPORTS
    required_action = Action.EXPORT

    def get(self, request, report_type):
        report_type = report_type.upper()
        report_fn = REPORT_REGISTRY.get(report_type)
        if not report_fn:
            raise NotFound(f'Unknown report type "{report_type}". Valid types: {", ".join(REPORT_REGISTRY)}.')

        export_format = request.query_params.get('format', 'pdf').upper()
        if export_format not in VALID_FORMATS:
            raise ValidationError('format must be "pdf" or "xlsx".')

        title, headers, rows = report_fn()

        if export_format == 'PDF':
            content = build_pdf(title, headers, rows)
            content_type = 'application/pdf'
            filename = f'{report_type.lower()}_report.pdf'
        else:
            content = build_xlsx(title, headers, rows)
            content_type = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
            filename = f'{report_type.lower()}_report.xlsx'

        ReportExportLog.objects.create(
            report_type=report_type, format=export_format,
            generated_by=request.user, row_count=len(rows),
        )
        log_action(
            user=request.user, action=AuditLog.Action.OTHER,
            description=f'Exported {title} as {export_format} ({len(rows)} rows)', request=request,
        )

        response = HttpResponse(content, content_type=content_type)
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        return response
