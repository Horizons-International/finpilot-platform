import csv
import html
import io
from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from openpyxl import Workbook
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import (
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from app.reporting.data_service import ReportTable
from app.utils.enums import ReportExportFormat

CONTENT_TYPES = {
    ReportExportFormat.CSV: "text/csv",
    ReportExportFormat.EXCEL: (
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    ),
    ReportExportFormat.PDF: "application/pdf",
}


EXTENSIONS = {
    ReportExportFormat.CSV: "csv",
    ReportExportFormat.EXCEL: "xlsx",
    ReportExportFormat.PDF: "pdf",
}


def _display_value(value: Any) -> str:
    if value is None:
        return ""

    if isinstance(value, (datetime, date)):
        return value.isoformat()

    if isinstance(value, Decimal):
        return str(value)

    if isinstance(value, UUID):
        return str(value)

    return str(value)


def _excel_value(value: Any) -> Any:
    if isinstance(value, UUID):
        return str(value)

    if isinstance(value, Decimal):
        return float(value)

    if isinstance(value, datetime):
        if value.tzinfo is not None:
            return value.replace(tzinfo=None)

        return value

    return value


class ReportGenerator:
    def generate(
        self,
        *,
        table: ReportTable,
        format: ReportExportFormat,
    ) -> bytes:
        if format == ReportExportFormat.CSV:
            return self._generate_csv(table)

        if format == ReportExportFormat.EXCEL:
            return self._generate_excel(table)

        if format == ReportExportFormat.PDF:
            return self._generate_pdf(table)

        raise ValueError(
            f"Unsupported export format: {format}",
        )

    @staticmethod
    def content_type(
        format: ReportExportFormat,
    ) -> str:
        return CONTENT_TYPES[format]

    @staticmethod
    def extension(
        format: ReportExportFormat,
    ) -> str:
        return EXTENSIONS[format]

    @staticmethod
    def _generate_csv(
        table: ReportTable,
    ) -> bytes:
        output = io.StringIO(
            newline="",
        )

        writer = csv.writer(
            output,
            lineterminator="\n",
        )

        writer.writerow(table.columns)

        for row in table.rows:
            writer.writerow([_display_value(value) for value in row])

        return output.getvalue().encode(
            "utf-8-sig",
        )

    @staticmethod
    def _generate_excel(
        table: ReportTable,
    ) -> bytes:
        workbook = Workbook()
        worksheet = workbook.active
        worksheet.title = "Report"

        worksheet.append(table.columns)

        for row in table.rows:
            worksheet.append([_excel_value(value) for value in row])

        worksheet.freeze_panes = "A2"
        worksheet.auto_filter.ref = worksheet.dimensions

        for column_cells in worksheet.columns:
            maximum_length = 0

            for cell in column_cells:
                value = _display_value(
                    cell.value,
                )

                maximum_length = max(
                    maximum_length,
                    len(value),
                )

            column_letter = column_cells[0].column_letter

            worksheet.column_dimensions[column_letter].width = min(
                max(maximum_length + 2, 12),
                40,
            )

        output = io.BytesIO()

        workbook.save(output)

        return output.getvalue()

    @staticmethod
    def _generate_pdf(
        table: ReportTable,
    ) -> bytes:
        output = io.BytesIO()

        document = SimpleDocTemplate(
            output,
            pagesize=landscape(A4),
            rightMargin=24,
            leftMargin=24,
            topMargin=24,
            bottomMargin=24,
        )

        styles = getSampleStyleSheet()

        elements = [
            Paragraph(
                html.escape(table.title),
                styles["Title"],
            ),
            Spacer(
                1,
                12,
            ),
        ]

        pdf_data = [
            [
                Paragraph(
                    html.escape(column),
                    styles["Heading4"],
                )
                for column in table.columns
            ]
        ]

        for row in table.rows:
            pdf_data.append(
                [
                    Paragraph(
                        html.escape(_display_value(value)).replace(
                            "\n",
                            "<br/>",
                        ),
                        styles["BodyText"],
                    )
                    for value in row
                ]
            )

        report_table = Table(
            pdf_data,
            repeatRows=1,
        )

        report_table.setStyle(
            TableStyle(
                [
                    ("GRID", (0, 0), (-1, -1), 0.5, "black"),
                    ("BACKGROUND", (0, 0), (-1, 0), "#DDDDDD"),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("FONTSIZE", (0, 0), (-1, -1), 7),
                    ("LEFTPADDING", (0, 0), (-1, -1), 4),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                    ("TOPPADDING", (0, 0), (-1, -1), 4),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ]
            )
        )

        elements.append(report_table)

        document.build(elements)

        return output.getvalue()
