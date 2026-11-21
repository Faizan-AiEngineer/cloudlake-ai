import csv
import io
import re
from decimal import Decimal
from typing import Literal
from xml.sax.saxutils import escape

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response
from openpyxl import Workbook
from openpyxl.styles import Alignment
from openpyxl.utils import get_column_letter
from reportlab.graphics.charts.barcharts import VerticalBarChart
from reportlab.graphics.shapes import Drawing
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from sqlalchemy import case, func, select

from backend.app.database import Alert, Quality, Run, Task, published_run, serialize
from data_engineering.gold import sales_summary
from data_engineering.schema import SCHEMA_VERSION

router = APIRouter(prefix="/api/v1")
Report = Literal["executive", "pipeline", "quality", "business", "infrastructure", "incident"]
Format = Literal["pdf", "csv", "xlsx"]
TITLES = {
    "executive": "Executive platform report", "pipeline": "Pipeline performance",
    "quality": "Data quality", "business": "Business analytics", "infrastructure": "Infrastructure summary",
    "incident": "Operational incidents",
}


def quality_totals(session, run_id, incident_ids):
    scopes = {run_id: "Published snapshot", **dict.fromkeys(incident_ids, "Blocked candidate")}
    totals = {
        row.run_id: row for row in session.execute(
            select(
                Run.id.label("run_id"),
                Run.rejected,
                func.count(Quality.id).label("checks"),
                func.sum(Quality.evaluated).label("rule_evaluations"),
                func.sum(Quality.failed).label("failed_rule_evaluations"),
                func.sum(case((Quality.id.is_not(None), case((Quality.status == "blocked", 1), else_=0))))
                .label("blocked_rules"),
            ).outerjoin(Quality, Quality.run_id == Run.id).where(Run.id.in_(scopes)).group_by(Run.id, Run.rejected)
        )
    }
    rows = []
    for identifier, scope in scopes.items():
        result = totals.get(identifier)
        rows.append({
            "scope": scope, "run_id": identifier, "checks": result.checks if result else 0,
            "rule_evaluations": result.rule_evaluations if result else None,
            "failed_rule_evaluations": result.failed_rule_evaluations if result else None,
            "blocked_rules": result.blocked_rules if result else None,
            "quarantined_rows": result.rejected if result and result.checks else None,
        })
    return rows


def report_data(db, kind):
    sections = {}
    with db.transaction() as session:
        run_id = published_run(session)
        if kind in {"executive", "quality", "business"} and run_id is None:
            raise HTTPException(409, "A published pipeline run is required")
        if kind in {"executive", "pipeline"}:
            runs = list(session.scalars(select(Run).order_by(
                Run.started_at.desc(), Run.id.desc(),
            ).limit(3 if kind == "executive" else 12)))
            sections["Pipeline runs"] = [{
                "run_id": row.id, "mode": row.mode, "status": row.status,
                "processed": row.processed, "rejected": row.rejected,
                "seconds": round(row.duration, 2) if row.duration is not None else None,
            } for row in runs]
            if kind == "pipeline" and runs:
                sections["Latest run tasks"] = [
                    {key: value for key, value in serialize(task).items() if key in {"name", "status", "seconds", "message"}}
                    for task in session.scalars(select(Task).where(Task.run_id == runs[0].id).order_by(Task.id))
                ]
        alerts = []
        if kind in {"executive", "incident"}:
            alerts = list(session.execute(
                select(Alert, Run.status).outerjoin(Run, Alert.run_id == Run.id)
                .order_by(Alert.id.desc()).limit(8 if kind == "executive" else 25)
            ))
        if kind == "executive":
            incidents = dict.fromkeys(
                [run.id for run in runs if run.status == "blocked"]
                + [alert.run_id for alert, status in alerts if status == "blocked"]
            )
            sections["Quality totals by run"] = quality_totals(session, run_id, incidents)
        if kind == "executive":
            sections["Operational alerts"] = [{
                "alert_id": alert.id, "kind": alert.kind, "status": alert.status, "severity": alert.severity,
                "run_id": alert.run_id, "run_status": status, "message": alert.message,
            } for alert, status in alerts]
        if kind == "incident":
            sections["Operational alerts"] = [
                {**serialize(alert), "run_status": status} for alert, status in alerts
            ]
        if kind == "quality":
            sections["Quality scope"] = quality_totals(session, run_id, ())
            checks = session.scalars(select(Quality).where(Quality.run_id == run_id).order_by(
                Quality.failed.desc(), Quality.dataset, Quality.rule_id,
            ))
            sections["Rule results"] = [{
                "dataset": row.dataset, "rule": row.rule_name, "severity": row.severity,
                "records": row.evaluated, "failed": row.failed, "pass_rate": f"{row.pass_rate:.2%}",
            } for row in checks]
        if kind == "executive":
            publication = session.get(Run, run_id)
            sections["Source datasets"] = [
                {"dataset": dataset, "journal_rows": metrics["input"], "schema_version": SCHEMA_VERSION}
                for dataset, metrics in sorted(publication.details.get("silver", {}).items())
            ]
    trend = []
    if kind in {"executive", "business"}:
        directory = db.settings.home / "snapshots" / run_id
        result = sales_summary(directory / "gold", {})
        formatted = {
            key: round(value, 4) if isinstance(value, float) else value for key, value in result["kpis"].items()
        }
        sections["Sales metrics"] = [{"metric": key, "value": value} for key, value in formatted.items()]
        trend = result["trend"]
        if kind == "business":
            sections["Monthly sales"] = trend
            sections["Sales by category"] = result["categories"]
            sections["Sales by region"] = result["regions"]
    if kind in {"executive", "infrastructure"}:
        sections["Infrastructure"] = [
            {"component": "Local metadata", "status": db.engine.dialect.name},
            {"component": "AWS data plane", "status": "Configuration prepared. Deployment unverified."},
            {"component": "Bundled demo data", "status": "Seeded synthetic commerce and an illustrative FX fixture"},
            {"component": "Local incremental mode", "status": "Changed inputs rebuild Silver and Gold snapshots"},
        ]
    return sections, trend


def safe_cell(value):
    if isinstance(value, str) and value.lstrip().startswith(("=", "+", "-", "@")):
        return "'" + value
    return value


def csv_report(sections):
    target = io.StringIO()
    writer = csv.writer(target, lineterminator="\n")
    writer.writerow(["section", "row", "field", "value"])
    for name, rows in sections.items():
        for index, row in enumerate(rows, 1):
            writer.writerows((name, index, key, safe_cell(value)) for key, value in row.items())
    return target.getvalue().encode("utf-8")


def xlsx_report(sections):
    workbook = Workbook()
    workbook.remove(workbook.active)
    for name, rows in sections.items():
        sheet = workbook.create_sheet(name[:31])
        if rows:
            fields = list(rows[0])
            sheet.append(fields)
            for row in rows:
                sheet.append([safe_cell(row[field]) for field in fields])
            sheet.freeze_panes = "A2"
            sheet.auto_filter.ref = sheet.dimensions
            for column, field in enumerate(fields, 1):
                width = max(len(field), *(len(str(row[field])) for row in rows)) + 2
                sheet.column_dimensions[get_column_letter(column)].width = min(width, 52)
                if width > 52:
                    for index in range(2, sheet.max_row + 1):
                        sheet.cell(index, column).alignment = Alignment(wrap_text=True)
        else:
            sheet.append(["No records"])
    target = io.BytesIO()
    workbook.save(target)
    return target.getvalue()


def label(value):
    if value is None:
        return "—"
    if isinstance(value, Decimal):
        return f"{value:,.2f}"
    return str(value)


def revenue_chart(trend):
    trend = trend[-12:]
    drawing = Drawing(465, 132)
    chart = VerticalBarChart()
    chart.x, chart.y, chart.width, chart.height = 54, 24, 395, 94
    chart.data = [[float(row["revenue_usd"]) for row in trend]]
    chart.categoryAxis.categoryNames = [row["month"].strftime("%b %y") for row in trend]
    chart.categoryAxis.labels.fontSize = 7
    chart.valueAxis.labels.fontSize = 7
    chart.valueAxis.valueMin = 0
    chart.valueAxis.labelTextFormat = lambda value: f"{value:,.0f}"
    chart.bars[0].fillColor = colors.HexColor("#317bb9")
    chart.bars[0].strokeColor = None
    drawing.add(chart)
    return drawing


def pdf_report(kind, sections, trend):
    target = io.BytesIO()
    doc = SimpleDocTemplate(target, title=TITLES[kind], author="CloudLake AI",
                            leftMargin=42, rightMargin=42, topMargin=42, bottomMargin=42)
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle("Cell", parent=styles["BodyText"], fontSize=7.5, leading=10))
    styles.add(ParagraphStyle("HeaderCell", parent=styles["Cell"], textColor=colors.white, fontName="Helvetica-Bold"))
    body = [
        Paragraph("CLOUDLAKE AI  /  OPERATIONS", styles["Heading3"]),
        Paragraph(TITLES[kind], styles["Title"]),
        Paragraph("Prepared from the local workspace. The bundled demo uses seeded synthetic commerce "
                  "and an illustrative exchange-rate fixture.", styles["BodyText"]),
        Spacer(1, 8),
    ]
    if kind == "executive":
        summary = sections["Sales metrics"]
        values = {item["metric"]: item["value"] for item in summary}
        body.append(Paragraph(
            f"Completed sales contributed USD {values['revenue_usd']:,.2f} across {values['orders']:,} orders.",
            styles["BodyText"],
        ))
        body.append(Paragraph(
            "Sales and source counts use the published snapshot. Quality totals show the publication and "
            "any blocked runs in the recent history or alerts. Rule evaluations count each row once per rule.",
            styles["BodyText"],
        ))
    if trend:
        body.extend([Paragraph("Monthly recognized revenue (USD)", styles["Heading2"]), revenue_chart(trend)])
    for name, rows in sections.items():
        heading = Paragraph(name, styles["Heading2"])
        heading.keepWithNext = True
        body.append(heading)
        if not rows:
            body.append(Paragraph("No records", styles["BodyText"]))
            continue
        fields = list(rows[0])
        data = [[Paragraph(escape(re.sub("_", " ", field).title()), styles["HeaderCell"]) for field in fields]]
        data.extend([Paragraph(escape(label(row[field])), styles["Cell"]) for field in fields] for row in rows)
        widths = [2 if field in {"message", "metric", "rule", "run_id"} else 1 for field in fields]
        table = Table(data, colWidths=[doc.width * width / sum(widths) for width in widths], repeatRows=1)
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#16304b")),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.HexColor("#edf4fa"), colors.white]),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ]))
        body.append(table)
        body.append(Spacer(1, 9))

    def footer(canvas, document):
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(colors.HexColor("#4d647a"))
        canvas.drawString(42, 22, "CloudLake AI  |  Local demonstration")
        canvas.drawRightString(document.pagesize[0] - 42, 22, f"Page {document.page}")

    doc.build(body, onFirstPage=footer, onLaterPages=footer)
    return target.getvalue()


@router.get("/reports/{kind}/{file_format}")
def report(request: Request, kind: Report, file_format: Format):
    sections, trend = report_data(request.app.state.database, kind)
    if file_format == "pdf":
        payload, media = pdf_report(kind, sections, trend), "application/pdf"
    elif file_format == "csv":
        payload, media = csv_report(sections), "text/csv; charset=utf-8"
    else:
        payload, media = xlsx_report(sections), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    return Response(payload, media_type=media, headers={
        "Content-Disposition": f'attachment; filename="cloudlake-{kind}.{file_format}"',
        "X-Content-Type-Options": "nosniff",
    })
