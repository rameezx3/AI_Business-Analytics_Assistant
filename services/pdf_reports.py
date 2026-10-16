"""Create polished downloadable PDF business reports from current analytics."""

from __future__ import annotations

from datetime import datetime
from io import BytesIO
from zoneinfo import ZoneInfo

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import pandas as pd
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    Image,
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)
from xml.sax.saxutils import escape


NAVY = colors.HexColor("#12243A")
BLUE = colors.HexColor("#246B8E")
CYAN = colors.HexColor("#20A7B8")
MUTED = colors.HexColor("#5E7185")
PALE = colors.HexColor("#EEF4F8")
LINE = colors.HexColor("#D8E1E9")


def _paragraph(text: object, style: ParagraphStyle) -> Paragraph:
    return Paragraph(escape(str(text)).replace("\n", "<br/>"), style)


def _charts(monthly: pd.DataFrame, categories: pd.DataFrame) -> tuple[bytes | None, bytes | None]:
    sales_png = None
    reliable = (
        monthly.loc[monthly["reliable"]].copy().sort_values("month")
        if {"reliable", "month", "gross_sales"}.issubset(monthly.columns)
        else pd.DataFrame()
    )
    if not reliable.empty:
        fig, ax = plt.subplots(figsize=(9.2, 3.0), dpi=170)
        ax.plot(reliable["month"], reliable["gross_sales"], color="#168AA5", linewidth=2.2, marker="o", markersize=3.5)
        ax.fill_between(reliable["month"], reliable["gross_sales"], color="#20A7B8", alpha=0.12)
        ax.set_title("Reliable monthly gross item sales", loc="left", color="#12243A", fontsize=12, weight="bold", pad=12)
        ax.set_ylabel("Sales (R$)", color="#5E7185")
        ax.grid(axis="y", color="#D8E1E9", linewidth=0.7)
        ax.spines[["top", "right", "left"]].set_visible(False)
        ax.spines["bottom"].set_color("#D8E1E9")
        ax.tick_params(colors="#5E7185", labelsize=8, length=0)
        ax.xaxis.set_major_locator(mdates.MonthLocator(interval=3))
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %Y"))
        fig.autofmt_xdate(rotation=0, ha="center")
        fig.tight_layout()
        output = BytesIO()
        fig.savefig(output, format="png", bbox_inches="tight", facecolor="white")
        plt.close(fig)
        sales_png = output.getvalue()

    category_png = None
    if not categories.empty:
        top = categories.sort_values("gross_sales", ascending=True).tail(8)
        fig, ax = plt.subplots(figsize=(9.2, 3.6), dpi=170)
        ax.barh(top["category"].astype(str), top["gross_sales"], color="#246B8E")
        ax.set_title("Top categories by gross item sales", loc="left", color="#12243A", fontsize=12, weight="bold", pad=12)
        ax.set_xlabel("Sales (R$)", color="#5E7185")
        ax.grid(axis="x", color="#D8E1E9", linewidth=0.7)
        ax.set_axisbelow(True)
        ax.spines[["top", "right", "left"]].set_visible(False)
        ax.spines["bottom"].set_color("#D8E1E9")
        ax.tick_params(colors="#5E7185", labelsize=8, length=0)
        fig.tight_layout()
        output = BytesIO()
        fig.savefig(output, format="png", bbox_inches="tight", facecolor="white")
        plt.close(fig)
        category_png = output.getvalue()
    return sales_png, category_png


def build_pdf_report(
    insights: list[dict[str, object]],
    monthly: pd.DataFrame,
    categories: pd.DataFrame,
    stats: dict[str, float],
    data_cutoff: pd.Timestamp,
    template_name: str = "Executive overview",
) -> bytes:
    """Return a multi-page, printable PDF report as bytes for Streamlit download."""
    generated = datetime.now(ZoneInfo("Asia/Kolkata"))
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=0.62 * inch,
        leftMargin=0.62 * inch,
        topMargin=0.68 * inch,
        bottomMargin=0.66 * inch,
        title=f"AI Business Analytics - {template_name}",
        author="AI Business Analytics Assistant",
        subject="Evidence-linked Olist business analytics report",
    )
    sample = getSampleStyleSheet()
    styles = {
        "title": ParagraphStyle("ReportTitle", parent=sample["Title"], fontName="Helvetica-Bold", fontSize=23, leading=28, textColor=NAVY, alignment=TA_LEFT, spaceAfter=5),
        "subtitle": ParagraphStyle("ReportSubtitle", parent=sample["Normal"], fontName="Helvetica", fontSize=9, leading=14, textColor=MUTED, spaceAfter=15),
        "section": ParagraphStyle("ReportSection", parent=sample["Heading2"], fontName="Helvetica-Bold", fontSize=14, leading=18, textColor=NAVY, spaceBefore=12, spaceAfter=7, keepWithNext=True),
        "finding": ParagraphStyle("FindingTitle", parent=sample["Heading3"], fontName="Helvetica-Bold", fontSize=10.5, leading=14, textColor=BLUE, spaceBefore=7, spaceAfter=3, keepWithNext=True),
        "body": ParagraphStyle("ReportBody", parent=sample["BodyText"], fontName="Helvetica", fontSize=9, leading=13, textColor=NAVY, spaceAfter=4),
        "small": ParagraphStyle("ReportSmall", parent=sample["BodyText"], fontName="Helvetica", fontSize=8, leading=11, textColor=MUTED, spaceAfter=4),
        "kpi_label": ParagraphStyle("KpiLabel", parent=sample["Normal"], fontName="Helvetica-Bold", fontSize=7.5, leading=10, textColor=MUTED, alignment=TA_CENTER),
        "kpi_value": ParagraphStyle("KpiValue", parent=sample["Normal"], fontName="Helvetica-Bold", fontSize=12, leading=16, textColor=NAVY, alignment=TA_CENTER),
    }
    story = [
        _paragraph("BUSINESS ANALYTICS REPORT", ParagraphStyle("Eyebrow", parent=styles["small"], fontName="Helvetica-Bold", fontSize=8, textColor=CYAN)),
        _paragraph(template_name, styles["title"]),
        _paragraph(f"Brazilian E-Commerce (Olist) dataset  |  Generated {generated:%d %b %Y, %H:%M} IST  |  Data through {pd.Timestamp(data_cutoff):%d %b %Y}", styles["subtitle"]),
    ]

    kpis = [
        ("GROSS ITEM SALES", f"R$ {stats['revenue']:,.0f}"),
        ("UNIQUE CUSTOMERS", f"{stats['customers']:,.0f}"),
        ("AVERAGE ORDER VALUE", f"R$ {stats['average_order_value']:,.2f}"),
        ("REPEAT-CUSTOMER RATE", f"{stats['repeat_rate']:.2f}%"),
    ]
    cells = [[_paragraph(label, styles["kpi_label"]) for label, _ in kpis], [_paragraph(value, styles["kpi_value"]) for _, value in kpis]]
    kpi_table = Table(cells, colWidths=[(A4[0] - 1.24 * inch) / 4] * 4, rowHeights=[0.30 * inch, 0.40 * inch])
    kpi_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), PALE),
        ("BOX", (0, 0), (-1, -1), 0.5, LINE),
        ("INNERGRID", (0, 0), (-1, -1), 0.5, LINE),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5), ("RIGHTPADDING", (0, 0), (-1, -1), 5),
    ]))
    story += [kpi_table, Spacer(1, 0.16 * inch)]

    if template_name in {"Executive overview", "Sales and product"}:
        sales_png, _ = _charts(monthly, pd.DataFrame())
        if sales_png:
            story += [_paragraph("Sales trend", styles["section"]), Image(BytesIO(sales_png), width=6.95 * inch, height=2.25 * inch)]
    if template_name in {"Executive overview", "Sales and product"}:
        _, category_png = _charts(pd.DataFrame(), categories)
        if category_png:
            story += [_paragraph("Category performance", styles["section"]), Image(BytesIO(category_png), width=6.95 * inch, height=2.70 * inch)]

    story += [PageBreak(), _paragraph("Evidence-linked findings", styles["section"])]
    for item in insights:
        finding = [
            _paragraph(item["title"], styles["finding"]),
            _paragraph(f"{item['area']} - {item['priority']}", styles["small"]),
            _paragraph(item["summary"], styles["body"]),
            Paragraph("<b>Evidence</b>", styles["small"]),
        ]
        finding.extend(_paragraph(f"- {evidence}", styles["small"]) for evidence in item["evidence"])
        finding += [
            Paragraph(f"<b>Suggested action:</b> {escape(str(item['action']))}", styles["body"]),
            Paragraph(f"<b>Limitation:</b> {escape(str(item['limitation']))}", styles["small"]),
            Spacer(1, 0.08 * inch),
        ]
        story.append(KeepTogether(finding))

    story += [
        _paragraph("Definitions and interpretation", styles["section"]),
        _paragraph("Gross item sales sum product item prices and exclude freight. Average order value uses item sales for orders with items. Repeat-customer rate counts people with more than one recorded order.", styles["body"]),
        _paragraph("Sales comparisons use complete-enough months with at least 500 orders. Customer groups are relative RFM segments anchored to the dataset cutoff. Delivery comparisons use delivered-order weighted averages. These historical associations are descriptive and do not establish causation or predict current performance.", styles["body"]),
        _paragraph("Source: project PostgreSQL database populated from the Brazilian E-Commerce Public Dataset by Olist. Generated metrics reflect the local database at report creation time.", styles["small"]),
    ]

    def draw_page(canvas, document):
        canvas.saveState()
        width, _ = A4
        canvas.setStrokeColor(LINE)
        canvas.setLineWidth(0.6)
        canvas.line(0.62 * inch, 0.48 * inch, width - 0.62 * inch, 0.48 * inch)
        canvas.setFont("Helvetica", 7.5)
        canvas.setFillColor(MUTED)
        canvas.drawString(0.62 * inch, 0.32 * inch, "AI Business Analytics Assistant  |  Historical analysis, not live operational advice")
        canvas.drawRightString(width - 0.62 * inch, 0.32 * inch, f"Page {document.page}")
        canvas.restoreState()

    doc.build(story, onFirstPage=draw_page, onLaterPages=draw_page)
    return buffer.getvalue()
