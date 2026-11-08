import os
from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.platypus import HRFlowable, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from backend.app.core.config import settings
from backend.app.core.logging import logger


class PurchaseOrderPDFGenerator:
    @staticmethod
    def generate_pdf(
        po_number: str,
        supplier_name: str,
        supplier_email: str,
        warehouse_name: str,
        warehouse_code: str,
        created_at: datetime,
        expected_delivery: datetime,
        items: List[Dict[str, Any]],
        total_cost: Decimal,
        status: str,
        approval_mode: str
    ) -> str:
        """
        Generate a professional vector PDF Purchase Order using ReportLab.
        Returns the absolute file path of the generated PDF.
        """
        filename = f"{po_number}.pdf"
        file_path = os.path.join(settings.PO_PDF_DIR, filename)

        doc = SimpleDocTemplate(
            file_path,
            pagesize=letter,
            rightMargin=36,
            leftMargin=36,
            topMargin=36,
            bottomMargin=36
        )

        styles = getSampleStyleSheet()
        title_style = ParagraphStyle(
            "POTitle",
            parent=styles["Heading1"],
            fontSize=22,
            leading=26,
            textColor=colors.HexColor("#1e293b")
        )
        subtitle_style = ParagraphStyle(
            "POSubTitle",
            parent=styles["Normal"],
            fontSize=10,
            leading=14,
            textColor=colors.HexColor("#64748b")
        )
        section_style = ParagraphStyle(
            "POSection",
            parent=styles["Heading3"],
            fontSize=12,
            leading=16,
            textColor=colors.HexColor("#0f172a")
        )
        body_style = ParagraphStyle(
            "POBody",
            parent=styles["Normal"],
            fontSize=9,
            leading=13,
            textColor=colors.HexColor("#334155")
        )

        elements = []

        # 1. Header: System & Document Details
        header_data = [
            [
                Paragraph("<b>AUTONOMOUS INVENTORY SYSTEM</b><br/>Automated Procurement Gateway", body_style),
                Paragraph(f"<b>PURCHASE ORDER</b><br/><font size=14 color='#0284c7'><b>{po_number}</b></font>", title_style)
            ]
        ]
        header_table = Table(header_data, colWidths=[300, 240])
        header_table.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('ALIGN', (1, 0), (1, 0), 'RIGHT'),
        ]))
        elements.append(header_table)
        elements.append(Spacer(1, 15))
        elements.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#cbd5e1"), spaceBefore=5, spaceAfter=15))

        # 2. Metadata / Parties Table
        info_data = [
            [
                Paragraph("<b>SUPPLIER (VENDOR)</b>", section_style),
                Paragraph("<b>SHIP TO (WAREHOUSE)</b>", section_style),
                Paragraph("<b>PO DETAILS</b>", section_style),
            ],
            [
                Paragraph(f"<b>{supplier_name}</b><br/>Email: {supplier_email}", body_style),
                Paragraph(f"<b>{warehouse_name}</b><br/>Facility Code: {warehouse_code}", body_style),
                Paragraph(
                    f"Date: {created_at.strftime('%Y-%m-%d')}<br/>"
                    f"Expected Delivery: {expected_delivery.strftime('%Y-%m-%d') if expected_delivery else 'TBD'}<br/>"
                    f"Status: <b>{status}</b><br/>"
                    f"Approval Mode: {approval_mode}",
                    body_style
                ),
            ]
        ]
        info_table = Table(info_data, colWidths=[180, 180, 180])
        info_table.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor("#f8fafc")),
            ('PADDING', (0, 0), (-1, -1), 8),
            ('BOX', (0, 0), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
        ]))
        elements.append(info_table)
        elements.append(Spacer(1, 20))

        # 3. Line Items Table
        table_rows = [
            [
                Paragraph("<b>SKU</b>", body_style),
                Paragraph("<b>Item Description</b>", body_style),
                Paragraph("<b>Qty Ordered</b>", body_style),
                Paragraph("<b>Unit Cost</b>", body_style),
                Paragraph("<b>Subtotal</b>", body_style),
            ]
        ]

        total_units = 0
        for item in items:
            qty = item.get("quantity_ordered", 0)
            cost = Decimal(str(item.get("unit_cost", "0.00")))
            subtotal = cost * qty
            total_units += qty

            table_rows.append([
                Paragraph(str(item.get("sku", "N/A")), body_style),
                Paragraph(str(item.get("name", "Product")), body_style),
                Paragraph(str(qty), body_style),
                Paragraph(f"${cost:.2f}", body_style),
                Paragraph(f"${subtotal:.2f}", body_style),
            ])

        # Summary Row
        table_rows.append([
            "",
            Paragraph("<b>TOTALS</b>", body_style),
            Paragraph(f"<b>{total_units}</b>", body_style),
            "",
            Paragraph(f"<b>${total_cost:.2f}</b>", body_style),
        ])

        col_widths = [100, 200, 70, 80, 90]
        items_table = Table(table_rows, colWidths=col_widths)
        items_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#0f172a")),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('PADDING', (0, 0), (-1, -1), 6),
            ('GRID', (0, 0), (-1, -2), 0.5, colors.HexColor("#e2e8f0")),
            ('LINEABOVE', (0, -1), (-1, -1), 1, colors.HexColor("#0f172a")),
            ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor("#f1f5f9")),
        ]))
        elements.append(items_table)
        elements.append(Spacer(1, 25))

        # 4. Terms and Autonomous Certification Footer
        cert_text = (
            f"<i>Autonomous Procurement System Notification</i>: This purchase order was generated automatically "
            f"via statistical stochastic replenishment policies. Approval Mode: {approval_mode}. "
            f"Please dispatch goods to the designated warehouse facility according to agreed lead times."
        )
        elements.append(Paragraph(cert_text, subtitle_style))

        # Build PDF
        doc.build(elements)
        logger.info(f"Purchase Order PDF successfully generated at {file_path}")
        return file_path

