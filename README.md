# MovideskDashboard — Plataforma de Inteligência Operacional (Movidesk + Apache Superset)

Sistema corporativo de inteligência de dados e operação desenvolvido para a **Advice Compliance Solutions** acompanhar em tempo real a operação de suporte técnico, métricas preditivas de SLA, gargalos de desenvolvimento/atendimento, saúde de carteira (Radar de Churn) e vazão de equipes.

---

## 🏗️ Arquitetura Atualizada da Solução

```text
[API Movidesk REST (/tickets, /persons)]
        │  ▲  (Paginação c/ backoff 503/504/429, rate-limit comercial/livre & cursor UTC)
        ▼
[MovideskControlPanel.exe (.NET 8 WinForms + Blazor Hybrid)]
   ├── Launcher Superset (WSL2 Ubuntu :8088 em background)
   ├── Monitor Dapper em Tempo Real (auto-refresh 5s + fronteira histórica)
   ├── Setup Automático Nativo C# (HttpClient -> REST API do Apache Superset)
   └── Orquestrador de Carga (Histórica c/ Cursor, Incremental & /persons)
   (Opcional CLI headless: src/Movidesk.Ingestion)
        │
        ▼
[Microsoft SQL Server (Localhost) — Banco MovideskDM (Horário BRT)]
   ├── raw  : Payloads JSON brutos (Ticket, Pessoa, *_Stage) para reprocessamento sem custo de API
   ├── core : Fatos e Dimensões normalizados (Fato_Ticket, StatusHistorico, SnapshotBacklog 90d, Dim_*)
   ├── ctl  : Controle de marca d'água, auditoria (ExecucaoCarga) e parâmetros dinâmicos (4h/48h/60d)
   ├── sec  : Mapeamento de segurança por equipe (Row-Level Security)
   └── mart : 9 Views Analíticas + 3 Covering Indexes de alta performance
        │
        ▼
[Apache Superset 6.1.0 (WSL2 Ubuntu :8088)]
   └── "Dashboard - Movidesk BI" (/superset/dashboard/dashboard-movidesk/)
       • 15 Gráficos em 4 Blocos Operacionais & Sucesso do Cliente
       • 3 Filtros Nativos Globais: Equipe (15 gráficos), Serviço (6 gráficos) e Período (2 gráficos)
```

---

## 🚀 Início Rápido — Instalação via Pacote Oficial (Recomendado)

A maneira mais rápida e recomendada de operar todo o ambiente no **Windows 10/11 (x64)** é utilizando o pacote pronto **`MovideskControlPanel-win-x64.zip`**, compilado automaticamente pelo GitHub Actions a cada release na branch `main`.

### 1. Subir o Banco de Dados (`MovideskDM`) no SQL Server Local
Na primeira instalação (ou após clonar o repositório), abra o **PowerShell** na raiz do projeto e execute:

```powershell
powershell -ExecutionPolicy Bypass -File .\deploy_local.ps1
```

Esse script executa automaticamente na ordem correta:
1. [`database/00_banco.sql`](database/00_banco.sql) — Cria o banco `MovideskDM` (`RECOVERY SIMPLE`, `COMPATIBILITY_LEVEL >= 140`).
2. [`database/01_tabelas.sql`](database/01_tabelas.sql) — Cria os 5 schemas (`raw`, `core`, `mart`, `ctl`, `sec`), tabelas e todos os índices (incluindo os 3 *covering indexes* do Raio-X e Clientes por Período).
3. [`database/02_carga_auxiliares.sql`](database/02_carga_auxiliares.sql) — Popula `Dim_Status`, `Dim_Calendario` (2022–2030), `ctl.Parametro` e `Dim_CampoCustomizado` (`#133948` Versão/Release).
4. [`database/04_procedure_processamento.sql`](database/04_procedure_processamento.sql) — Cria as procedures de processamento em Horário de Brasília (`BRT`) e Snapshot de 90 dias.
5. [`database/03_views_kpis.sql`](database/03_views_kpis.sql) — Cria todas as **9 Views** do schema `mart`.

> **Upgrades de ambientes existentes via SSMS:** Os scripts [`05_atualizacao_fuso_status_snapshot.sql`](database/05_atualizacao_fuso_status_snapshot.sql), [`06_alter_views_filtro_equipe.sql`](database/06_alter_views_filtro_equipe.sql), [`07_fix_backlog_sla_e_nova_view_clientes.sql`](database/07_fix_backlog_sla_e_nova_view_clientes.sql) e [`08_ajuste_raiox_e_servico_clientes_periodo.sql`](database/08_ajuste_raiox_e_servico_clientes_periodo.sql) aplicam as evoluções de schema/índices/views de forma idempotente caso seu banco tenha sido criado em uma versão anterior (e também são verificados automaticamente pelo Painel de Controle).

### 2. Executar o Painel de Controle Desktop (`MovideskControlPanel.exe`)
1. Baixe a release mais recente em [**GitHub Releases**](https://github.com/goncajeff-ui/MovideskDashboard/releases/latest) (`MovideskControlPanel-win-x64.zip`) e extraia **toda a pasta** (incluindo `wwwroot/`, `appsettings.json` e `setup_superset_auto.py`).
   * *(Alternativa local: execute [`Gerar_Executavel.bat`](Gerar_Executavel.bat) no Windows com .NET 8 SDK para compilar e gerar o atalho na Área de Trabalho).*
2. Confira a string de conexão SQL Server e o token Movidesk em [`appsettings.json`](src/Movidesk.ControlPanel/appsettings.json).
3. Abra o **`MovideskControlPanel.exe`** para gerenciar com cliques:
   * **Card 1 — Launcher Superset (WSL2):** Inicia/para o servidor Apache Superset na porta `8088` em background sem janelas extras.
   * **Card 2 — Monitor de Volumetria (MovideskDM):** Mostra em tempo real (`Dapper`) totais RAW/CORE, empresas/contatos vinculados, faixa de `#ID`, cursor histórico e dias de snapshot.
   * **Card Configuração Inicial do Superset (REST API Nativa C#):** Provisiona em 1 clique a conexão `MovideskDM`, os **9 Datasets `mart`**, os **15 Gráficos** e os **3 Filtros Nativos** do **`Dashboard - Movidesk BI`**.
   * **Card 3 — Orquestrador Anti-Travamento:** Dispara/retoma **Carga Histórica** (detecção automática de cursor UTC), **Carga Incremental** (preservando customizações manuais de views) e **Sincronizar Empresas (`/persons`)**.

### 3. Instalar o Apache Superset Base (WSL2 Ubuntu — Primeira Vez)
Consulte o guia atualizado em [`superset/README.md`](superset/README.md) para preparar o ambiente Python/WSL2 e aplicar [`superset/superset_config.py`](superset/superset_config.py) (`SUPERSET_WEBSERVER_TIMEOUT = 120`, `pt_BR`, `America/Sao_Paulo`, *Feature Flags*). Em seguida, use o próprio Painel de Controle (ou [`superset/setup_superset_auto.py`](superset/setup_superset_auto.py)) para publicar todo o Dashboard automaticamente.

---

## 📊 Catálogo do Dashboard — 9 Views `mart.*` & 15 Gráficos

Dashboard oficial: **`Dashboard - Movidesk BI`** (`/superset/dashboard/dashboard-movidesk/`), equipado com os filtros nativos **`Equipe`** (todos os 15 gráficos), **`Serviço`** (6 gráficos) e **`Período (Tickets por Cliente)`** (2 gráficos).

### Bloco 1 — Big Numbers (Saúde Imediata)
* **`mart.vw_VisaoGeralKpis`:** Alimenta os 6 cartões de topo por equipe (`KPI - Backlog Atual`, `KPI - SLA Vencidos`, `KPI - SLA Iminente (< 4h)`, `KPI - Abertos Hoje`, `KPI - Resolvidos Hoje`, `KPI - FCR 30 Dias (%)`), considerando precedência de `StatusBase` encerrado e SLA pausado efetivo (`SlaSolucaoPausado` / `Dim_Status.PausaSla`).

### Bloco 2 — Monitoramento de Fila e Vazão
* **`mart.vw_SlaRadar` → `Radar Preditivo de SLA (Fila Viva)`:** Ordena chamados abertos por `OrdemGravidade` e `MinutosParaVencer` (`Vencido`, `Crítico < 2h`, `Alerta < 4h`, `Atenção < 8h`).
* **`mart.vw_BacklogEvolucao` → `Evolução Diária do Backlog e SLA Vencido (90 Dias)`:** Série temporal em área (`echarts_area`, eixo X `DataSnapshot`) construída sobre `core.Fato_SnapshotBacklog`.
* **`mart.vw_ThroughputDiario` → `Throughput Diário: Abertos vs Resolvidos`:** Compara diariamente entradas, resoluções e `SaldoLiquido` sobre a `Dim_Calendario`.

### Bloco 3 — Auditoria e Gargalos (Eficiência)
* **`mart.vw_BacklogAging` → `Auditoria de Envelhecimento (Backlog Aging & +48h Sem Ação)`:** Faixas de idade da fila aberta (0–2d até >30d) e alerta configurável `SemInteracaoMais48h`.
* **`mart.vw_StatusAging` → `Gargalos Operacionais por Status (Horas Úteis e Corridas)`:** Tempo médio útil/corrido e horas totais acumuladas por etapa (ex.: *Dependência Dev* vs *Aguardando Cliente*).
* **`mart.vw_MapaDemanda` → `Mapa de Demanda por Serviço, Categoria e Versão Release`:** Pareto cruzando `Servico`, `Categoria`, `Urgencia` e campo customizado `#133948` (`VersaoProduto`).

### Bloco 4 — Sucesso do Cliente (CS, Churn & Período)
* **`mart.vw_ClienteRaioX` → `Raio-X de Empresas Clientes e Radar de Churn (Silenciosos > 60d)`:** Agregação *single-pass* de alta velocidade granularizada por **Empresa Cliente + Serviço**, atribuindo a `Equipe` pelo **Dono Atual (último ticket)** do produto/serviço e alertando clientes silenciosos (`> 60d`).
* **`mart.vw_TicketsPorClientePeriodo` → `Tickets Abertos por Cliente (Organização)` (Donut) & `Detalhamento de Tickets por Cliente no Período` (Grid com `%Total`):** Distribuição e ranking por **Cliente + Serviço** no período selecionado, filtráveis por `Equipe`, `Serviço` e `DataAbertura`.

---

## 📚 Documentação Corporativa e Manuais Oficiais (`docs/manuais/`)

| Documento | Descrição |
| :--- | :--- |
| [`Manual_01_Operacao_Painel_Controle_Movidesk_BI.pdf`](docs/manuais/Manual_01_Operacao_Painel_Controle_Movidesk_BI.pdf) | Guia operacional do `MovideskControlPanel.exe` (Launcher Superset, Monitor Dapper, Setup Automático e Cargas). |
| [`Manual_02_Configuracao_Apache_Superset_Corporativo.pdf`](docs/manuais/Manual_02_Configuracao_Apache_Superset_Corporativo.pdf) | Manual passo a passo do Apache Superset (Setup Automático, Conexão MSSQL, Datasets, Gráficos, Role *Gamma* e Túnel *Ngrok*). |
| [`Manual_03_Dicionario_de_Dados_Completo.pdf`](docs/manuais/Manual_03_Dicionario_de_Dados_Completo.pdf) | Dicionário técnico completo de arquitetura (5 schemas, tabelas `raw`/`core`/`ctl`/`sec`, *covering indexes* e as 9 Views `mart`). |
| [`Manual_04_Leitura_Executiva_Dashboard_Movidesk_BI.pdf`](docs/manuais/Manual_04_Leitura_Executiva_Dashboard_Movidesk_BI.pdf) | Manual executivo ilustrado com 15 capturas reais (*O que é*, *Como ler* e *Ação Sugerida* para cada KPI e gráfico). |
| [`Historico_Passo_a_Passo_Projeto.md`](docs/manuais/Historico_Passo_a_Passo_Projeto.md) | Auditoria cronológica completa de todas as fases, commits, releases, correções e decisões técnicas do projeto. |

---

## ⚙️ Uso Alternativo via CLI (`src/Movidesk.Ingestion`)

Caso precise executar cargas manualmente ou em agendamentos *headless* fora do Painel de Controle:

```powershell
cd src\Movidesk.Ingestion
dotnet run -- teste         # Carga rápida dos 50 tickets mais recentes + processamento CORE
dotnet run -- historico     # Carga histórica completa (aceita skip inicial: dotnet run -- historico 15000)
dotnet run -- incremental   # Loop incremental contínuo em terminal
dotnet run -- pessoas       # Sincroniza organizações (/persons) e vínculos em Dim_Cliente
dotnet run -- processar     # Executa apenas core.usp_ProcessarTickets localmente
```

> **Dica de Rate-Limit (API Movidesk):** Entre **07:01 e 18:59 (BRT)** a API pública limita chamadas a **10 requisições/minuto**. A partir das **19h00** o tráfego é liberado para cargas históricas em alta velocidade. Tanto o Painel quanto o CLI ajustam o espaçamento automaticamente.
