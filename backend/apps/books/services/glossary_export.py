from __future__ import annotations

import csv
from io import BytesIO, StringIO

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from apps.books.models import TermDefinition, UserBook, UserTermEdit


def glossary_rows(user_book: UserBook) -> list[dict[str, str]]:
    if not user_book.global_cache:
        return []

    terms = TermDefinition.objects.filter(global_cache=user_book.global_cache).order_by("term")
    edits = {
        edit.term_definition_id: edit.custom_definition
        for edit in UserTermEdit.objects.filter(user=user_book.user, user_book=user_book)
    }
    rows = []
    for term in terms:
        definition = edits.get(term.id, term.definition)
        source = term.source_chapter or "Без главы"
        rows.append(
            {
                "term": term.term,
                "definition": definition,
                "source": source,
            }
        )
    return rows


def export_csv(user_book: UserBook) -> bytes:
    rows = glossary_rows(user_book)
    sio = StringIO()
    writer = csv.writer(sio)
    writer.writerow(["term", "definition", "source"])
    for row in rows:
        writer.writerow([row["term"], row["definition"], row["source"]])
    return sio.getvalue().encode("utf-8-sig")


def export_txt(user_book: UserBook) -> bytes:
    rows = glossary_rows(user_book)
    lines = [
        f"Название книги: {user_book.title}",
        f"Авторы: {user_book.authors or '-'}",
        "",
        "Термины:",
    ]
    for idx, row in enumerate(rows, start=1):
        lines.extend(
            [
                f"{idx}. {row['term']}",
                f"   {row['definition']}",
                f"   Источник: {row['source']}",
                "",
            ]
        )
    return "\n".join(lines).encode("utf-8")


def export_pdf(user_book: UserBook) -> bytes:
    rows = glossary_rows(user_book)
    buffer = BytesIO()
    document = SimpleDocTemplate(buffer, pagesize=A4, leftMargin=15 * mm, rightMargin=15 * mm)
    styles = getSampleStyleSheet()
    content = [
        Paragraph(f"<b>Глоссарий: {user_book.title}</b>", styles["Title"]),
        Spacer(1, 8),
        Paragraph(f"Авторы: {user_book.authors or '-'}", styles["Normal"]),
        Spacer(1, 12),
    ]

    table_data = [["Термин", "Определение", "Источник"]]
    for row in rows:
        table_data.append(
            [
                Paragraph(row["term"], styles["BodyText"]),
                Paragraph(row["definition"], styles["BodyText"]),
                Paragraph(row["source"], styles["BodyText"]),
            ]
        )

    table = Table(table_data, colWidths=[45 * mm, 105 * mm, 30 * mm], repeatRows=1)
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.black),
                ("GRID", (0, 0), (-1, -1), 0.3, colors.grey),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    content.append(table)

    document.build(content)
    return buffer.getvalue()
