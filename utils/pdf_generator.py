import io
from datetime import datetime
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors

def generate_kontoauszug_pdf(konto_name, zeitraum_text, df_transactions, startbestand, endsaldo_geplant, endsaldo_aktuell):
    """Generiert ein professionelles PDF-Dokument im Arbeitsspeicher."""
    buffer = io.BytesIO()
    
    # PDF-Dokument einrichten mit 20mm Rand
    doc = SimpleDocTemplate(
        buffer, pagesize=A4, 
        rightMargin=40, leftMargin=40, 
        topMargin=40, bottomMargin=40
    )
    story = []
    styles = getSampleStyleSheet()
    
    # Eigene Design-Stile definieren
    title_style = ParagraphStyle(
        'DocTitle', parent=styles['Heading1'], fontSize=22, leading=26,
        textColor=colors.HexColor("#1A365D"), spaceAfter=4
    )
    subtitle_style = ParagraphStyle(
        'DocSubtitle', parent=styles['Normal'], fontSize=10,
        textColor=colors.HexColor("#4A5568"), spaceAfter=15
    )
    meta_style = ParagraphStyle(
        'MetaBoxText', parent=styles['Normal'], fontSize=11, leading=16,
        textColor=colors.HexColor("#2D3748")
    )
    table_header = ParagraphStyle(
        'TableHeaderText', parent=styles['Normal'], fontSize=10, fontName="Helvetica-Bold",
        textColor=colors.white
    )
    table_cell = ParagraphStyle(
        'TableCellText', parent=styles['Normal'], fontSize=9, leading=12,
        textColor=colors.HexColor("#2D3748")
    )
    
    # 1. Titel & Header
    story.append(Paragraph(f"Kontoauszug: {konto_name}", title_style))
    story.append(Paragraph(f"Generiert am: {datetime.now().strftime('%d.%m.%Y %H:%M')} | Zeitraum: {zeitraum_text}", subtitle_style))
    story.append(Spacer(1, 10))
    
    # 2. Kennzahlen-Box (Zusammenfassung)
    summary_data = [
        [
            Paragraph(f"<b>Startbestand:</b><br/>{startbestand:,.2f} CHF", meta_style),
            Paragraph(f"<b>Geplanter Endsaldo:</b><br/>{endsaldo_geplant:,.2f} CHF", meta_style),
            Paragraph(f"<b>Aktueller Endsaldo:</b><br/>{endsaldo_aktuell:,.2f} CHF", meta_style)
        ]
    ]
    summary_table = Table(summary_data, colWidths=[170, 170, 170])
    summary_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), colors.HexColor("#F7FAFC")),
        ('PADDING', (0,0), (-1,-1), 12),
        ('BOX', (0,0), (-1,-1), 1, colors.HexColor("#E2E8F0")),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
    ]))
    story.append(summary_table)
    story.append(Spacer(1, 25))
    
    # 3. Buchungstabelle
    story.append(Paragraph("<b>Detaillierte Buchungsübersicht</b>", styles['Heading2']))
    story.append(Spacer(1, 8))
    
    headers = [
        Paragraph("Datum", table_header), 
        Paragraph("Beschreibung / Zweck", table_header), 
        Paragraph("Typ", table_header), 
        Paragraph("Status", table_header), 
        Paragraph("Betrag", table_header)
    ]
    table_rows = [headers]
    
    if not df_transactions.empty:
        for _, row in df_transactions.iterrows():
            b_val = row['betrag']
            # Farbcodierung: Rot für Minus, Grün für Plus
            color_hex = "#C53030" if b_val < 0 else "#22543D"
            betrag_p = Paragraph(f"<font color='{color_hex}'><b>{b_val:,.2f} CHF</b></font>", table_cell)
            
            table_rows.append([
                Paragraph(row['datum'], table_cell),
                Paragraph(row['beschreibung'], table_cell),
                Paragraph(row['typ'], table_cell),
                Paragraph(row['status'].capitalize(), table_cell),
                betrag_p
            ])
    else:
        table_rows.append([Paragraph("Keine Buchungen in diesem Zeitraum vorhanden.", table_cell), "", "", "", ""])
        
    # Spaltenbreiten für A4 (Total 510 Punkte)
    tx_table = Table(table_rows, colWidths=[65, 215, 75, 65, 90])
    tx_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor("#1A365D")), # Dunkelblau
        ('BOTTOMPADDING', (0,0), (-1,0), 8),
        ('TOPPADDING', (0,0), (-1,0), 8),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor("#E2E8F0")),
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, colors.HexColor("#F7FAFC")]), # Zebra-Streifen
        ('PADDING', (0,1), (-1,-1), 6),
    ]))
    story.append(tx_table)
    
    # PDF bauen
    doc.build(story)
    buffer.seek(0)
    return buffer.getvalue()