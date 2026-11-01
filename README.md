
    # 🎓 Sistema de Otimização e Gestão de Ensalamento — UniSoma 2026
    > **Equipe 10 | Grupo 20 — Desafio UniSoma 2026**
    > *Solução completa para alocação ótima de turmas, equilíbrio demográfico, validação de inconsistências, aplicativo desktop
    nativo e automação em lote.*

    ![Logo ABC Aprendiz](src/app/images/abc-logo-1024x798.webp)

    ---

    ## 📌 Sumário
    1. [Visão Geral e Arquitetura](#-visão-geral-e-arquitetura)
    2. [Modelagem Matemática e Solver MILP](#-modelagem-matemática-e-solver-milp)
    3. [Pré-requisitos e Instalação](#-pré-requisitos-e-instalação)
    4. [Execução via Linha de Comando (CLI — `main.py`)](#-execução-via-linha-de-comando-cli--mainpy)
       - [Guia Exaustivo de Flags e Argumentos](#guia-exaustivo-de-flags-e-argumentos)
       - [Exemplos Práticos de Uso](#exemplos-práticos-de-uso)
    5. [Aplicativo Desktop Gráfico (GUI)](#-aplicativo-desktop-gráfico-gui)
       - [Como Rodar a Aplicação Python](#como-rodar-a-aplicação-python)
       - [Recursos e Funcionamento da Interface](#recursos-e-funcionamento-da-interface)
       - [Diagramas e Telas da Aplicação](#diagramas-e-telas-da-aplicação)
    6. [Geração do Executável Autônomo (.EXE)](#-geração-do-executável-autônomo-exe)
    7. [Estrutura do Repositório](#-estrutura-do-repositório)

    ---

    ## 🚀 Visão Geral e Arquitetura

    O sistema resolve o problema de **Ensalamento Escolar Balanceado** para o Instituto ABC Aprendiz, considerando:
    - **Restrições Rígidas (Hard Constraints)**: Respeito estrito à capacidade máxima de cada sala, correspondência de turno (Manhã,
    Tarde ou flexibilidade Integral) e alocação única por aluno.
    - **Detecção e Tratamento de Inconsistências**: Identificação automática de turmas inexistentes na planilha de alunos (R1),
    incompatibilidade de turno entre aluno e turma (R2), nomes duplicados e campos ausentes.
    - **Otimização Multiobjetivo Lexicográfica**: Minimização simultânea da amplitude de ocupação entre salas do mesmo turno e
    balanceamento equitativo de gênero (50% F / 50% M).

    > **Diagram exceeds terminal width (202 > 135 cols)**
    > Displayed as code block. Widen terminal to view inline.

    ```mermaid
    flowchart TD
        A["Planilha Excel (.xlsx)Abas: Alunos & Turmas"] --> B["1. Leitor Agnóstico(src/read_instance.py)"]
        B --> C["2. Pré-processamento & Auditoria(src/pre_process.py)"]
        C -->|Detecta R1, R2, Duplicatas| D["Relatório de Inconsistências"]
        C -->|Instância Higienizada| E["3. Solver MILP PuLP + CBC(src/models/solver.py)"]

        subgraph SOLVER["Pipeline de Otimização Lexicográfica em 2 Fases"]
            E1["Agregação por Perfis Demográficos(Redução de simetria O(N) -> O(Perfis))"] --> E2["Fase 1: Min-MaxMinimiza
            amplitude de vagas e desequilíbrio de gênero"]
            E2 --> E3["Fase 2: Suavização Par-a-ParMinimiza variância quadrática equivalente + Paridade 50/50"]
        end

        E --> SOLVER
        SOLVER --> F["4. Pós-processamento(src/pos_process.py)"]
        F --> G["Planilha Excel EnriquecidaAbas: Ensalamento + Inconsistências"]
        F --> H["Relatório Diagnóstico (.txt)Métricas, Tempos e Distribuição"]
        F --> I["Listas de Chamada em PDF(src/app/pdf_lists.py)"]
  ──────

## 🧠 Modelagem Matemática e Solver MILP

  O grande diferencial do solver é a Decomposição por Perfis Demográficos Agregados:
  Em vez de criar dezenas de milhares de variáveis binárias individuais x_{i,k} ∈ {0, 1} (que tornariam o problema intratável para N
  ≥ 10.000 alunos), os alunos válidos são agrupados em perfis p = (gênero, turno_disponível).

  • Fase 1 (Min-Max):

    min   Z₁ = W    · Δ    + W    · Δ
                qtd    qtd    gen    gen

  Onde Δ_{qtd} é a diferença entre a maior e a menor turma de um mesmo turno, e Δ_{gen} é a amplitude do desvio de gênero.

  • Fase 2 (Dispersão Par-a-Par e Paridade 50/50):
  Fixa os limites ótimos alcançados na Fase 1 (Z₁^*) e minimiza a soma das diferenças absolutas par-a-par entre todas as turmas,
  adicionando um termo suavizador ε para atingir a máxima simetria intra-turma:

    min   Z₂ =  ∑   │Nₖ - N  │ +  ∑   │Fₖ - F  │ + ε ∑ |Fₖ - Mₖ|
               k<k' │      k'│   k<k' │      k'│     k

  Graças a essa modelagem, instâncias gigantes com 50.000 alunos são resolvidas com solução ótima global em menos de 3 segundos no
  solver open-source CBC!
  ──────

## 💻 Pré-requisitos e Instalação

### Requisitos de Sistema

  • Python: Versão 3.10, 3.11 ou 3.12 (64-bit recomendado).
  • Sistema Operacional: Windows 10/11 (possui WebView2 nativo para o Desktop), Linux ou macOS.

### 1. Criar e Ativar Ambiente Virtual

    # No Windows PowerShell:
    python -m venv .venv
    .\.venv\Scripts\Activate.ps1

    # No Linux / macOS:
    python3 -m venv .venv
    source .venv/bin/activate

### 2. Instalar Dependências

    pip install --upgrade pip
    pip install -r requirements.txt

  Para usufruir da interface gráfica desktop, exportação de PDF e geração do executável, instale os pacotes complementares:

    pip install bottle pywebview pythonnet reportlab pyinstaller
  ──────

## ⌨ Execução via Linha de Comando (CLI — main.py)

  O orquestrador src/main.py permite resolver desde uma única planilha até lotes massivos de instâncias de forma totalmente não
  interativa.

    python src/main.py [caminhos_ou_pastas] [flags]

### Guia Exaustivo de Flags e Argumentos

   Flag / Argumento    │               Tipo / Padrão                │ Descrição Completa
  ─────────────────────┼────────────────────────────────────────────┼────────────────────────────────────────────────────────────────
   inputs              │               Posicional (*)               │ Caminho para um ou mais arquivos .xlsx, pastas ou padrões glob
                       │                                            │ (ex: instances/public/*.xlsx). Se omitido e sem --all,
                       │                                            │ processa por padrão todas as planilhas em instances/public/.
   --all               │                  Booleano                  │ Processa em lote todas as instâncias contidas em
                       │                                            │ instances/public/ e instances/generated/.
   --summary-only      │                  Booleano                  │ Suprime os relatórios extensos no console e exibe apenas uma
                       │                                            │ tabela resumo consolidada com status, tempos e funções
                       │                                            │ objetivo.
   --in-place          │                  Booleano                  │ Grava as abas geradas (Ensalamento e Inconsistências)
                       │                                            │ diretamente no próprio arquivo Excel de entrada, sem criar
                       │                                            │ novas cópias.
   --output-dir        │          Diretório (Path)Default:          │ Pasta onde serão salvas as novas planilhas .xlsx processadas
                       │           instances/experiments            │ (quando --in-place não for ativado).
   --reports-dir       │      Diretório (Path)Default: reports      │ Pasta onde os relatórios diagnósticos de texto
                       │                                            │ (*_relatorio.txt) são salvos.
   --allow-integral    │                  Booleano                  │ Trata a disponibilidade Integral ou Ambos como flexível,
                       │                                            │ permitindo ao solver alocar o aluno na Manhã ou na Tarde para
                       │                                            │ otimizar o equilíbrio das salas.
   --allow-unallocated │                  Booleano                  │ Ativa a restrição suave de capacidade (∑ xᵢₖ + uᵢ = 1). Caso
                       │                                            │ falte vaga global, aloca o máximo possível de alunos e lista
                       │                                            │ os excedentes na lista de espera.
   --w-qtd             │             FloatDefault: 1.0              │ Peso de penalização para o desequilíbrio na quantidade total
                       │                                            │ de alunos entre turmas (W_{qtd}).
   --w-gen             │             FloatDefault: 1.0              │ Peso de penalização para o desequilíbrio de gênero entre
                       │                                            │ turmas (W_{gen}).
   --epsilon           │             FloatDefault: 1e-4             │ Peso de suavização intra-turma para aproximar cada sala da
                       │                                            │ paridade 50% Feminino / 50% Masculino.
   --no-phase2         │                  Booleano                  │ Desativa a Fase 2, parando a otimização imediatamente após
                       │                                            │ encontrar a solução ótima da Fase 1 (Min-Max).
   --auto-phase2       │                  Booleano                  │ Pula a Fase 2 de forma inteligente quando o perfil de turmas
                       │                                            │ da Fase 1 já for matematicamente único (ex: amplitude ≤ 1).
   --legacy-monolithic │                  Booleano                  │ Executa o modelo monolítico antigo com variáveis individuais
                       │                                            │ xᵢₖ por aluno (destinado a comparação e benchmarks).
   --time-limit        │           Inteiro (s)Default: 60           │ Tempo limite máximo em segundos por fase de otimização do CBC.
   --solver-verbose    │                  Booleano                  │ Imprime no console os logs brutos e iterações de Branch-and-
                       │                                            │ Bound do solver CBC.
  ──────

### Exemplos Práticos de Uso

#### 1. Resolver uma planilha individual com relatório detalhado:

    python src/main.py instances/public/instancia_1.xlsx

#### 2. Resolver salvando o resultado dentro da própria planilha (--in-place):

    python src/main.py instances/public/instancia_1.xlsx --in-place

#### 3. Permitir flexibilidade de turno para quem marcou "Integral/Ambos":

    python src/main.py instances/public/instancia_2.xlsx --allow-integral

#### 4. Rodar todo o lote de instâncias públicas e geradas com tabela resumo:

    python src/main.py --all --summary-only

  Exemplo de saída do lote:

    ================================================================================================================
     RESUMO DO LOTE EXECUTADO (4 instâncias)
    ================================================================================================================
      Instância                              | Status     |    Alocados | S/Turma |   Z1* | Z2_puro* |  Tempo Solver
      ------------------------------------------------------------------------------------------------------------
      instancia_1                            | Optimal    |     100/100 |       0 |     2 |       12 |       84.2 ms
      instancia_2                            | Optimal    |     300/300 |       0 |     4 |       28 |      112.5 ms
      instancia_3                            | Optimal    |     500/500 |       0 |     3 |       40 |      145.0 ms
      instancia_4                            | Optimal    |   1200/1200 |       0 |     5 |       96 |      290.4 ms
    ================================================================================================================
  ──────

## 🖥 Aplicativo Desktop Gráfico (GUI)

  O projeto inclui uma aplicação desktop profissional, 100% offline, construída com arquitetura desacoplada: WSGI local (Bottle) +
  PyWebView (WebView2) + Grid Tabulator reativo.

### Como Rodar a Aplicação Python

  Para abrir o aplicativo diretamente via código-fonte Python:

    python src/app/__main__.py

  (ou equivalentemente: python -m src.app)
  ──────

### Recursos e Funcionamento da Interface

1. Visualizador e Editor de Planilhas em Memória:
   • Abas dinâmicas para navegar entre Alunos, Turmas, Inconsistências e Ensalamento.
   • Edição de células in-place com clique duplo, persistência de largura de colunas e paginação de alta performance.
   • Histórico de alterações com Desfazer / Refazer ilimitado (Ctrl+Z / Ctrl+Y).
   • Botões para Inserir Linha, Inserir Coluna e Excluir Registros.
2. Auditoria Visual de Inconsistências:
   • Destaque automático em cores para erros de Regra 1 (Turma inexistente) e Regra 2 (Turno divergente).
   • Botão "Resolver Problema" para correção com 1 clique (ex: mover aluno para turma compatível ou alterar disponibilidade).
3. Solver Integrado de 1 Clique:
   • Botão "Executar Ensalamento" que roda o modelo MILP diretamente da memória da aplicação.
   • Configuração rápida de pesos, limites de tempo e opção de flexibilização de turnos.
4. Assistente Inteligente Offline (Chatbot):
   • Painel lateral com assistente determinístico que responde a perguntas em linguagem natural sobre métricas da turma,
   percentuais de gênero, contagem de inconsistências e diagnósticos.
5. Exportação de Listas de Presença em PDF:
   • Gera folhas de chamada prontas para impressão formatadas por turma, turno e professor.

  ──────

### Diagramas e Telas da Aplicação

#### Estrutura Visual da Janela Desktop

    +----------------------------------------------------------------------------------------------------+
    | [Logo ABC] UniSoma Ensalamento | Arquivo: instancia_1.xlsx [Salvar] [Salvar Como...] [Exportar PDF] |
    +----------------------------------------------------------------------------------------------------+
    | [Alunos (100)]  [Turmas (4)]  [Inconsistências (2)]  [Ensalamento (100)]        | Filtro: [Buscar...] |
    +----------------------------------------------------------------------------------+-----------------+
    | + Inserir Aluno  | + Inserir Coluna | - Excluir Linha | Desfazer (Ctrl+Z)        |  ASSISTENTE IA  |
    +----+--------------------+---------+--------------+--------------+----------------+  (Offline)      |
    | ID | Nome               | Gênero  | Turno        | Turma        | Status         |                 |
    +----+--------------------+---------+--------------+--------------+----------------+ "Quantos alunos |
    | 1  | Ana Clara Silva    | F       | Manhã        | Turma A      | OK             |  temos no turno |
    | 2  | Bruno Henrique     | M       | Tarde        | Turma B      | OK             |  da manhã?"     |
    | 3  | Carlos Eduardo     | M       | Manhã        | Turma C [!]  | ERRO REGRA 2   |                 |
    |    |                    |         |              |              | [Corrigir]     | > 50 alunos na  |
    +----+--------------------+---------+--------------+--------------+----------------+ Manhã e 50 na   |
    | CARDS DE MÉTRICAS EM TEMPO REAL:                                                 | Tarde. 0 sem    |
    | [ Total Alunos: 100 ] [ Vagas: 120 ] [ Desvio Gênero: 0 ] [ Status: Ótimo ]    | vaga.           |
    +----------------------------------------------------------------------------------+-----------------+
    | [ ⚙️ Configurar Parâmetros ]                     [ ⚡ EXECUTAR ENSALAMENTO OTIMIZADO ]            |
    +----------------------------------------------------------------------------------------------------+

#### Fluxo de Uso do Usuário

  │ Diagram exceeds terminal width (136 > 135 cols)
  │ Displayed as code block. Widen terminal to view inline.

    sequenceDiagram
        autonumber
        actor Usuario as Gestor Escolar
        participant UI as Interface Desktop (WebView2)
        participant Backend as Backend WSGI (AppBackend)
        participant Solver as Solver MILP (PuLP/CBC)
        participant PDF as Gerador PDF (ReportLab)

        Usuario->>UI: Abre o arquivo .xlsx
        UI->>Backend: load_excel(caminho)
        Backend->>UI: Exibe dados em abas e destaca inconsistências (R1/R2)

        opt Correção Rápida
            Usuario->>UI: Clica em "Resolver" na linha com inconsistência
            UI->>Backend: resolve_issue(tipo, id)
            Backend-->>UI: Planilha atualizada e validada
        end

        Usuario->>UI: Clica em "Executar Ensalamento"
        UI->>Backend: run_ensalamento(parametros)
        Backend->>Solver: solve_ensalamento(instancia)
        Solver-->>Backend: Solução Ótima (Alocação, Métricas, Z1*, Z2*)
        Backend-->>UI: Cria aba 'Ensalamento' e exibe métricas no Dashboard

        Usuario->>UI: Clica em "Exportar Listas PDF"
        UI->>Backend: export_pdf(caminho)
        Backend->>PDF: generate_class_lists_pdf()
        PDF-->>Usuario: Salva PDF com listas de chamada por sala
  ──────

## 📦 Geração do Executável Autônomo (.EXE)

  O projeto possui um arquivo de especificação dedicado (UniSomaEnsalamento.spec) que empacota automaticamente o interpretador
  Python, o solver CBC binário, as rotinas de PDF e toda a interface HTML/CSS/JS em um arquivo único executável para Windows.

### Passo a Passo para Compilar o .EXE

1. Certifique-se de que o ambiente virtual está ativo e com as dependências instaladas:
   pip install pyinstaller pywebview bottle reportlab pulp openpyxl pythonnet
2. Execute o PyInstaller apontando para a especificação:
   pyinstaller --clean UniSomaEnsalamento.spec
3. O executável pronto será gerado em:
   dist/UniSomaEnsalamento.exe

### Características do Executável Gerado

  • Zero Instalação Externa: O usuário final não precisa ter Python, PuLP ou solvers instalados na máquina.
  • Solver CBC Embarcado: O binário nativo do solver CBC de 64 bits é copiado diretamente para dentro do executável.
  • Sem Tela Preta de Terminal: Compilado com a opção console=False, abrindo diretamente como um aplicativo nativo do Windows com
  ícone e janelas integradas.
  • Totalmente Offline: Não requer acesso à internet para funcionar.
  ──────

## 📂 Estrutura do Repositório

    desafio_unisoma_2026/
    │
    ├── UniSomaEnsalamento.spec    # Arquivo de especificação para compilação do PyInstaller
    ├── requirements.txt            # Dependências centrais do projeto
    ├── README.md                   # Documentação do projeto
    ├── Validador.exe               # Validador oficial de soluções do desafio
    │
    ├── src/                        # Código-fonte principal
    │   ├── main.py                 # Ponto de entrada CLI (orquestrador de lote e flags)
    │   ├── read_instance.py        # Leitor robusto de planilhas Excel (.xlsx)
    │   ├── pre_process.py          # Higienização, detecção de R1/R2 e perfis demográficos
    │   ├── pos_process.py          # Gravação das abas Ensalamento/Inconsistências e relatórios
    │   │
    │   ├── models/                 # Modelagem matemática
    │   │   ├── solver.py           # Solver MILP Lexicográfico em 2 Fases (PuLP/CBC)
    │   │   └── benchmark_phase2.py # Scripts de validação e benchmark de desempenho
    │   │
    │   └── app/                    # Aplicativo Desktop
    │       ├── __main__.py         # Inicializador do app desktop (PyWebView + Bottle)
    │       ├── server.py           # Backend do editor, assistente determinístico e solver
    │       ├── pdf_lists.py        # Geração de listas de chamada em PDF com ReportLab
    │       ├── images/             # Logotipos e recursos gráficos
    │       └── static/             # Frontend HTML5, CSS3 e Tabulator.js
    │
    ├── instances/                  # Conjuntos de dados
    │   ├── public/                 # Instâncias públicas oficiais de teste
    │   ├── generated/              # Instâncias sintéticas de estresse (até 50.000 alunos)
    │   └── experiments/            # Saída padrão das planilhas processadas
    │
    ├── reports/                    # Relatórios diagnósticos em formato .txt
    ├── tests/                      # Bateria de testes de estresse, robustez e regressão
    └── dist/                       # Pasta onde o executável .exe é gerado
  ──────

## 🏆 Créditos

  Desenvolvido pela Equipe 10 / Grupo 20 para o Desafio UniSoma 2026.
