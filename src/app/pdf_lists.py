"""Geradores de PDF de Listas de Turmas e Relatório de Distribuição do Dashboard — Desafio UniSoma 2026.

Inclui:
1. `generate_class_lists_pdf`: Documento PDF limpo para divulgação aos alunos/responsáveis,
   com a logo da ABC Aprendiz no canto superior esquerdo, uma turma por seção e lista de espera opcional.
2. `generate_dashboard_report_pdf`: Relatório analítico completo do Dashboard do Ensalamento,
   com a logo da ABC Aprendiz no canto superior esquerdo, separação das turmas por turno (Manhã e Tarde),
   estatísticas de distribuição de alunos e de gênero, e aviso automático no início da seção do turno
   quando for possível remover uma ou mais turmas naquele período.
"""

from __future__ import annotations

from datetime import datetime
import io
import math
from pathlib import Path
import re
import sys
from typing import Any, Optional
from xml.sax.saxutils import escape

from reportlab.graphics.shapes import Drawing, Rect
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import (
    HRFlowable,
    Image as RLImage,
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

try:
    from PIL import Image as PILImage
except ImportError:
    PILImage = None  # type: ignore[assignment]

_CACHED_LOGO_PNG: Optional[tuple[bytes, int, int]] = None


def _get_bundle_root() -> Path:
    """Localiza o diretório raiz do projeto ou pacote PyInstaller (_MEIPASS)."""
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(getattr(sys, "_MEIPASS")).resolve()
    return Path(__file__).resolve().parent.parent.parent


def _get_abc_logo_png_info() -> Optional[tuple[bytes, int, int]]:
    """Carrega a logo da ABC Aprendiz como bytes PNG RGB (fundo branco) e dimensões (w, h)."""
    global _CACHED_LOGO_PNG
    if _CACHED_LOGO_PNG is not None:
        return _CACHED_LOGO_PNG

    root = _get_bundle_root()
    here = Path(__file__).resolve().parent
    candidates = [
        here / "static" / "abc-logo.png",
        root / "src" / "app" / "static" / "abc-logo.png",
        here / "images" / "abc-logo-1024x798.webp",
        root / "src" / "app" / "images" / "abc-logo-1024x798.webp",
        here / "assets" / "logo_abc_aprendiz.png",
        root / "src" / "app" / "assets" / "logo_abc_aprendiz.png",
    ]

    raw_bytes: Optional[bytes] = None
    for cand in candidates:
        if cand.is_file():
            try:
                raw_bytes = cand.read_bytes()
                break
            except Exception:
                continue

    if raw_bytes is None:
        # Fallback: extrai data URI base64 de index.html caso empacotado apenas com index.html
        idx_candidates = [
            here / "static" / "index.html",
            root / "src" / "app" / "static" / "index.html",
        ]
        for idx_path in idx_candidates:
            if idx_path.is_file():
                try:
                    import base64

                    html_txt = idx_path.read_text(encoding="utf-8", errors="ignore")
                    m = re.search(r"data:image/[a-zA-Z0-9+.-]+;base64,([A-Za-z0-9+/=]+)", html_txt)
                    if m:
                        raw_bytes = base64.b64decode(m.group(1))
                        break
                except Exception:
                    continue

    if raw_bytes is None:
        return None

    if PILImage is not None:
        try:
            pil_img = PILImage.open(io.BytesIO(raw_bytes)).convert("RGBA")
            bbox = pil_img.getbbox()
            if bbox:
                pil_img = pil_img.crop(bbox)
            bg = PILImage.new("RGB", pil_img.size, (255, 255, 255))
            bg.paste(pil_img, mask=pil_img.split()[3])
            out_buf = io.BytesIO()
            bg.save(out_buf, format="PNG")
            _CACHED_LOGO_PNG = (out_buf.getvalue(), bg.width, bg.height)
            return _CACHED_LOGO_PNG
        except Exception:
            pass

    _CACHED_LOGO_PNG = (raw_bytes, 998, 778)
    return _CACHED_LOGO_PNG


def _build_header_with_logo(
    title_paragraph: Paragraph,
    subtitle_paragraph: Paragraph,
    logo_width_cm: float = 2.2,
    total_width_cm: float = 17.4,
) -> list[Any]:
    """Constrói o cabeçalho com a logo da ABC Aprendiz no canto superior esquerdo."""
    logo_info = _get_abc_logo_png_info()
    if logo_info is None:
        return [title_paragraph, Spacer(1, 3), subtitle_paragraph]

    png_bytes, w_px, h_px = logo_info
    aspect = (h_px / w_px) if w_px > 0 else 0.78
    logo_w = logo_width_cm * cm
    logo_h = logo_w * aspect

    rl_img = RLImage(io.BytesIO(png_bytes), width=logo_w, height=logo_h)
    rl_img.hAlign = "LEFT"

    col_logo_w = (logo_width_cm + 0.45) * cm
    col_text_w = max(8.0 * cm, (total_width_cm * cm) - col_logo_w)

    header_table = Table(
        [[rl_img, [title_paragraph, Spacer(1, 3), subtitle_paragraph]]],
        colWidths=[col_logo_w, col_text_w],
    )
    header_table.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("ALIGN", (0, 0), (0, 0), "LEFT"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ]
        )
    )
    return [header_table]


def generate_class_lists_pdf(
    output_pdf_path: str | Path,
    instance_title: str,
    turmas_data: list[dict],
    waitlist_data: Optional[list[dict]] = None,
    allow_unallocated: bool = False,
) -> Path:
    """Gera o PDF com a lista nominal de alunos de cada turma (1 turma por página),
    com a logo da ABC Aprendiz no canto superior esquerdo e, opcionalmente, a seção
    de Lista de Espera ao final caso `allow_unallocated=True` e existam estudantes na espera.
    """
    out_path = Path(output_pdf_path).resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)

    doc = SimpleDocTemplate(
        str(out_path),
        pagesize=A4,
        leftMargin=1.8 * cm,
        rightMargin=1.8 * cm,
        topMargin=1.4 * cm,
        bottomMargin=1.5 * cm,
        pageCompression=0,
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

        title_p = Paragraph(f"Turma: {codigo}", header_title_style)
        sub_p = Paragraph(
            f"Período: <b>{turno}</b> &nbsp;•&nbsp; Total de estudantes: <b>{len(alunos)}</b> "
            f"&nbsp;•&nbsp; Emitido em {stamp}",
            subtitle_style,
        )
        story.extend(_build_header_with_logo(title_p, sub_p))
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
                Paragraph("Nome do Estudante", th_style),
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

        wl_title_p = Paragraph("Lista de Espera", header_title_style)
        wl_sub_p = Paragraph(
            f"Situação: <b>Aguardando Vaga</b> &nbsp;•&nbsp; "
            f"Total de estudantes na lista de espera: <b>{len(waitlist_data)}</b> "
            f"&nbsp;•&nbsp; Emitido em {stamp}",
            subtitle_style,
        )
        story.extend(_build_header_with_logo(wl_title_p, wl_sub_p))
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
                Paragraph("Nome do Estudante", th_style),
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


def _create_gender_bar_drawing(
    masc: int, fem: int, cap: int, width_pt: float = 82.0, height_pt: float = 10.0
) -> Drawing:
    """Cria uma barra proporcional colorida (Azul=M, Vermelho=F, Cinza=Livre) para o relatório PDF."""
    d = Drawing(width_pt, height_pt)
    d.add(
        Rect(
            0,
            0,
            width_pt,
            height_pt,
            fillColor=colors.HexColor("#CBD5E1"),
            strokeColor=None,
        )
    )
    if cap <= 0:
        return d

    w_m = min(width_pt, max(0.0, (width_pt * masc) / cap))
    w_f = min(max(0.0, width_pt - w_m), max(0.0, (width_pt * fem) / cap))

    if w_m > 0:
        d.add(
            Rect(
                0,
                0,
                w_m,
                height_pt,
                fillColor=colors.HexColor("#0E76BC"),
                strokeColor=None,
            )
        )
    if w_f > 0:
        d.add(
            Rect(
                w_m,
                0,
                w_f,
                height_pt,
                fillColor=colors.HexColor("#E11D48"),
                strokeColor=None,
            )
        )
    return d


def _fmt_num(val: float, decimals: int = 1) -> str:
    """Formata número decimal no padrão brasileiro (vírgula decimal)."""
    return f"{val:.{decimals}f}".replace(".", ",")


def generate_dashboard_report_pdf(
    output_pdf_path: str | Path,
    instance_title: str,
    summary_data: dict[str, Any],
) -> Path:
    """Gera o relatório PDF sobre a distribuição de alunos e gênero nas turmas (Dashboard do Ensalamento).

    Inclui:
    - Logo da ABC Aprendiz no canto superior esquerdo;
    - Resumo executivo global do ensalamento;
    - Seções separadas por turno (Manhã e Tarde);
    - Aviso em destaque no início da seção do turno caso seja possível remover uma ou mais turmas;
    - Estatísticas detalhadas de distribuição de alunos e de equilíbrio de gênero por turno;
    - Tabela de turmas do turno com barra visual de proporção (Masculino / Feminino / Vagas livres).
    """
    out_path = Path(output_pdf_path).resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)

    doc = SimpleDocTemplate(
        str(out_path),
        pagesize=A4,
        leftMargin=1.6 * cm,
        rightMargin=1.6 * cm,
        topMargin=1.4 * cm,
        bottomMargin=1.5 * cm,
        pageCompression=0,
        title=f"Relatório de Distribuição das Turmas — {instance_title}",
    )

    styles = getSampleStyleSheet()

    title_style = ParagraphStyle(
        "DashReportTitle",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=15,
        leading=19,
        textColor=colors.HexColor("#2A469A"),
    )

    subtitle_style = ParagraphStyle(
        "DashReportSubtitle",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=9.5,
        leading=13,
        textColor=colors.HexColor("#475569"),
    )

    shift_hdr_style = ParagraphStyle(
        "ShiftHeaderText",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=12,
        leading=15,
        textColor=colors.white,
    )

    warn_style = ParagraphStyle(
        "RemovableClassWarn",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=9.5,
        leading=13.5,
        textColor=colors.HexColor("#92400E"),
    )

    sec_label_style = ParagraphStyle(
        "SectionSubLabel",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=10,
        leading=13,
        textColor=colors.HexColor("#1E293B"),
    )

    stat_cell_style = ParagraphStyle(
        "StatCell",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=9,
        leading=12.5,
        textColor=colors.HexColor("#1E293B"),
    )

    th_style = ParagraphStyle(
        "DashTH",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=8.8,
        leading=11,
        textColor=colors.white,
    )

    th_center_style = ParagraphStyle(
        "DashTHCenter",
        parent=th_style,
        alignment=1,
    )

    td_style = ParagraphStyle(
        "DashTD",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=9,
        leading=12,
        textColor=colors.HexColor("#0F172A"),
    )

    td_bold_style = ParagraphStyle(
        "DashTDBold",
        parent=td_style,
        fontName="Helvetica-Bold",
    )

    td_center_style = ParagraphStyle(
        "DashTDCenter",
        parent=td_style,
        alignment=1,
    )

    td_m_style = ParagraphStyle(
        "DashTDM",
        parent=td_center_style,
        fontName="Helvetica-Bold",
        textColor=colors.HexColor("#0E76BC"),
    )

    td_f_style = ParagraphStyle(
        "DashTDF",
        parent=td_center_style,
        fontName="Helvetica-Bold",
        textColor=colors.HexColor("#E11D48"),
    )

    empty_style = ParagraphStyle(
        "DashEmpty",
        parent=styles["Normal"],
        fontName="Helvetica-Oblique",
        fontSize=9.5,
        leading=13,
        textColor=colors.HexColor("#64748B"),
    )

    story: list[Any] = []
    stamp = datetime.now().strftime("%d/%m/%Y às %H:%M")
    safe_title = escape(str(instance_title or "Planilha Atual"))

    turmas: list[dict[str, Any]] = list(summary_data.get("turmas") or [])
    stats_turnos: dict[str, Any] = dict(summary_data.get("stats_turnos") or {})
    total_alocados = int(summary_data.get("total_alocados", sum(int(t.get("lotacao", 0)) for t in turmas)))
    total_validos = int(summary_data.get("total_validos", total_alocados))
    total_espera = int(summary_data.get("total_espera", max(0, total_validos - total_alocados)))
    total_salas = int(summary_data.get("total_salas", len(turmas)))

    total_cap_global = sum(int(t.get("capacidade", 0)) for t in turmas)
    total_m_global = sum(int(t.get("masculino", 0)) for t in turmas)
    total_f_global = sum(int(t.get("feminino", 0)) for t in turmas)
    total_livres_global = max(0, total_cap_global - total_alocados)
    ocup_global_pct = (100.0 * total_alocados / total_cap_global) if total_cap_global > 0 else 0.0
    pct_m_global = (100.0 * total_m_global / total_alocados) if total_alocados > 0 else 0.0
    pct_f_global = (100.0 * total_f_global / total_alocados) if total_alocados > 0 else 0.0

    # Cabeçalho Principal com Logo da ABC Aprendiz no canto superior esquerdo
    hdr_title = Paragraph("Relatório de Distribuição de Alunos nas Turmas", title_style)
    hdr_sub = Paragraph(
        f"Planilha: <b>{safe_title}</b> &nbsp;•&nbsp; Emitido em: <b>{stamp}</b><br/>"
        f"Total Alocados: <b>{total_alocados}/{total_validos}</b> &nbsp;•&nbsp; "
        f"Salas Ofertadas: <b>{total_salas}</b> &nbsp;•&nbsp; "
        f"Ocupação Global: <b>{_fmt_num(ocup_global_pct)}%</b> &nbsp;•&nbsp; "
        f"Lista de Espera: <b>{total_espera}</b>",
        subtitle_style,
    )
    story.extend(_build_header_with_logo(hdr_title, hdr_sub, logo_width_cm=2.3, total_width_cm=17.8))
    story.append(Spacer(1, 6))
    story.append(
        HRFlowable(
            width="100%",
            thickness=1.4,
            color=colors.HexColor("#2A469A"),
            spaceAfter=10,
        )
    )

    # Quadro Resumo Global
    global_summary_rows = [
        [
            Paragraph(
                f"<b>Estudantes Ensalados:</b> {total_alocados} de {total_validos} válidos",
                stat_cell_style,
            ),
            Paragraph(
                f"<b>Vagas Totais / Ociosas:</b> {total_cap_global} vagas ({total_livres_global} livres)",
                stat_cell_style,
            ),
            Paragraph(
                f"<b>Equilíbrio Global de Gênero:</b> "
                f"<font color='#0E76BC'><b>{total_m_global} M ({_fmt_num(pct_m_global)}%)</b></font> / "
                f"<font color='#E11D48'><b>{total_f_global} F ({_fmt_num(pct_f_global)}%)</b></font>",
                stat_cell_style,
            ),
        ]
    ]
    global_box = Table(global_summary_rows, colWidths=[5.6 * cm, 5.8 * cm, 6.4 * cm])
    global_box.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F8FAFC")),
                ("BOX", (0, 0), (-1, -1), 0.7, colors.HexColor("#CBD5E1")),
                ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#E2E8F0")),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 7),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
            ]
        )
    )
    story.append(global_box)
    story.append(Spacer(1, 12))

    # Separação das turmas por turno (MANHÃ e TARDE)
    shift_specs = [
        (
            "MANHÃ",
            "1. Turno da Manhã",
            colors.HexColor("#0E76BC"),
            lambda t: "MANH" in str(t.get("turno", "")).upper(),
        ),
        (
            "TARDE",
            "2. Turno da Tarde",
            colors.HexColor("#2F9587"),
            lambda t: "MANH" not in str(t.get("turno", "")).upper(),
        ),
    ]

    for idx_s, (shift_key, shift_title, shift_color, pred_fn) in enumerate(shift_specs):
        if idx_s > 0:
            story.append(Spacer(1, 14))

        shift_turmas = [t for t in turmas if pred_fn(t)]
        st_info = dict(stats_turnos.get(shift_key) or {})

        n_salas = len(shift_turmas) if shift_turmas else int(st_info.get("salas", 0))
        cap_unit = (
            int(shift_turmas[0].get("capacidade", 0))
            if shift_turmas
            else int(st_info.get("capacidade_unitaria", 0))
        )
        cap_total = (
            sum(int(t.get("capacidade", 0)) for t in shift_turmas)
            if shift_turmas
            else int(st_info.get("capacidade_total", n_salas * cap_unit))
        )
        aloc_turno = (
            sum(int(t.get("lotacao", 0)) for t in shift_turmas)
            if shift_turmas
            else int(st_info.get("alocados", 0))
        )
        livres_turno = max(0, cap_total - aloc_turno)
        ocup_turno_pct = (100.0 * aloc_turno / cap_total) if cap_total > 0 else 0.0

        # Barra de título da seção do turno
        termo_turmas_hdr = f"{n_salas} turma ofertada" if n_salas == 1 else f"{n_salas} turmas ofertadas"
        shift_banner = Table(
            [[Paragraph(f"{shift_title} ({termo_turmas_hdr})", shift_hdr_style)]],
            colWidths=[17.8 * cm],
        )
        shift_banner.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, -1), shift_color),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 10),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 10),
                    ("TOPPADDING", (0, 0), (-1, -1), 6),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ]
            )
        )
        story.append(shift_banner)
        story.append(Spacer(1, 6))

        # Verificação se é possível remover uma (ou mais) turma(s) neste turno:
        # Se (n_salas - 1) * cap_unit >= aloc_turno (ou seja, vagas ociosas >= capacidade de 1 turma),
        # podemos remover pelo menos 1 turma no turno mantendo todos os alunos alocados.
        min_salas_necessarias = (
            math.ceil(aloc_turno / cap_unit) if (cap_unit > 0 and aloc_turno > 0) else 0
        )
        turmas_removiveis = max(0, n_salas - min_salas_necessarias) if n_salas > 0 else 0

        if turmas_removiveis >= 1 and cap_unit > 0:
            salas_restantes = n_salas - turmas_removiveis
            vagas_restantes = salas_restantes * cap_unit
            nova_ocup_pct = (
                (100.0 * aloc_turno / vagas_restantes) if vagas_restantes > 0 else 0.0
            )
            termo_turma = "1 turma" if turmas_removiveis == 1 else f"{turmas_removiveis} turmas"
            termo_aluno = f"{aloc_turno} estudante" if aloc_turno == 1 else f"{aloc_turno} estudantes"
            termo_alocado = "alocado" if aloc_turno == 1 else "alocados"
            artigo_todos = "o" if aloc_turno == 1 else "todos os"
            if salas_restantes > 0:
                termo_restantes = "1 turma" if salas_restantes == 1 else f"{salas_restantes} turmas"
                detalhe_restante = (
                    f"mantendo <b>{termo_restantes}</b> ({vagas_restantes} vagas, "
                    f"ocupação de {_fmt_num(nova_ocup_pct)}%) com capacidade suficiente para atender "
                    f"{artigo_todos} {termo_aluno} {termo_alocado} no período."
                )
            else:
                detalhe_restante = "pois não há estudantes alocados neste período."

            termo_n_turmas = "1 turma" if n_salas == 1 else f"{n_salas} turmas"
            warn_text = (
                f"<b>⚠ AVISO — Possibilidade de Redução de Turma no Turno {shift_key}:</b> "
                f"Este turno possui <b>{termo_aluno}</b> {termo_alocado} para <b>{cap_total}</b> vagas "
                f"distribuídas em <b>{termo_n_turmas}</b> (<b>{livres_turno} vagas ociosas</b>, sendo "
                f"<b>{cap_unit}</b> vagas por turma). <b>É possível remover {termo_turma}</b> neste turno, "
                f"{detalhe_restante}"
            )
            warn_box = Table([[Paragraph(warn_text, warn_style)]], colWidths=[17.8 * cm])
            warn_box.setStyle(
                TableStyle(
                    [
                        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#FFFBEB")),
                        ("BOX", (0, 0), (-1, -1), 1.0, colors.HexColor("#F59E0B")),
                        ("LEFTPADDING", (0, 0), (-1, -1), 10),
                        ("RIGHTPADDING", (0, 0), (-1, -1), 10),
                        ("TOPPADDING", (0, 0), (-1, -1), 7),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
                    ]
                )
            )
            story.append(warn_box)
            story.append(Spacer(1, 7))

        if not shift_turmas:
            story.append(
                Paragraph(f"Nenhuma turma configurada ou alocada para o turno {shift_key}.", empty_style)
            )
            continue

        # Cálculo das estatísticas de distribuição de alunos e de gênero no turno
        lots = [int(t.get("lotacao", 0)) for t in shift_turmas]
        mascs = [int(t.get("masculino", 0)) for t in shift_turmas]
        fems = [int(t.get("feminino", 0)) for t in shift_turmas]
        intras = [abs(m - f) for m, f in zip(mascs, fems)]

        mean_lot = sum(lots) / len(lots)
        min_lot = min(lots)
        max_lot = max(lots)
        amp_lot = max_lot - min_lot
        std_lot = math.sqrt(sum((x - mean_lot) ** 2 for x in lots) / len(lots))

        tot_m = sum(mascs)
        tot_f = sum(fems)
        pct_m_shift = (100.0 * tot_m / aloc_turno) if aloc_turno > 0 else 0.0
        pct_f_shift = (100.0 * tot_f / aloc_turno) if aloc_turno > 0 else 0.0

        mean_m = tot_m / len(mascs)
        min_m, max_m = min(mascs), max(mascs)
        amp_m = max_m - min_m

        mean_f = tot_f / len(fems)
        min_f, max_f = min(fems), max(fems)
        amp_f = max_f - min_f

        mean_intra = sum(intras) / len(intras)
        max_intra = max(intras)

        # Quadro sintético de Estatísticas do Turno (Distribuição e Gênero simplificados)
        termo_alunos_media = f"{_fmt_num(mean_lot)} aluno/turma" if round(mean_lot, 1) == 1.0 else f"{_fmt_num(mean_lot)} alunos/turma"
        termo_alunos_faixa = f"{min_lot} a {max_lot} aluno" if min_lot == max_lot == 1 else f"{min_lot} a {max_lot} alunos"
        termo_m_aluno = "aluno" if tot_m == 1 else "alunos"
        termo_f_aluna = "aluna" if tot_f == 1 else "alunas"
        stats_rows = [
            [
                Paragraph("<b>Distribuição de Alunos</b>", sec_label_style),
                Paragraph("<b>Gênero nas Turmas</b>", sec_label_style),
            ],
            [
                Paragraph(
                    f"• <b>Média por Turma:</b> {termo_alunos_media}<br/>"
                    f"• <b>Faixa de Lotação:</b> {termo_alunos_faixa} (Diferença: {amp_lot})",
                    stat_cell_style,
                ),
                Paragraph(
                    f"• <font color='#0E76BC'><b>Meninos (M):</b> {tot_m} {termo_m_aluno} ({_fmt_num(pct_m_shift)}%)</font><br/>"
                    f"• <font color='#E11D48'><b>Meninas (F):</b> {tot_f} {termo_f_aluna} ({_fmt_num(pct_f_shift)}%)</font>",
                    stat_cell_style,
                ),
            ],
        ]

        stats_table = Table(stats_rows, colWidths=[8.7 * cm, 9.1 * cm])
        stats_table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#F1F5F9")),
                    ("BACKGROUND", (0, 1), (-1, 1), colors.white),
                    ("BOX", (0, 0), (-1, -1), 0.6, colors.HexColor("#CBD5E1")),
                    ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#E2E8F0")),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("TOPPADDING", (0, 0), (-1, -1), 6),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                    ("LEFTPADDING", (0, 0), (-1, -1), 8),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ]
            )
        )
        story.append(stats_table)
        story.append(Spacer(1, 8))

        # Tabela detalhada por turma do turno
        turma_rows: list[list[Any]] = [
            [
                Paragraph("Turma", th_style),
                Paragraph("Lotação / Cap.", th_center_style),
                Paragraph("Ocupação", th_center_style),
                Paragraph("Vagas Livres", th_center_style),
                Paragraph("Meninos (M)", th_center_style),
                Paragraph("Meninas (F)", th_center_style),
                Paragraph("Proporção (M / F / Livre)", th_center_style),
            ]
        ]

        for t in shift_turmas:
            cod = escape(str(t.get("codigo", "")))
            lot = int(t.get("lotacao", 0))
            cap = int(t.get("capacidade", 0))
            liv = max(0, cap - lot)
            m_cnt = int(t.get("masculino", 0))
            f_cnt = int(t.get("feminino", 0))
            ocup_t = (100.0 * lot / cap) if cap > 0 else 0.0
            pct_m_t = (100.0 * m_cnt / lot) if lot > 0 else 0.0
            pct_f_t = (100.0 * f_cnt / lot) if lot > 0 else 0.0

            bar_drawing = _create_gender_bar_drawing(m_cnt, f_cnt, cap, width_pt=104.0, height_pt=10.0)

            turma_rows.append(
                [
                    Paragraph(cod, td_bold_style),
                    Paragraph(f"{lot} / {cap}", td_center_style),
                    Paragraph(f"{_fmt_num(ocup_t)}%", td_center_style),
                    Paragraph(str(liv), td_center_style),
                    Paragraph(f"{m_cnt} ({_fmt_num(pct_m_t)}%)", td_m_style),
                    Paragraph(f"{f_cnt} ({_fmt_num(pct_f_t)}%)", td_f_style),
                    bar_drawing,
                ]
            )

        # Linha de Total do Turno
        total_bar = _create_gender_bar_drawing(tot_m, tot_f, cap_total, width_pt=104.0, height_pt=10.0)
        turma_rows.append(
            [
                Paragraph(f"Total {shift_key}", td_bold_style),
                Paragraph(f"<b>{aloc_turno} / {cap_total}</b>", td_center_style),
                Paragraph(f"<b>{_fmt_num(ocup_turno_pct)}%</b>", td_center_style),
                Paragraph(f"<b>{livres_turno}</b>", td_center_style),
                Paragraph(f"{tot_m} ({_fmt_num(pct_m_shift)}%)", td_m_style),
                Paragraph(f"{tot_f} ({_fmt_num(pct_f_shift)}%)", td_f_style),
                total_bar,
            ]
        )

        turmas_table = Table(
            turma_rows,
            colWidths=[
                2.6 * cm,
                2.5 * cm,
                2.1 * cm,
                2.2 * cm,
                2.4 * cm,
                2.4 * cm,
                3.6 * cm,
            ],
            repeatRows=1,
        )
        turmas_table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), shift_color),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("ALIGN", (6, 1), (6, -1), "CENTER"),
                    ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#CBD5E1")),
                    (
                        "ROWBACKGROUNDS",
                        (0, 1),
                        (-1, -2),
                        [colors.white, colors.HexColor("#F8FAFC")],
                    ),
                    ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#F1F5F9")),
                    ("TOPPADDING", (0, 0), (-1, -1), 5),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                    ("LEFTPADDING", (0, 0), (0, -1), 7),
                ]
            )
        )
        story.append(turmas_table)

    doc.build(story)
    return out_path
