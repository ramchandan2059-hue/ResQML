import os
import re
import html
import datetime
from typing import Dict, Any, List
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable, KeepTogether
)

REPORTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "reports")
os.makedirs(REPORTS_DIR, exist_ok=True)

def sanitize_text_for_reportlab(text: Any) -> str:
    """
    Sanitizes plain or markdown text so that ReportLab's Paragraph parser will never crash.
    Converts unsupported unicode characters, fixes unclosed <br> tags, converts Markdown,
    and strips tags that ReportLab paraparser rejects.
    """
    if text is None:
        return ""
    s = str(text)

    # 1. Normalize unicode characters that cause Latin-1 font issues or paraparser errors
    replacements = {
        '\u2022': '&bull; ',
        '\u2023': '&bull; ',
        '\u25e6': '&bull; ',
        '\u2043': '&bull; ',
        '\u2219': '&bull; ',
        '\u2011': '-',
        '\u2012': '-',
        '\u2013': '-',
        '\u2014': '--',
        '\u2018': "'",
        '\u2019': "'",
        '\u201c': '"',
        '\u201d': '"',
        '\u2026': '...',
        '\u202f': ' ',
        '\u00a0': ' ',
        '\ufeff': '',
    }
    for orig, repl in replacements.items():
        s = s.replace(orig, repl)

    # 2. Fix unclosed or malformed <br> tags
    s = re.sub(r'<br\s*/?>', '<br/>', s, flags=re.IGNORECASE)

    # 3. Strip unsupported HTML tags
    s = re.sub(r'</?(?:para|p|div|span|table|thead|tbody|tr|th|td|ul|ol|li|hr|a|img|header|footer|section)[^>]*>', ' ', s, flags=re.IGNORECASE)

    # 4. Convert markdown bold and italic
    s = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', s)
    s = re.sub(r'__(.+?)__', r'<b>\1</b>', s)
    s = re.sub(r'(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)', r'<i>\1</i>', s)

    # 5. Fix unescaped ampersands (e.g. "R & D" -> "R &amp; D")
    s = re.sub(r'&(?!([a-zA-Z0-9]+|#\d+|#x[0-9a-fA-F]+);)', '&amp;', s)

    return s

def generate_pdf_report(
    patient: Dict[str, Any],
    medications: List[Dict[str, Any]],
    risk_summary: Dict[str, Any],
    ai_explanation: Dict[str, Any],
    report_id: str
) -> str:
    """
    Builds a professional clinical PDF case report matching the BTEC Hackathon specification.
    Returns the absolute path to the generated PDF.
    """
    pdf_filename = f"{report_id}.pdf"
    pdf_path = os.path.join(REPORTS_DIR, pdf_filename)
    
    doc = SimpleDocTemplate(
        pdf_path,
        pagesize=letter,
        rightMargin=36,
        leftMargin=36,
        topMargin=36,
        bottomMargin=36
    )

    styles = getSampleStyleSheet()
    
    # Custom styles
    title_style = ParagraphStyle(
        'DocTitle',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=20,
        leading=24,
        textColor=colors.HexColor('#1e3a8a')
    )
    subtitle_style = ParagraphStyle(
        'DocSubTitle',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=10,
        leading=14,
        textColor=colors.HexColor('#475569')
    )
    h2_style = ParagraphStyle(
        'Heading2Custom',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=13,
        leading=17,
        textColor=colors.HexColor('#0f172a'),
        spaceBefore=10,
        spaceAfter=4
    )
    body_style = ParagraphStyle(
        'BodyCustom',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=9,
        leading=13,
        textColor=colors.HexColor('#1e293b')
    )
    bold_label = ParagraphStyle(
        'BoldLabel',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=9,
        leading=13,
        textColor=colors.HexColor('#0f172a')
    )
    badge_style = ParagraphStyle(
        'BadgeStyle',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=14,
        leading=18,
        alignment=1
    )
    alert_box_style = ParagraphStyle(
        'AlertBoxStyle',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=8.5,
        leading=12,
        textColor=colors.HexColor('#334155')
    )
    disclaimer_style = ParagraphStyle(
        'DisclaimerStyle',
        parent=styles['Normal'],
        fontName='Helvetica-Oblique',
        fontSize=8,
        leading=11,
        textColor=colors.HexColor('#dc2626')
    )

    story = []

    # 1. Header Banner
    story.append(Paragraph("POLYPHARMACY RISK ANALYZER", title_style))
    story.append(Paragraph("Clinical Decision-Support & Medication Review Prototype", subtitle_style))
    story.append(HRFlowable(width="100%", thickness=2, color=colors.HexColor('#2563eb'), spaceBefore=6, spaceAfter=10))

    # 2. Metadata Grid (Date, Case ID, Report ID)
    date_str = datetime.datetime.now().strftime("%d %B %Y, %H:%M")
    meta_data = [
        [
            Paragraph(f"<b>Report ID:</b> {report_id}", body_style),
            Paragraph(f"<b>Patient Case ID:</b> {patient.get('case_id', 'N/A')}", body_style),
            Paragraph(f"<b>Review Date:</b> {date_str}", body_style)
        ]
    ]
    meta_table = Table(meta_data, colWidths=[2.3*inch, 2.3*inch, 2.5*inch])
    meta_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), colors.HexColor('#f1f5f9')),
        ('PADDING', (0,0), (-1,-1), 6),
        ('BOX', (0,0), (-1,-1), 0.5, colors.HexColor('#cbd5e1')),
    ]))
    story.append(meta_table)
    story.append(Spacer(1, 10))

    # 3. Patient Information
    story.append(Paragraph("1. Synthetic Patient Profile", h2_style))
    patient_info = [
        [
            Paragraph("<b>Age:</b>", bold_label),
            Paragraph(f"{patient.get('age')} years old", body_style),
            Paragraph("<b>Biological Sex:</b>", bold_label),
            Paragraph(str(patient.get('biological_sex')), body_style)
        ],
        [
            Paragraph("<b>Diagnosed Conditions:</b>", bold_label),
            Paragraph(str(patient.get('conditions')), body_style),
            Paragraph("<b>Duration of Conditions:</b>", bold_label),
            Paragraph(str(patient.get('condition_duration', 'N/A')), body_style)
        ],
        [
            Paragraph("<b>Frailty / Allergies:</b>", bold_label),
            Paragraph(str(patient.get('frailty_allergies', 'None recorded')), body_style),
            Paragraph("<b>Total Active Medicines:</b>", bold_label),
            Paragraph(f"{len(medications)} drugs", body_style)
        ]
    ]
    pat_table = Table(patient_info, colWidths=[1.7*inch, 2.3*inch, 1.8*inch, 1.5*inch])
    pat_table.setStyle(TableStyle([
        ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#e2e8f0')),
        ('PADDING', (0,0), (-1,-1), 5),
    ]))
    story.append(pat_table)
    story.append(Spacer(1, 10))

    # 4. Prototype Risk Indicator Status Box
    risk_level = risk_summary.get('risk_level', 'LOW')
    risk_score = risk_summary.get('risk_score', 0)
    
    bg_color = colors.HexColor('#fee2e2') if risk_level == "HIGH" else (
        colors.HexColor('#fef3c7') if risk_level == "MEDIUM" else colors.HexColor('#dcfce7')
    )
    border_color = colors.HexColor('#ef4444') if risk_level == "HIGH" else (
        colors.HexColor('#f59e0b') if risk_level == "MEDIUM" else colors.HexColor('#22c55e')
    )
    text_color = colors.HexColor('#991b1b') if risk_level == "HIGH" else (
        colors.HexColor('#92400e') if risk_level == "MEDIUM" else colors.HexColor('#166534')
    )

    badge_p = Paragraph(f"<font color='{text_color.hexval()}'>PROTOTYPE RISK LEVEL: {risk_level} ({risk_score} Points)</font>", badge_style)
    subtext_p = Paragraph(
        f"<font color='{text_color.hexval()}'>Evaluation: <b>{risk_summary.get('total_issues', 0)} potential issue(s) detected</b> "
        f"across {len(medications)} medications. (Prototype scale: 0-2 Low, 3-4 Medium, 5+ High)</font>",
        alert_box_style
    )

    risk_box_table = Table([[badge_p], [subtext_p]], colWidths=[7.2*inch])
    risk_box_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), bg_color),
        ('BOX', (0,0), (-1,-1), 1.5, border_color),
        ('PADDING', (0,0), (-1,-1), 6),
        ('ALIGN', (0,0), (-1,-1), 'CENTER'),
    ]))
    story.append(risk_box_table)
    story.append(Spacer(1, 12))

    # 5. Medication Regimen Table
    story.append(Paragraph("2. Current Medication Schedule", h2_style))
    med_table_data = [
        [
            Paragraph("<b>#</b>", bold_label),
            Paragraph("<b>Medicine Name</b>", bold_label),
            Paragraph("<b>Dose</b>", bold_label),
            Paragraph("<b>Frequency</b>", bold_label),
            Paragraph("<b>Duration</b>", bold_label),
            Paragraph("<b>Therapeutic Category</b>", bold_label)
        ]
    ]
    for idx, med in enumerate(medications, 1):
        med_table_data.append([
            Paragraph(str(idx), body_style),
            Paragraph(f"<b>{med.get('medicine_name')}</b>", body_style),
            Paragraph(str(med.get('dose', '-')), body_style),
            Paragraph(str(med.get('frequency', '-')), body_style),
            Paragraph(str(med.get('duration', '-')), body_style),
            Paragraph(str(med.get('category', 'Prescription Drug')), body_style)
        ])

    regimen_table = Table(med_table_data, colWidths=[0.3*inch, 1.8*inch, 1.0*inch, 1.4*inch, 1.0*inch, 1.7*inch])
    regimen_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#e2e8f0')),
        ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#cbd5e1')),
        ('PADDING', (0,0), (-1,-1), 4),
    ]))
    story.append(regimen_table)
    story.append(Spacer(1, 12))

    # 6. Detected Alerts and Rule Findings
    story.append(Paragraph("3. Detected Rule Findings & Alerts", h2_style))
    findings = risk_summary.get("findings", [])
    if not findings:
        story.append(Paragraph("No conflicting interactions or predefined high-risk rules matched for this medication list.", body_style))
    else:
        for idx, f in enumerate(findings, 1):
            sev = f.get('severity', 'Moderate')
            sev_color = '#ef4444' if sev == 'Major' else ('#f59e0b' if sev == 'Moderate' else '#3b82f6')
            
            f_title = sanitize_text_for_reportlab(f.get('title'))
            f_exp = sanitize_text_for_reportlab(f.get('explanation'))
            f_ref = sanitize_text_for_reportlab(f.get('reference'))
            finding_text = f"""<b>Finding #{idx}: {f_title}</b> (<font color='{sev_color}'><b>{sev.upper()} SEVERITY</b></font> | +{f.get('points')} pts)<br/>
<b>Clinical Explanation:</b> {f_exp}<br/>
<b>Reference Source:</b> <i>{f_ref}</i>"""
            
            try:
                finding_p = Paragraph(finding_text, alert_box_style)
            except Exception:
                safe_plain = html.escape(re.sub(r'<[^>]+>', '', finding_text))
                finding_p = Paragraph(safe_plain, alert_box_style)

            f_table = Table([[finding_p]], colWidths=[7.2*inch])
            f_table.setStyle(TableStyle([
                ('BACKGROUND', (0,0), (-1,-1), colors.HexColor('#f8fafc')),
                ('BOX', (0,0), (-1,-1), 0.5, colors.HexColor('#cbd5e1')),
                ('PADDING', (0,0), (-1,-1), 6),
            ]))
            story.append(f_table)
            story.append(Spacer(1, 5))

    story.append(Spacer(1, 8))

    # 7. AI Plain-Language Explanation
    story.append(Paragraph(f"4. Plain-Language Explanation ({ai_explanation.get('model', 'Groq LLaMA-3.3')})", h2_style))
    explanation_text = ai_explanation.get("text", "")
    paragraphs = explanation_text.split("\n\n")

    for para in paragraphs:
        lines = [ln.strip() for ln in para.split('\n') if ln.strip()]
        if not lines:
            continue

        # Check if this paragraph is a Markdown table
        if len(lines) >= 2 and lines[0].startswith('|') and lines[0].endswith('|') and ('|---' in lines[1] or '|:--' in lines[1]):
            header_cols = [c.strip() for c in lines[0].strip('|').split('|')]
            t_data = []
            # Header row
            t_data.append([Paragraph(f"<b>{sanitize_text_for_reportlab(col)}</b>", bold_label) for col in header_cols])

            for r_line in lines[2:]:
                if not r_line.startswith('|'):
                    continue
                cols = [c.strip() for c in r_line.strip('|').split('|')]
                while len(cols) < len(header_cols):
                    cols.append('')
                row_cells = []
                for c in cols[:len(header_cols)]:
                    ct = sanitize_text_for_reportlab(c)
                    try:
                        cell_p = Paragraph(ct, body_style)
                    except Exception:
                        cell_p = Paragraph(html.escape(re.sub(r'<[^>]+>', '', ct)), body_style)
                    row_cells.append(cell_p)
                t_data.append(row_cells)

            if len(t_data) > 1:
                col_w = (7.2 * inch) / max(1, len(header_cols))
                t = Table(t_data, colWidths=[col_w] * len(header_cols))
                t.setStyle(TableStyle([
                    ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#f1f5f9')),
                    ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#cbd5e1')),
                    ('PADDING', (0,0), (-1,-1), 4),
                    ('VALIGN', (0,0), (-1,-1), 'TOP')
                ]))
                story.append(t)
                story.append(Spacer(1, 6))
                continue

        # Regular text paragraph
        cleaned_para = sanitize_text_for_reportlab(para.strip().replace("\n", "<br/>"))
        if cleaned_para:
            try:
                story.append(Paragraph(cleaned_para, body_style))
            except Exception:
                # Infallible fallback: stripped plain text escaped for XML
                plain_text = html.escape(re.sub(r'<[^>]+>', '', cleaned_para))
                story.append(Paragraph(plain_text, body_style))
            story.append(Spacer(1, 4))

    story.append(Spacer(1, 10))

    # 8. Mandatory Safety & Professional Disclaimer
    story.append(Paragraph("5. Important Clinical Governance & Safety Notice", h2_style))
    disclaimer_text = (
        "<b>CLINICAL REVIEW NOTICE:</b> This report is generated by a student-built clinical decision-support "
        "prototype developed for educational and medication-screening demonstration purposes. The risk indicators, "
        "interaction alerts, and explanations are intended exclusively to aid qualified healthcare professionals "
        "(physicians and clinical pharmacists) during structured medication review. "
        "This tool DOES NOT diagnose disease, does NOT prescribe medicines, and CANNOT be used to discontinue or modify "
        "patient prescriptions without licensed clinical authorization."
    )
    disc_table = Table([[Paragraph(disclaimer_text, disclaimer_style)]], colWidths=[7.2*inch])
    disc_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), colors.HexColor('#fef2f2')),
        ('BOX', (0,0), (-1,-1), 1, colors.HexColor('#fca5a5')),
        ('PADDING', (0,0), (-1,-1), 8),
    ]))
    story.append(disc_table)

    # Build Document
    doc.build(story)
    return pdf_path
