"""
Official MRM form PDF (landscape A4) — port of the legacy services/pdf_service.py.

Differences from the legacy generator:
  * Risk colours come from the official matrix (apps.mrm.risk), not a score threshold.
  * Hazards are rendered from each form's frozen snapshots, so an approved PDF never
    changes when the hazard registry is edited later.
  * The decision-authority row is chosen by tier, not by integer percent ranges
    (the legacy ranges left gaps such as 50.5% and 65.5%).
  * QR codes use reportlab's built-in generator — no extra dependency.
"""
from io import BytesIO
from pathlib import Path
from xml.sax.saxutils import escape

from django.utils import timezone
from reportlab.graphics import renderPDF  # noqa: F401  (ensures graphics backends are loaded)
from reportlab.graphics.barcode import qr
from reportlab.graphics.shapes import Drawing
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from . import risk
from .access import ancestor_units

ASSETS = Path(__file__).resolve().parent / 'assets'
PURPLE = colors.HexColor('#800080')
LEVEL_COLORS = {risk.HIGH: colors.red, risk.MEDIUM: colors.yellow, risk.LOW: colors.green}
TOTAL_WIDTH = 725


def _p(text, style):
    return Paragraph(escape(str(text)) if text is not None else '', style)


def _image(source, width, height):
    try:
        path = source if isinstance(source, (str, Path)) else source.path
        if path and Path(path).exists():
            return Image(str(path), width=width, height=height, kind='proportional')
    except Exception:
        pass
    return None


def _qr(data, size=34):
    widget = qr.QrCodeWidget(data)
    widget.barFillColor = PURPLE
    x0, y0, x1, y1 = widget.getBounds()
    drawing = Drawing(size, size, transform=[size / (x1 - x0), 0, 0, size / (y1 - y0), 0, 0])
    drawing.add(widget)
    return drawing


def _signature_block(user, signed, when, role, mrm_number, small):
    """Signature image + QR (if signed) or a blank signing line."""
    if user and signed and getattr(user, 'signature', None):
        sig = _image(user.signature, 80, 34)
        if sig is not None:
            stamp = when.strftime('%y%m%d%H%M') if when else '0000000000'
            code = _qr(f'{role}|{mrm_number}|{user.username}|{stamp}')
            block = Table([[sig, code]], colWidths=[88, 38])
            block.setStyle(TableStyle([('VALIGN', (0, 0), (-1, -1), 'MIDDLE'), ('LEFTPADDING', (0, 0), (-1, -1), 0),
                                       ('RIGHTPADDING', (0, 0), (-1, -1), 0)]))
            return block
    return Paragraph('__________________', small)


def _person_cell(label, user, name_snapshot, signed, when, role, mrm_number, small, bold, centered):
    name = name_snapshot or (user.display_name_with_rank if user else '')
    stamp = when.strftime('%d %b %Y %H:%M') if (signed and when) else ''
    rows = [[_p(label, bold)], [_signature_block(user, signed, when, role, mrm_number, small)],
            [_p(name, centered)], [_p(stamp, centered)]]
    t = Table(rows, colWidths=[150])
    t.setStyle(TableStyle([('ALIGN', (0, 0), (-1, -1), 'CENTER'), ('TOPPADDING', (0, 0), (-1, -1), 1),
                           ('BOTTOMPADDING', (0, 0), (-1, -1), 1)]))
    return t


def _hierarchy(unit):
    """('PHILIPPINE AIR FORCE', parents…) lines above the unit, the 'HEADQUARTERS …' line, and the logo units."""
    chain = list(reversed(ancestor_units(unit))) if unit else []
    lines = ['PHILIPPINE AIR FORCE'] + [u.name.upper() for u in chain if u.category != 'HPAF']
    headline = f'HEADQUARTERS {unit.name.upper()}' if unit else ''
    mother = chain[0] if chain else unit
    return lines, headline, mother


def _unit_logo(unit):
    logo = getattr(unit, 'mrm_logo', None) if unit else None
    if logo and logo.is_active and logo.image:
        return _image(logo.image, 50, 50)
    return None


def _risk_bg(rating_code):
    try:
        return LEVEL_COLORS[risk.level(rating_code)]
    except Exception:
        return colors.white


def generate_pdf(form):
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=landscape(A4), leftMargin=58, rightMargin=58, topMargin=20, bottomMargin=20,
        title=f'MRM {form.mrm_number}', author='UOMS — Mission Risk Management',
    )
    styles = getSampleStyleSheet()
    small = ParagraphStyle('small', parent=styles['Normal'], fontSize=8, leading=9.5)
    centered = ParagraphStyle('centered', parent=small, alignment=1)
    bold = ParagraphStyle('bold', parent=small, fontName='Helvetica-Bold', alignment=1)
    head = ParagraphStyle('head', parent=styles['Title'], alignment=1, fontSize=11, leading=13)
    title = ParagraphStyle('title', parent=styles['Title'], alignment=1, fontSize=15, leading=18)
    mid = ParagraphStyle('mid', parent=styles['Normal'], fontSize=10, leading=13, alignment=1)
    grid = ('GRID', (0, 0), (-1, -1), 0.4, colors.black)

    elements = []
    creator, reviewer, authority = form.created_by, form.reviewed_by, form.authority_assigned_to
    lines, headline, mother = _hierarchy(form.unit)

    # ---- header: mother-unit logo | hierarchy | unit logo ----------------
    left = _unit_logo(mother) or _image(ASSETS / 'logo.png', 50, 50) or _p('PAF', small)
    right = _unit_logo(form.unit) or _p('', small)
    text_rows = [[_p(line, head)] for line in lines]
    if headline:
        text_rows.append([_p(headline, head)])
    text_rows.append([_p('MISSION RISK MANAGEMENT (MRM) FORM', title)])
    text = Table(text_rows, colWidths=[585])
    text.setStyle(TableStyle([('ALIGN', (0, 0), (-1, -1), 'CENTER'), ('TOPPADDING', (0, 0), (-1, -1), 0),
                              ('BOTTOMPADDING', (0, 0), (-1, -1), 0)]))
    header = Table([[left, text, right]], colWidths=[70, 585, 70])
    header.setStyle(TableStyle([('VALIGN', (0, 0), (-1, -1), 'MIDDLE'), ('ALIGN', (0, 0), (0, 0), 'CENTER'),
                                ('ALIGN', (2, 0), (2, 0), 'CENTER')]))
    elements += [header, Spacer(1, 4)]

    # ---- mission / compiled / reviewed / date ----------------------------
    compiled = _person_cell('Compiled by', creator, form.creator_name, form.creator_signed,
                            form.creator_signature_date, 'CREATOR', form.mrm_number, small, bold, centered)
    reviewed = _person_cell('Reviewed by', reviewer, form.reviewer_name, form.evaluator_signed,
                            form.evaluator_signature_date, 'REVIEWER', form.mrm_number, small, bold, centered)
    created = form.created_at.astimezone().strftime('%d %B %Y') if form.created_at else ''
    row = Table([[Paragraph(f'<b>Mission/Activity:</b><br/><br/>{escape(form.activity_mission)}', small), compiled,
                  reviewed, Paragraph(f'<b>Date:</b><br/><br/>{created}', small)]], colWidths=[339, 153, 153, 80])
    row.setStyle(TableStyle([grid, ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'), ('ALIGN', (0, 0), (-1, -1), 'CENTER')]))
    elements.append(row)

    verify = Table([[Paragraph(
        f'<font size=7><b>Document Verification:</b> MRM: {form.mrm_number} | Created: '
        f'{form.created_at:%Y-%m-%d %H:%M} | ID: {form.id}</font>', small)]], colWidths=[TOTAL_WIDTH])
    verify.setStyle(TableStyle([grid, ('BACKGROUND', (0, 0), (-1, 0), colors.lightgrey), ('ALIGN', (0, 0), (-1, -1), 'CENTER')]))
    elements.append(verify)

    objective = Table([[Paragraph(f'<b>Mission/Activity Objective:</b> {escape(form.safety_objectives)}<br/><br/>', small)]],
                      colWidths=[TOTAL_WIDTH])
    objective.setStyle(TableStyle([grid]))
    elements.append(objective)

    assumptions = Table([[Paragraph('<b>Assumptions / Nominal Conditions</b>', mid)]], colWidths=[TOTAL_WIDTH])
    assumptions.setStyle(TableStyle([grid, ('BACKGROUND', (0, 0), (-1, 0), colors.whitesmoke)]))
    elements.append(assumptions)

    crew = [f'{escape(t.user.display_name_with_rank)} ({escape(t.role)})' for t in form.tagged_personnel.filter(is_active=True).select_related('user')]
    imsafe_ok = all(form.imsafe.get(k) for k in 'IMSAFE') if form.imsafe else False
    crew_html = '<b>Crew/Personnel:</b> I.M.S.A.F.E. ' + ('confirmed' if imsafe_ok else 'not confirmed')
    if crew:
        crew_html += '<br/>' + '; '.join(crew)
    env_row = Table([[Paragraph(crew_html, small), Paragraph(f'<b>Environment:</b> {escape(form.environment)}', small)]],
                    colWidths=[362.5, 362.5])
    env_row.setStyle(TableStyle([grid, ('VALIGN', (0, 0), (-1, -1), 'MIDDLE')]))
    elements.append(env_row)

    veh_row = Table([[Paragraph(f'<b>Aircraft/Vehicle:</b> {escape(form.aircraft_vehicle)}', small),
                      Paragraph(f'<b>Mission:</b> {escape(form.mission_statement)}', small)]], colWidths=[362.5, 362.5])
    veh_row.setStyle(TableStyle([grid]))
    elements.append(veh_row)

    # ---- hazard table ----------------------------------------------------
    data = [
        ['NR', 'Risk Identified (RI)', 'Assessed Risk (AR)', '', '', 'Mitigations / Treatments Needed', 'Residual Risk (RR)', '', ''],
        ['NR', 'Hazard Description', 'Likelihood', 'Severity', 'Risk Level', 'Mitigations', 'Likelihood', 'Severity', 'Risk Level'],
    ]
    style = [
        grid, ('SPAN', (2, 0), (4, 0)), ('SPAN', (6, 0), (8, 0)), ('SPAN', (1, 0), (1, 1)), ('SPAN', (5, 0), (5, 1)),
        ('SPAN', (0, 0), (0, 1)), ('ALIGN', (0, 0), (-1, -1), 'CENTER'), ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('ALIGN', (5, 2), (5, -1), 'LEFT'), ('BACKGROUND', (0, 0), (-1, 1), colors.lightgrey),
        ('FONTSIZE', (0, 0), (-1, 1), 8),
    ]
    for index, mh in enumerate(form.mission_hazards.select_related('hazard'), start=1):
        snap = mh.snapshot or {}
        before_rating = snap.get('before_risk_rating') or mh.hazard.before_risk_rating
        after_l, after_s = mh.effective_residual
        after_rating = risk.rating(after_l, after_s)
        extra = mh.additional_mitigations
        mitigations = snap.get('mitigations', mh.hazard.mitigations) or ''
        if extra:
            mitigations = f'{mitigations}\n{extra}'
        lines_ = ['• ' + escape(line.strip()) for line in mitigations.splitlines() if line.strip()]
        data.append([
            str(index), Paragraph(escape(snap.get('hazard_description', mh.hazard.hazard_description)), small),
            snap.get('before_likelihood', mh.hazard.before_likelihood), snap.get('before_severity', mh.hazard.before_severity),
            before_rating, Paragraph('<br/>'.join(lines_) or 'N/A', small), after_l, after_s, after_rating,
        ])
        row_index = index + 1
        style += [('BACKGROUND', (4, row_index), (4, row_index), _risk_bg(before_rating)),
                  ('BACKGROUND', (8, row_index), (8, row_index), _risk_bg(after_rating))]
    table = Table(data, colWidths=[24, 190, 48, 44, 48, 215, 48, 44, 48][:9], repeatRows=2)
    table.setStyle(TableStyle(style))
    elements.append(table)

    # ---- management summary & authority ---------------------------------
    pct = form.total_percent or 0
    summary = Table([[Paragraph(f'<b>Total RR/Max Risk x 100 = Risk% __{pct:.0f}%__</b>', mid), Paragraph('<b>MANAGEMENT</b>', mid)]],
                    colWidths=[350, 375])
    summary.setStyle(TableStyle([grid, ('BACKGROUND', (0, 0), (-1, 0), colors.lightblue), ('ALIGN', (0, 0), (-1, -1), 'CENTER')]))
    elements.append(summary)

    if authority and form.authority_approved:
        stamp = form.authority_approval_date.strftime('%d %B %Y %H:%M') if form.authority_approval_date else ''
        who = Paragraph(f'{escape(form.authority_name or authority.display_name_with_rank)}<br/>{stamp}', centered)
    elif authority:
        who = Paragraph(f'{escape(form.authority_name or authority.display_name_with_rank)}<br/>Pending Approval', centered)
    else:
        who = Paragraph('Not Assigned<br/>Pending Approval', centered)
    sig = _signature_block(authority, form.authority_approved, form.authority_approval_date, 'AUTHORITY', form.mrm_number, small)

    rows = [['Residual Risk /Max Risk (%)', 'Mission Decision Authority', 'Name with Date/Time', 'Signature']]
    active_row = 1
    for index, (_, code) in enumerate(risk.AUTHORITY_TIERS, start=1):
        is_active = code == (form.authority_level or 'OPERATOR')
        if is_active:
            active_row = index
        rows.append([risk.AUTHORITY_RANGE_LABELS[code], risk.AUTHORITY_LABELS[code], who if is_active else '', sig if is_active else ''])
    auth = Table(rows, colWidths=[150, 200, 200, 175])
    auth.setStyle(TableStyle([grid, ('BACKGROUND', (0, 0), (-1, 0), colors.lightgrey), ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                              ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'), ('FONTSIZE', (0, 0), (-1, -1), 8),
                              ('BACKGROUND', (0, active_row), (3, active_row), colors.lightblue)]))
    elements.append(auth)

    footer = Table([[Paragraph(f'<font size=6>Verified: {timezone.now():%Y-%m-%d %H:%M:%S} UTC | MRM: {form.mrm_number} | ID: {form.id}'
                               f'{"" if form.authority_approved else " | NOT YET APPROVED — DRAFT COPY"}</font>', small)]],
                   colWidths=[TOTAL_WIDTH])
    footer.setStyle(TableStyle([grid, ('BACKGROUND', (0, 0), (-1, 0), colors.lightgrey), ('ALIGN', (0, 0), (-1, -1), 'CENTER')]))
    elements.append(footer)

    legend = _image(ASSETS / 'risk_matrix.png', 360, 180)
    if legend is not None:
        elements += [Spacer(1, 10), Paragraph('<b>Risk Matrix Legend:</b>', small), legend]

    doc.build(elements)
    return buffer.getvalue()
