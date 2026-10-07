from datetime import datetime

from app.reporting.data_service import ReportTable
from app.reporting.generator import ReportGenerator
from app.utils.enums import ReportExportFormat


def build_table() -> ReportTable:
    return ReportTable(
        title="Customer Report",
        columns=[
            "Customer ID",
            "Status",
            "Created At",
        ],
        rows=[
            [
                "123",
                "VERIFIED",
                datetime(2026, 10, 7, 10, 30),
            ],
            [
                "456",
                "PENDING_VERIFICATION",
                datetime(2026, 10, 7, 11, 45),
            ],
        ],
    )


def test_generates_csv() -> None:
    content = ReportGenerator().generate(
        table=build_table(),
        format=ReportExportFormat.CSV,
    )

    assert content
    assert b"Customer ID" in content
    assert b"VERIFIED" in content


def test_generates_excel() -> None:
    content = ReportGenerator().generate(
        table=build_table(),
        format=ReportExportFormat.EXCEL,
    )

    assert content
    assert content[:2] == b"PK"


def test_generates_pdf() -> None:
    content = ReportGenerator().generate(
        table=build_table(),
        format=ReportExportFormat.PDF,
    )

    assert content
    assert content.startswith(b"%PDF")
