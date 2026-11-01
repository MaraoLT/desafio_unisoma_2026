"""Gerador do Manual e Tutorial em PDF — Desafio UniSoma 2026 (ABC Aprendiz).

Gera um PDF institucional completo, diagramado e com a logo oficial da ABC Aprendiz
no canto superior esquerdo, explicando detalhadamente o fluxo de uso das funcionalidades:
1. Adicionar uma planilha (com validação prévia de cabeçalhos)
2. Corrigir erros (clicando na aba de erros e inconsistências)
3. Modificar células na planilha (atalhos, edição em lote e undo/redo)
4. Gerar ensalamento (otimização lexicográfica e lista de espera)
5. Relatório de Turmas (PDF oficial para chamadas e mural)
6. Relatório do Dashboard (PDF analítico com aviso de redução de turmas e equilíbrio)
"""

from __future__ import annotations

from datetime import datetime
import io
from pathlib import Path
from typing import Any, Optional

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.pdfgen import canvas
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

from src.app.pdf_lists import _get_abc_logo_png_info

# Cores da Identidade Visual Oficial ABC Aprendiz / UniSoma
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

        # Linha fina de rodapé
        y_footer = 1.05 * cm
        self.setStrokeColor(BORDER_COLOR)
        self.setLineWidth(0.6)
        self.line(1.4 * cm, y_footer + 10, A4[0] - 1.4 * cm, y_footer + 10)

        # Texto do rodapé
        left_text = "ABC Aprendiz • Desafio UniSoma 2026 — Guia do Usuário e Tutorial do Sistema"
        right_text = f"Página {self._pageNumber} de {total_pages}"
        self.drawString(1.4 * cm, y_footer, left_text)
        self.drawRightString(A4[0] - 1.4 * cm, y_footer, right_text)

        self.restoreState()


def build_tutorial_pdf(output_path: str | Path) -> Path:
    """Gera o documento PDF do tutorial de uso do sistema."""
    out_file = Path(output_path).resolve()
    out_file.parent.mkdir(parents=True, exist_ok=True)

    doc = SimpleDocTemplate(
        str(out_file),
        pagesize=A4,
        leftMargin=1.4 * cm,
        rightMargin=1.4 * cm,
        topMargin=1.0 * cm,
        bottomMargin=1.1 * cm,
        pageCompression=0,
        title="Manual e Tutorial de Uso — Sistema de Ensalamento Otimizado ABC Aprendiz",
    )

    styles = getSampleStyleSheet()

    # Tipografia customizada
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
        fontSize=8.5,
        leading=11.2,
        textColor=TEXT_MUTED,
    )
    h1_style = ParagraphStyle(
        "H1Sec",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=11.2,
        leading=14.2,
        textColor=ABC_TEAL,
        spaceBefore=5,
        spaceAfter=2,
    )
    h2_style = ParagraphStyle(
        "H2Sec",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=9.2,
        leading=11.8,
        textColor=ABC_CYAN,
        spaceBefore=3,
        spaceAfter=1,
    )
    body_style = ParagraphStyle(
        "BodyTutorial",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=8.9,
        leading=12.0,
        textColor=TEXT_DARK,
        alignment=4,  # Justificado
    )
    bullet_style = ParagraphStyle(
        "BulletTutorial",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=8.6,
        leading=11.6,
        textColor=TEXT_DARK,
        leftIndent=11,
    )
    box_text_style = ParagraphStyle(
        "BoxText",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=8.5,
        leading=11.4,
        textColor=TEXT_DARK,
    )

    story: list[Any] = []

    # -------------------------------------------------------------------------
    # Cabeçalho Oficial com a Logo da ABC Aprendiz no canto superior esquerdo
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
                        Paragraph("<b>MANUAL DE INSTRUÇÕES E TUTORIAL DE USO</b>", doc_title_style),
                        Spacer(1, 2),
                        Paragraph(
                            "<b>Sistema de Ensalamento Otimizado</b> &nbsp;•&nbsp; Desafio UniSoma 2026 &nbsp;•&nbsp; ABC Aprendiz<br/>"
                            f"<i>Guia Prático de Operação da Aplicação Desktop e Web • Atualizado em {datetime.now().strftime('%d/%m/%Y')}</i>",
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
        story.append(Paragraph("<b>MANUAL DE INSTRUÇÕES E TUTORIAL DE USO</b>", doc_title_style))
        story.append(Spacer(1, 2))
        story.append(
            Paragraph("Sistema de Ensalamento Otimizado — ABC Aprendiz • Desafio UniSoma 2026", doc_sub_style)
        )

    story.append(Spacer(1, 4))
    story.append(HRFlowable(width="100%", thickness=1.5, color=ABC_TEAL, spaceBefore=2, spaceAfter=8))

    # Box introdutório de boas-vindas
    intro_p = Paragraph(
        "<b>Visão Geral da Ferramenta:</b> Esta plataforma foi desenvolvida para apoiar a secretaria e a coordenação "
        "da <b>ABC Aprendiz</b> na organização automatizada das turmas dos cursos de aprendizagem profissional. "
        "A ferramenta reúne higienização de dados cadastrais, validação prévia de cabeçalhos, resolução de duplicidades, "
        "editor interativo de planilhas e um motor matemático avançado de otimização "
        "que garante turmas perfeitamente equilibradas em tamanho e equidade de gênero.",
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
    story.append(Spacer(1, 8))

    # -------------------------------------------------------------------------
    # 1. ADICIONAR UMA PLANILHA
    # -------------------------------------------------------------------------
    story.append(Paragraph("1. Adicionar uma Planilha", h1_style))
    story.append(
        Paragraph(
            "A ferramenta aceita planilhas oficiais no formato Microsoft Excel (<b>.xlsx</b>). "
            "Para carregar uma nova base de alunos e turmas:",
            body_style,
        )
    )
    story.append(Spacer(1, 3))
    story.append(Paragraph("• <b>Passo a Passo:</b> Na barra superior da tela, clique no botão azul <b>'Abrir Planilha'</b>. Uma janela nativa de seleção de arquivos se abrirá para escolher a planilha desejada.", bullet_style))
    story.append(Paragraph("• <b>Estrutura Esperada:</b> A planilha deve conter duas abas principais:", bullet_style))
    story.append(Paragraph("&nbsp;&nbsp;&nbsp;&nbsp;<b>1. Aba 'Alunos':</b> Lista os estudantes cadastrados. Colunas esperadas: <code>Nome</code>, <code>Sexo</code> (M ou F) e <code>Disponibilidade</code> (Manhã, Tarde ou Integral).", bullet_style))
    story.append(Paragraph("&nbsp;&nbsp;&nbsp;&nbsp;<b>2. Aba 'Turmas':</b> Define as turmas ofertadas pela instituição. Colunas esperadas: <code>Turma</code> (código/identificador) e <code>Vagas</code> (capacidade física máxima da sala).", bullet_style))
    story.append(Paragraph("• <b>Validador Automático de Cabeçalhos:</b> Ao selecionar o arquivo, a aplicação inspeciona imediatamente a primeira linha de cada aba. Caso o cabeçalho esteja vazio, fora da ordem ou com nomes diferentes do padrão oficial (ex.: faltar a coluna <code>Disponibilidade</code>), o sistema bloqueia o arquivo preventivamente e emite uma mensagem clara no painel lateral apontando exatamente quais colunas faltam para correção antes de qualquer processamento.", bullet_style))

    story.append(Spacer(1, 8))

    # -------------------------------------------------------------------------
    # 2. CORRIGIR ERROS (CLICANDO NA ABA DE ERROS E INCONSISTÊNCIAS)
    # -------------------------------------------------------------------------
    story.append(Paragraph("2. Corrigir Erros (Aba de Erros e Alertas Cadastrais)", h1_style))
    story.append(
        Paragraph(
            "O painel lateral direito (aba <b>'Relatório &amp; Alertas'</b>) reúne o diagnóstico em tempo real "
            "de todas as inconsistências identificadas na planilha na seção <b>'Erros e Alertas Cadastrais'</b>.",
            body_style,
        )
    )
    story.append(Spacer(1, 3))

    story.append(Paragraph("<b>Ordem de Prioridade das Mensagens:</b>", h2_style))
    story.append(
        Paragraph(
            "As inconsistências são organizadas de maneira hierárquica inteligente para facilitar a auditoria:",
            body_style,
        )
    )
    story.append(Paragraph("1. <font color='#DC2626'><b>Erros Impeditivos [IMPEDITIVA] no topo:</b></font> Aparecem com prioridade máxima no início da lista. Incluem alunos com campo Sexo ou Disponibilidade em branco, valores irreconhecíveis ou déficit de capacidade física. Esses erros <i>impedem</i> a geração de turmas e exigem correção.", bullet_style))
    story.append(Paragraph("2. <font color='#D97706'><b>Alertas de Duplicidade [ALERTA]:</b></font> Listados logo após os erros impeditivos, ordenados estritamente pela <b>linha da planilha</b>. Indicam estudantes homônimos ou cadastros repetidos em múltiplos períodos.", bullet_style))
    story.append(Paragraph("3. <font color='#107C41'><b>Erros Tratados Automaticamente [TRATADA]:</b></font> Também dispostos em ordem de linha, indicam pequenos ajustes já efetuados pelo sistema (ex.: 'feminino' normalizado para 'F', 'manha' para 'MANHÃ').", bullet_style))

    story.append(Spacer(1, 3))
    story.append(Paragraph("<b>Navegação com 1 Clique e Ferramentas de Correção:</b>", h2_style))
    story.append(Paragraph("• <b>Pular para a Linha:</b> Clique em qualquer card de erro ou alerta no painel lateral para navegar automaticamente até a linha correspondente na tabela, com a célula destacada e pronta para edição.", bullet_style))
    story.append(Paragraph("• <b>Alternar Homônimos:</b> Em alertas de duplicidade de nome, um botão especial (ex.: <code>3 ocorrências &lt;-&gt;</code>) permite alternar o foco da tabela ciclicamente entre todas as linhas onde aquele nome aparece.", bullet_style))
    story.append(Paragraph("• <b>Botão 'Corrigir':</b> Em erros tratáveis (como acentuação ou minúsculas), basta clicar no botão azul <code>Corrigir</code> no card para aplicar a higienização recomendada com apenas um toque.", bullet_style))

    story.append(Spacer(1, 8))

    # -------------------------------------------------------------------------
    # 3. MODIFICAR CÉLULAS NA PLANILHA
    # -------------------------------------------------------------------------
    story.append(Paragraph("3. Modificar Células na Planilha", h1_style))
    story.append(
        Paragraph(
            "A ferramenta conta com um editor de dados de alta performance integrado à tela principal, "
            "com a mesma facilidade de uso do Microsoft Excel:",
            body_style,
        )
    )
    story.append(Spacer(1, 3))
    story.append(Paragraph("• <b>Edição Direta:</b> Dê um duplo clique em qualquer célula para alterar o texto (Nome, Sexo ou Disponibilidade). Pressione <b>Enter</b> para confirmar ou clique fora da célula.", bullet_style))
    story.append(Paragraph("• <b>Gerenciamento de Linhas:</b> Na barra de ferramentas superior, utilize o botão <b>'+ Nova Linha'</b> para cadastrar um novo estudante ou <b>'Excluir Linha'</b> para remover os registros selecionados.", bullet_style))
    story.append(Paragraph("• <b>Navegação e Seleção:</b> Clique nas células ou arraste o mouse para selecionar linhas e colunas para inspeção direta dos dados.", bullet_style))
    story.append(Paragraph("• <b>Revalidação Instantânea:</b> Ao alterar qualquer célula, o sistema reavalia imediatamente todas as regras de validação cadastral e atualiza os contadores de erros no painel lateral em tempo real.", bullet_style))

    story.append(Spacer(1, 4))
    story.append(PageBreak())

    # -------------------------------------------------------------------------
    # 4. GERAR ENSALAMENTO
    # -------------------------------------------------------------------------
    story.append(Paragraph("4. Gerar Ensalamento Otimizado", h1_style))
    story.append(
        Paragraph(
            "Após revisar e corrigir a planilha, o processo de ensalamento é disparado em poucos segundos:",
            body_style,
        )
    )
    story.append(Spacer(1, 3))
    story.append(Paragraph("• <b>Execução:</b> Clique no botão verde <b>'Otimizar Turmas'</b> na barra superior para iniciar o ensalamento automático.", bullet_style))
    story.append(Paragraph("• <b>Distribuição Equilibrada:</b> O sistema distribui os alunos respeitando rigorosamente a capacidade de cada sala e os turnos informados (Manhã, Tarde ou Integral), garantindo turmas equilibradas em quantidade e proporção entre meninos e meninas.", bullet_style))
    story.append(Paragraph("• <b>Opção 'Permitir Lista de Espera':</b> Localizada na barra superior. Se o número de inscritos for superior à capacidade física das salas e essa opção estiver <i>marcada</i>, o sistema ensala o contingente máximo e organiza os alunos excedentes em lista de espera.", bullet_style))
    story.append(Paragraph("• <b>Criação das Abas Oficiais:</b> Ao finalizar o cálculo, a ferramenta gera e exibe automaticamente duas novas abas na planilha:", bullet_style))
    story.append(Paragraph("&nbsp;&nbsp;&nbsp;&nbsp;• <b>Aba 'Ensalamento':</b> Tabela oficial com as colunas <code>Nome</code>, <code>Sexo</code>, <code>Disponibilidade</code> e <code>Turma</code> (ex.: MANHÃ - A).", bullet_style))
    story.append(Paragraph("&nbsp;&nbsp;&nbsp;&nbsp;• <b>Aba 'Inconsistências':</b> Registro completo de todas as ocorrências cadastrais e alunos na lista de espera para arquivamento oficial.", bullet_style))

    story.append(Spacer(1, 8))

    # -------------------------------------------------------------------------
    # 5. RELATÓRIO DE TURMAS
    # -------------------------------------------------------------------------
    story.append(Paragraph("5. Relatório de Turmas (PDF Oficial de Chamada e Mural)", h1_style))
    story.append(
        Paragraph(
            "O <b>Relatório de Turmas</b> é o documento oficial destinado à impressão física para a secretaria, "
            "portaria da instituição e listas de chamada dos educadores:",
            body_style,
        )
    )
    story.append(Spacer(1, 3))
    story.append(Paragraph("• <b>Como Emitir:</b> Após executar a otimização das turmas, clique no botão azul <b>'Exportar PDF'</b> na barra de ferramentas superior.", bullet_style))
    story.append(Paragraph("• <b>Organização por Turma:</b> Cada turma possui sua própria seção formatada com tabela contendo:", bullet_style))
    story.append(Paragraph("&nbsp;&nbsp;&nbsp;&nbsp;• Código da sala, turno (Manhã ou Tarde) e capacidade total.", bullet_style))
    story.append(Paragraph("&nbsp;&nbsp;&nbsp;&nbsp;• Tabela com posição sequencial (Nº), Nome do Estudante em ordem alfabética e indicação de Sexo (M / F).", bullet_style))
    story.append(Paragraph("&nbsp;&nbsp;&nbsp;&nbsp;• Rodapé da sala com total de alunos ensalados e vagas livres remanescentes.", bullet_style))
    story.append(Paragraph("• <b>Seção Integrada de Lista de Espera:</b> Caso haja alunos excedentes e a opção 'Permitir Lista de Espera' esteja ativa, o PDF incluirá automaticamente no final uma seção exclusiva de Lista de Espera, detalhando a posição de cada estudante, nome, gênero e turno solicitado.", bullet_style))

    story.append(Spacer(1, 8))

    # -------------------------------------------------------------------------
    # 6. RELATÓRIO DO DASHBOARD
    # -------------------------------------------------------------------------
    story.append(Paragraph("6. Relatório do Dashboard de Ensalamento", h1_style))
    story.append(
        Paragraph(
            "O <b>Relatório do Dashboard</b> é um relatório analítico e executivo para a coordenação "
            "avaliar a eficiência da distribuição das vagas e a viabilidade de economia de recursos:",
            body_style,
        )
    )
    story.append(Spacer(1, 3))
    story.append(Paragraph("• <b>Como Emitir:</b> No painel lateral direito, clique na aba <b>'Dashboard do Ensalamento'</b> e, em seguida, clique no botão <b>'Gerar Relatório de Distribuição'</b> localizado na parte inferior.", bullet_style))
    story.append(Paragraph("• <b>Conteúdo do Documento:</b>", bullet_style))
    story.append(Paragraph("&nbsp;&nbsp;&nbsp;&nbsp;<b>1. Logo e Resumo Global:</b> Logomarca da ABC Aprendiz no canto superior esquerdo acompanhada dos KPIs consolidados de total alocados, salas ofertadas, vagas livres e ocupação global.", bullet_style))
    story.append(Paragraph("&nbsp;&nbsp;&nbsp;&nbsp;<b>2. Aviso de Possibilidade de Redução de Turmas:</b> Se o número de estudantes alocados em um turno couber com folga em menos salas do que o ofertado inicialmente, o PDF insere automaticamente um <b>quadro de aviso em destaque amarelo</b> no início do turno, recomendando fechar salas ociosas para economizar professores e custos sem deixar nenhum aluno de fora.", bullet_style))
    story.append(Paragraph("&nbsp;&nbsp;&nbsp;&nbsp;<b>3. Estatísticas Objetivas por Turno:</b> Quadros concisos informando a <i>Média de alunos por turma</i>, a <i>Faixa de lotação</i> (mínimo e máximo) e o quantitativo exato de <i>Meninos (M)</i> e <i>Meninas (F)</i> com percentuais.", bullet_style))
    story.append(Paragraph("&nbsp;&nbsp;&nbsp;&nbsp;<b>4. Tabela Analítica sem Quebras:</b> Apresenta cada turma com Lotação/Capacidade, Taxa de Ocupação %, Vagas Livres, Meninos, Meninas e uma <b>barra gráfica visual colorida</b> que ilustra a proporção entre meninos (azul), meninas (coral) e vagas ociosas (cinza).", bullet_style))

    # Constrói o PDF utilizando o canvas numerado
    doc.build(story, canvasmaker=NumberedCanvas)
    return out_file


if __name__ == "__main__":
    target = Path("Tutorial_Uso_Ferramenta.pdf")
    build_tutorial_pdf(target)
    print(f"Tutorial gerado com sucesso em: {target.resolve()}")
