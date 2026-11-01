"""Gerador de PDF limpo de turmas para envio aos alunos — Desafio UniSoma 2026.

Gera um documento PDF minimalista e pronto para divulgação aos alunos/responsáveis,
contendo apenas a identificação de cada turma, o período (Manhã/Tarde) e a relação
nominal em ordem alfabética dos alunos enturmados (sem expor diagnósticos internos
ou colunas burocráticas).
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Optional
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import (
    HRFlowable,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)


def generate_class_lists_pdf(
    output_pdf_path: str | Path,
    instance_title: str,
    turmas_data: list[dict],
    waitlist_data: Optional[list[dict]] = None,
    allow_unallocated: bool = False,
) -> Path:
    """Gera o PDF com a lista nominal de alunos de cada turma (1 turma por página)
    e, opcionalmente, a seção de Lista de Espera ao final caso `allow_unallocated=True`
    e existam estudantes na lista de espera.
    """
    out_path = Path(output_pdf_path).resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)

    doc = SimpleDocTemplate(
        str(out_path),
        pagesize=A4,
        leftMargin=1.8 * cm,
        rightMargin=1.8 * cm,
        topMargin=1.6 * cm,
        bottomMargin=1.6 * cm,
        title=f"Relação de Turmas — {instance_title}",
    )

    styles = getSampleStyleSheet()

    header_title_style = ParagraphStyle(
        "ClassTitle",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=16,
        leading=20,
        textColor=colors.HexColor("#107C41"),
    )

    subtitle_style = ParagraphStyle(
        "ClassSubtitle",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=10,
        leading=14,
        textColor=colors.HexColor("#4B5563"),
    )

    th_style = ParagraphStyle(
        "TableHeader",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=9.5,
        leading=12,
        textColor=colors.white,
    )

    th_center_style = ParagraphStyle(
        "TableHeaderCenter",
        parent=th_style,
        alignment=1,
    )

    td_name_style = ParagraphStyle(
        "StudentName",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=10,
        leading=13,
        textColor=colors.HexColor("#111827"),
    )

    td_center_style = ParagraphStyle(
        "StudentNum",
        parent=td_name_style,
        alignment=1,
        textColor=colors.HexColor("#4B5563"),
    )

    empty_style = ParagraphStyle(
        "EmptyInfo",
        parent=styles["Normal"],
        fontName="Helvetica-Oblique",
        fontSize=10,
        leading=14,
        textColor=colors.HexColor("#6B7280"),
    )

    story: list = []
    stamp = datetime.now().strftime("%d/%m/%Y às %H:%M")

    non_empty_turmas = [t for t in turmas_data if t.get("alunos")]
    target_turmas = non_empty_turmas if non_empty_turmas else turmas_data

    for idx_t, turma in enumerate(target_turmas):
        if idx_t > 0:
            story.append(PageBreak())

        codigo = escape(str(turma.get("codigo", "")))
        turno = escape(str(turma.get("turno", "")))
        alunos = turma.get("alunos", [])

        story.append(Paragraph(f"Turma: {codigo}", header_title_style))
        story.append(Spacer(1, 3))
        story.append(
            Paragraph(
                f"Período: <b>{turno}</b> &nbsp;•&nbsp; Total de estudantes: <b>{len(alunos)}</b> "
                f"&nbsp;•&nbsp; Emitido em {stamp}",
                subtitle_style,
            )
        )
        story.append(Spacer(1, 6))
        story.append(
            HRFlowable(
                width="100%",
                thickness=1.2,
                color=colors.HexColor("#107C41"),
                spaceAfter=10,
            )
        )

        if not alunos:
            story.append(Paragraph("Nenhum estudante alocado nesta turma.", empty_style))
            continue

        rows = [
            [
                Paragraph("Nº", th_center_style),
                Paragraph("Nome do(a) Estudante", th_style),
                Paragraph("Turma / Período", th_center_style),
            ]
        ]

        for pos, aluno in enumerate(alunos, start=1):
            nome_safe = escape(str(aluno.get("nome", "")).strip())
            rows.append(
                [
                    Paragraph(str(pos), td_center_style),
                    Paragraph(nome_safe, td_name_style),
                    Paragraph(codigo, td_center_style),
                ]
            )

        table = Table(
            rows,
            colWidths=[1.6 * cm, 11.8 * cm, 4.0 * cm],
            repeatRows=1,
        )
        table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#107C41")),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#E5E7EB")),
                    (
                        "ROWBACKGROUNDS",
                        (0, 1),
                        (-1, -1),
                        [colors.white, colors.HexColor("#F8FAFC")],
                    ),
                    ("TOPPADDING", (0, 0), (-1, -1), 5),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                    ("LEFTPADDING", (1, 0), (1, -1), 8),
                ]
            )
        )
        story.append(table)

    if allow_unallocated and waitlist_data:
        if story:
            story.append(PageBreak())

        story.append(Paragraph("Lista de Espera", header_title_style))
        story.append(Spacer(1, 3))
        story.append(
            Paragraph(
                f"Situação: <b>Aguardando Vaga</b> &nbsp;•&nbsp; "
                f"Total de estudantes na lista de espera: <b>{len(waitlist_data)}</b> "
                f"&nbsp;•&nbsp; Emitido em {stamp}",
                subtitle_style,
            )
        )
        story.append(Spacer(1, 6))
        story.append(
            HRFlowable(
                width="100%",
                thickness=1.2,
                color=colors.HexColor("#107C41"),
                spaceAfter=10,
            )
        )

        waitlist_rows = [
            [
                Paragraph("Nº", th_center_style),
                Paragraph("Nome do(a) Estudante", th_style),
                Paragraph("Disponibilidade", th_center_style),
            ]
        ]

        for pos, aluno in enumerate(waitlist_data, start=1):
            nome_safe = escape(str(aluno.get("nome", "")).strip())
            disp_raw = str(aluno.get("disponibilidade", "") or "Lista de Espera").strip()
            disp_safe = escape(disp_raw)
            waitlist_rows.append(
                [
                    Paragraph(str(pos), td_center_style),
                    Paragraph(nome_safe, td_name_style),
                    Paragraph(disp_safe, td_center_style),
                ]
            )

        waitlist_table = Table(
            waitlist_rows,
            colWidths=[1.6 * cm, 11.8 * cm, 4.0 * cm],
            repeatRows=1,
        )
        waitlist_table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#107C41")),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#E5E7EB")),
                    (
                        "ROWBACKGROUNDS",
                        (0, 1),
                        (-1, -1),
                        [colors.white, colors.HexColor("#F8FAFC")],
                    ),
                    ("TOPPADDING", (0, 0), (-1, -1), 5),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                    ("LEFTPADDING", (1, 0), (1, -1), 8),
                ]
            )
        )
        story.append(waitlist_table)

    doc.build(story)
    return out_path
