"""Gerador do Manual e Tutorial em PDF — Aloca ABC (Desafio UniSoma 2026 / ABC Aprendiz).

Gera um PDF institucional completo, diagramado e com a logo oficial da ABC Aprendiz
no canto superior esquerdo, explicando detalhadamente todas as funcionalidades e o fluxo
de uso do aplicativo Aloca ABC, totalmente alinhado à documentação principal (README.md):
1. Abrir Planilhas, Validação Estrutural de Cabeçalhos e Botão Salvar (AlocaABC.xlsx)
2. Controles Operacionais: Aceitar Integral (Reativo em Tempo Real) e Permitir Lista de Espera
3. Auditoria Cadastral: Cards de Erros e Alertas Ordenados por Prioridade (Navegação em 1 Clique)
4. Editor de Planilha Integrado Estilo Excel (+ Linha Abaixo, + Coluna Direita, Excluir Linha, Ctrl+Z/Ctrl+Y)
5. Organizar Turmas e Aviso de Salas Excedentes (Possibilidade de Redução de Turmas)
6. Relatórios Oficiais em PDF (PDF p/ Alunos) e Dashboard Analítico (Gerar Relatório de Distribuição)
"""

from __future__ import annotations

import io
from pathlib import Path
from typing import Any

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.pdfgen import canvas
from reportlab.platypus import (
    HRFlowable,
    Image as RLImage,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from src.app.pdf_lists import _get_abc_logo_png_info

# Cores da Identidade Visual Oficial ABC Aprendiz / Aloca ABC
ABC_TEAL = colors.HexColor("#005C8A")        # Azul Petróleo Primário
ABC_CYAN = colors.HexColor("#0E76BC")        # Azul Secundário / Meninos
ABC_RED = colors.HexColor("#E11D48")         # Coral / Meninas
ABC_AMBER = colors.HexColor("#D97706")       # Âmbar / Alertas
ABC_GREEN = colors.HexColor("#107C41")       # Verde Excel / Sucesso
TEXT_DARK = colors.HexColor("#0F172A")       # Cinza ardósia escuro
TEXT_MUTED = colors.HexColor("#475569")      # Cinza médio
BG_CARD = colors.HexColor("#F8FAFC")         # Fundo suave de cards
BG_HIGHLIGHT = colors.HexColor("#F0F9FF")    # Azul bem claro de destaque
BORDER_COLOR = colors.HexColor("#E2E8F0")    # Borda sutil


class NumberedCanvas(canvas.Canvas):
    """Canvas com numeração de páginas em duas passadas: 'Página X de Y' e rodapé institucional."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._saved_page_states: list[dict[str, Any]] = []

    def showPage(self) -> None:
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self) -> None:
        num_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self.draw_page_decorations(num_pages)
            super().showPage()
        super().save()

    def draw_page_decorations(self, total_pages: int) -> None:
        self.saveState()
        self.setFont("Helvetica", 8.5)
        self.setFillColor(TEXT_MUTED)

        y_footer = 1.05 * cm
        self.setStrokeColor(BORDER_COLOR)
        self.setLineWidth(0.6)
        self.line(1.4 * cm, y_footer + 10, A4[0] - 1.4 * cm, y_footer + 10)

        left_text = "Aloca ABC • ABC Aprendiz • Desafio UniSoma 2026 — Manual e Tutorial de Uso da Ferramenta"
        right_text = f"Página {self._pageNumber} de {total_pages}"
        self.drawString(1.4 * cm, y_footer, left_text)
        self.drawRightString(A4[0] - 1.4 * cm, y_footer, right_text)

        self.restoreState()


def build_tutorial_pdf(output_path: str | Path) -> Path:
    """Gera o documento PDF do tutorial de uso do sistema Aloca ABC."""
    out_file = Path(output_path).resolve()
    out_file.parent.mkdir(parents=True, exist_ok=True)

    doc = SimpleDocTemplate(
        str(out_file),
        pagesize=A4,
        leftMargin=1.4 * cm,
        rightMargin=1.4 * cm,
        topMargin=1.0 * cm,
        bottomMargin=1.4 * cm,
        pageCompression=0,
        title="Manual e Tutorial de Uso — Aloca ABC (ABC Aprendiz)",
    )

    styles = getSampleStyleSheet()

    doc_title_style = ParagraphStyle(
        "DocTitle",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=14.5,
        leading=18.0,
        textColor=ABC_TEAL,
    )
    doc_sub_style = ParagraphStyle(
        "DocSub",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=8.6,
        leading=11.5,
        textColor=TEXT_MUTED,
    )
    h1_style = ParagraphStyle(
        "H1Sec",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=11.0,
        leading=14.2,
        textColor=ABC_TEAL,
        spaceBefore=6,
        spaceAfter=2,
    )
    h2_style = ParagraphStyle(
        "H2Sec",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=9.2,
        leading=12.0,
        textColor=ABC_CYAN,
        spaceBefore=3,
        spaceAfter=1,
    )
    body_style = ParagraphStyle(
        "BodyTutorial",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=8.8,
        leading=12.0,
        textColor=TEXT_DARK,
        alignment=4,
    )
    bullet_style = ParagraphStyle(
        "BulletTutorial",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=8.6,
        leading=11.6,
        textColor=TEXT_DARK,
        leftIndent=11,
        spaceBefore=1,
        spaceAfter=1,
    )
    box_text_style = ParagraphStyle(
        "BoxText",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=8.6,
        leading=11.6,
        textColor=TEXT_DARK,
    )

    story: list[Any] = []

    # -------------------------------------------------------------------------
    # Cabeçalho Oficial com a Logo da ABC Aprendiz (sem data de geração)
    # -------------------------------------------------------------------------
    logo_info = _get_abc_logo_png_info()
    col_logo_w = 3.2 * cm
    col_text_w = 18.2 * cm - col_logo_w

    if logo_info:
        png_bytes, w_px, h_px = logo_info
        aspect = (h_px / w_px) if w_px > 0 else 0.78
        logo_w = 2.7 * cm
        logo_h = logo_w * aspect
        rl_img = RLImage(io.BytesIO(png_bytes), width=logo_w, height=logo_h)
        rl_img.hAlign = "LEFT"
        header_table = Table(
            [
                [
                    rl_img,
                    [
                        Paragraph("<b>ALOCA ABC — MANUAL E TUTORIAL DE USO</b>", doc_title_style),
                        Spacer(1, 2),
                        Paragraph(
                            "<b>Sistema Inteligente de Ensalamento e Balanceamento de Turmas</b><br/>"
                            "1º Lugar no Desafio UniSoma 2026 — Equipe 10 / Grupo 20 (Ainaras Marão &amp; Douglas Henrique R. A. Pereira)",
                            doc_sub_style,
                        ),
                    ],
                ]
            ],
            colWidths=[col_logo_w, col_text_w],
        )
        header_table.setStyle(
            TableStyle(
                [
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 0),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                    ("TOPPADDING", (0, 0), (-1, -1), 0),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
                ]
            )
        )
        story.append(header_table)
    else:
        story.append(Paragraph("<b>ALOCA ABC — MANUAL E TUTORIAL DE USO</b>", doc_title_style))
        story.append(Spacer(1, 2))
        story.append(
            Paragraph(
                "Sistema Inteligente de Ensalamento e Balanceamento de Turmas — 1º Lugar Desafio UniSoma 2026",
                doc_sub_style,
            )
        )

    story.append(Spacer(1, 4))
    story.append(HRFlowable(width="100%", thickness=1.5, color=ABC_TEAL, spaceBefore=2, spaceAfter=7))

    # Box introdutório
    intro_p = Paragraph(
        "<b>Sobre o Aloca ABC:</b> O <b>Aloca ABC</b> foi desenvolvido para automatizar o planejamento e "
        "o balanceamento das turmas de capacitação da <b>ABC Aprendiz</b>. A aplicação funciona de maneira "
        "<b>100% offline</b> (via executável <code>AlocaABC.exe</code> ou ambiente Python) e reúne em uma única tela: "
        "auditoria automática de planilhas Excel, tratamento guiado de inconsistências e homônimos, editor interativo "
        "no estilo Excel, motor de otimização matemática em 2 estágios e emissão de relatórios oficiais em PDF.",
        box_text_style,
    )
    intro_table = Table([[intro_p]], colWidths=[18.2 * cm])
    intro_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), BG_HIGHLIGHT),
                ("BOX", (0, 0), (-1, -1), 0.8, colors.HexColor("#BAE6FD")),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
            ]
        )
    )
    story.append(intro_table)
    story.append(Spacer(1, 5))

    # -------------------------------------------------------------------------
    # 1. ABRIR PLANILHAS, VALIDAÇÃO DE CABEÇALHOS E BOTÃO SALVAR
    # -------------------------------------------------------------------------
    story.append(Paragraph("1. Abrir Planilhas, Validação de Cabeçalhos e Botão Salvar", h1_style))
    story.append(
        Paragraph(
            "Na barra superior esquerda do <b>Aloca ABC</b> encontram-se os comandos de leitura e gravação de arquivos Excel (<code>.xlsx</code>):",
            body_style,
        )
    )
    story.append(Spacer(1, 2))
    story.append(
        Paragraph(
            "• <b>Botão 'Abrir Planilha':</b> Abre o seletor nativo do sistema para carregar uma planilha <code>.xlsx</code> contendo as abas "
            "<b>Alunos</b> (colunas obrigatórias: <code>Nome</code>, <code>Sexo</code> e <code>Disponibilidade</code>) e "
            "<b>Turmas</b> (colunas obrigatórias: <code>Turma</code> e <code>Vagas</code>).",
            bullet_style,
        )
    )
    story.append(
        Paragraph(
            "• <b>Validação Estrutural de Cabeçalhos:</b> Assim que a planilha é carregada, o sistema verifica se todas as colunas obrigatórias "
            "estão presentes na primeira linha de cada aba. Caso falte alguma coluna ou haja erro de digitação no título, um card de alerta "
            "explica exatamente qual cabeçalho deve ser corrigido.",
            bullet_style,
        )
    )
    story.append(
        Paragraph(
            "• <b>Botão 'Salvar' (Exportação Completa em Excel):</b> O botão <b>'Salvar'</b> na barra superior permite gravar o trabalho a qualquer momento "
            "(sugerindo por padrão o nome <code>AlocaABC.xlsx</code>):",
            bullet_style,
        )
    )
    story.append(
        Paragraph(
            "&nbsp;&nbsp;&nbsp;&nbsp;1. <b>Durante a higienização cadastral:</b> Salva todas as edições feitas nas células, remoções de duplicatas e correções de erros.",
            bullet_style,
        )
    )
    story.append(
        Paragraph(
            "&nbsp;&nbsp;&nbsp;&nbsp;2. <b>Após clicar em 'Organizar Turmas':</b> Salva a planilha completa contendo as abas originais corrigidas mais a nova aba "
            "<b>Ensalamento</b> (com a turma atribuída a cada jovem) e a aba <b>Inconsistências</b> (com o histórico de auditoria e a Lista de Espera, se houver).",
            bullet_style,
        )
    )

    story.append(Spacer(1, 4))

    # -------------------------------------------------------------------------
    # 2. CONTROLES OPERACIONAIS: ACEITAR INTEGRAL E PERMITIR LISTA DE ESPERA
    # -------------------------------------------------------------------------
    story.append(Paragraph("2. Controles Operacionais: Aceitar Integral e Permitir Lista de Espera", h1_style))
    story.append(
        Paragraph(
            "Na barra superior direita existem duas chaves de configuração que controlam as regras de negócio em tempo real:",
            body_style,
        )
    )
    story.append(Spacer(1, 2))
    story.append(
        Paragraph(
            "• <b>Chave 'Aceitar Integral' (Validação Reativa Instantânea):</b> Define se a instituição aceita inscrições com disponibilidade "
            "<code>Integral</code> (flexíveis entre Manhã e Tarde). Quando esta caixa está <b>desmarcada</b>, qualquer aluno com disponibilidade "
            "<code>Integral</code> na planilha é sinalizado instantaneamente como erro bloqueante <font color='#DC2626'><b>[IMPEDITIVA]</b></font> "
            "no painel lateral e destacado em vermelho na tabela. Ao <b>marcar</b> a caixa, os erros desaparecem imediatamente e o otimizador passa "
            "a utilizar esses alunos como elo de equilíbrio entre os turnos.",
            bullet_style,
        )
    )
    story.append(
        Paragraph(
            "• <b>Chave 'Permitir Lista de Espera':</b> Caso o número de jovens inscritos supere a capacidade física máxima das salas "
            "de um turno ou do total geral, ativar esta opção permite que o motor aloque o número máximo viável de estudantes nas salas e "
            "posicione os demais em <b>Lista de Espera</b> (priorizando quem tem disponibilidade restrita a um único turno).",
            bullet_style,
        )
    )

    story.append(Spacer(1, 4))

    # -------------------------------------------------------------------------
    # 3. AUDITORIA CADASTRAL: ERROS, HOMÔNIMOS E NAVEGAÇÃO EM 1 CLIQUE
    # -------------------------------------------------------------------------
    story.append(Paragraph("3. Auditoria Cadastral e Tratamento de Erros e Homônimos", h1_style))
    story.append(
        Paragraph(
            "Na aba <b>'Relatório &amp; Alertas'</b> do painel direito, todas as ocorrências da planilha são listadas por ordem de prioridade:",
            body_style,
        )
    )
    story.append(Spacer(1, 2))
    story.append(
        Paragraph(
            "1. <font color='#DC2626'><b>Erros Impeditivos [IMPEDITIVA]:</b></font> Células em branco, valores desconhecidos de sexo/disponibilidade, "
            "alunos <code>Integral</code> com a chave desativada ou excesso de demanda sem lista de espera. Impedem o ensalamento até serem resolvidos.",
            bullet_style,
        )
    )
    story.append(
        Paragraph(
            "2. <font color='#D97706'><b>Alertas de Homônimos / Duplicidade [ALERTA]:</b></font> Identificam linhas com o mesmo nome de estudante. "
            "O card oferece botões rápidos para <b>alternar entre as linhas</b> na tabela, <b>Mesclar</b> registros duplicados, <b>Excluir</b> uma cópia "
            "ou clicar em <b>Manter Ambos</b> caso sejam duas pessoas distintas com o mesmo nome.",
            bullet_style,
        )
    )
    story.append(
        Paragraph(
            "3. <font color='#107C41'><b>Padronizações Automáticas [TRATADA]:</b></font> Registram acentos, espaços extras e variações de grafia "
            "(como <code>M/F</code> ou <code>Manha/Manhã</code>) que o sistema higienizou automaticamente ao abrir a planilha.",
            bullet_style,
        )
    )
    story.append(
        Paragraph(
            "• <b>Navegação em 1 Clique:</b> Clicar sobre qualquer card do painel lateral rola a planilha esquerda imediatamente até a linha "
            "do problema e destaca a célula correspondente.",
            bullet_style,
        )
    )

    story.append(PageBreak())

    # -------------------------------------------------------------------------
    # 4. EDITOR DE PLANILHA INTEGRADO (ESTILO EXCEL)
    # -------------------------------------------------------------------------
    story.append(Paragraph("4. Editor de Planilha Integrado (Estilo Excel)", h1_style))
    story.append(
        Paragraph(
            "O painel esquerdo disponibiliza uma grade interativa completa para editar dados sem precisar sair do aplicativo:",
            body_style,
        )
    )
    story.append(Spacer(1, 2))
    story.append(
        Paragraph(
            "• <b>Edição Direta e Barra de Fórmulas (fx):</b> Dê um duplo clique sobre qualquer célula da tabela ou clique nela e digite "
            "na barra superior <code>fx</code>, pressionando <b>Enter</b> para confirmar.",
            bullet_style,
        )
    )
    story.append(
        Paragraph(
            "• <b>Ferramentas Estruturais:</b> Use os botões da barra de ferramentas da planilha para adicionar registros (<b>'+ Linha Abaixo'</b>), "
            "criar novas colunas (<b>'+ Coluna Direita'</b>), apagar linhas selecionadas (<b>'Excluir Linha'</b>) ou voltar à ordem original de leitura (<b>'Restaurar Ordem'</b>).",
            bullet_style,
        )
    )
    story.append(
        Paragraph(
            "• <b>Atalhos e Filtros Rápidos:</b> Utilize <b>Ctrl+Z</b> (Desfazer) e <b>Ctrl+Y</b> (Refazer) para reverter ou repetir alterações. "
            "Use o campo <b>'Filtrar nome / turma...'</b> para localizar rapidamente qualquer aluno ou filtrar os integrantes de uma turma específica.",
            bullet_style,
        )
    )

    story.append(Spacer(1, 5))

    # -------------------------------------------------------------------------
    # 5. ORGANIZAR TURMAS E AVISO DE SALAS A MAIS (POSSIBILIDADE DE REDUÇÃO)
    # -------------------------------------------------------------------------
    story.append(Paragraph("5. Organizar Turmas e Aviso de Salas a Mais", h1_style))
    story.append(
        Paragraph(
            "Quando não houver erros impeditivos pendentes, clique no botão azul <b>'Organizar Turmas'</b> na barra superior direita:",
            body_style,
        )
    )
    story.append(Spacer(1, 2))
    story.append(
        Paragraph(
            "• <b>Otimização em 2 Estágios:</b> O motor resolve primeiro a partição global entre Manhã e Tarde (Estágio 1 Macro) e, em seguida, "
            "a composição exata de cada sala (Estágio 2 Micro), finalizando com um sorteio imparcial e reprodutível (via código <code>SHA-256</code> da planilha). "
            "Assim, todas as salas ficam com quantidades de alunos e proporções entre meninos e meninas o mais próximas possível.",
            bullet_style,
        )
    )
    story.append(
        Paragraph(
            "• <b>Aviso sobre Salas a Mais (Possibilidade de Redução de Turmas):</b> Após distribuir os estudantes nas turmas cadastradas na aba "
            "<code>Turmas</code>, o sistema verifica automaticamente em cada turno (Manhã e Tarde) se o total de vagas ociosas é maior ou igual "
            "à capacidade inteira de uma ou mais salas daquele período. Quando detecta que todos os alunos alocados no turno caberiam em um número "
            "menor de turmas respeitando o limite de vagas por sala, o aplicativo exibe um aviso no <b>Dashboard do Ensalamento</b> e no "
            "<b>Relatório de Distribuição em PDF</b> informando quantas salas poderiam deixar de ser usadas naquele turno e qual seria a nova taxa de ocupação.",
            bullet_style,
        )
    )

    story.append(Spacer(1, 5))

    # -------------------------------------------------------------------------
    # 6. EXPORTAÇÃO DE LISTAS (PDF P/ ALUNOS) E DASHBOARD DO ENSALAMENTO
    # -------------------------------------------------------------------------
    story.append(Paragraph("6. Relatórios em PDF e Dashboard do Ensalamento", h1_style))
    story.append(
        Paragraph(
            "Após organizar as turmas, além de gravar a planilha Excel pelo botão <b>'Salvar'</b>, você pode emitir dois relatórios oficiais em PDF:",
            body_style,
        )
    )
    story.append(Spacer(1, 2))
    story.append(Paragraph("<b>A) Botão 'PDF p/ Alunos' (Barra Superior):</b>", h2_style))
    story.append(
        Paragraph(
            "• Gera um arquivo PDF pronto para impressão e fixação nos murais da <b>ABC Aprendiz</b>, contendo uma página por turma com os alunos "
            "em ordem alfabética (preservando a privacidade de dados demográficos) e uma seção final caso haja estudantes na Lista de Espera.",
            bullet_style,
        )
    )
    story.append(Spacer(1, 3))
    story.append(Paragraph("<b>B) Aba 'Dashboard do Ensalamento' e Botão 'Gerar Relatório de Distribuição':</b>", h2_style))
    story.append(
        Paragraph(
            "• Ao clicar na aba <b>'Dashboard do Ensalamento'</b> no painel direito, você visualiza os indicadores gerais (Total de Alunos, Alocados, "
            "Lista de Espera, Turmas Ativas), o aviso de possibilidade de redução de salas por turno e os gráficos de ocupação e proporção Masculino/Feminino de cada sala.",
            bullet_style,
        )
    )
    story.append(
        Paragraph(
            "• O botão <b>'Gerar Relatório de Distribuição'</b> fica <b>fixo no topo do Dashboard</b> (logo acima dos cards das turmas) e exporta "
            "um relatório gerencial em PDF com todas as tabelas comparativas por turno, avisos de salas que podem ser economizadas e gráficos demográficos.",
            bullet_style,
        )
    )

    doc.build(story, canvasmaker=NumberedCanvas)
    return out_file


if __name__ == "__main__":
    target = Path("docs/Tutorial_Uso_Ferramenta.pdf")
    build_tutorial_pdf(target)
    print(f"Tutorial gerado com sucesso em: {target.resolve()}")
