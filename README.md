# MovideskDashboard — Painel de Operações e Inteligência (Movidesk + Apache Superset)

Sistema de inteligência de dados e painel gerencial corporativo desenvolvido para a gestão e diretoria acompanharem em tempo real a operação de suporte técnico, com métricas preditivas de SLA, controle de gargalos (dependência de desenvolvimento), monitoramento de churn e eficiência de equipes.

---

## 🏗️ Arquitetura da Solução

```
[API Movidesk REST]
        │
        ▼ (lotes / paginação com controle de rate-limit)
[Worker C# .NET 8] ─── Ingestor de alta performance (Histórico + Incremental a cada 5 min)
        │
        ▼
[SQL Server Developer (Localhost)] ─── Banco MovideskDM
   ├── raw  : JSON bruto dos tickets e pessoas (para reprocessamento rápido sem custo de API)
   ├── core : Fatos e Dimensões normalizados (Fato_Ticket, Dim_Equipe, Dim_Agente, Dim_Cliente, Dim_Status)
   ├── mart : Views Analíticas com KPIs pré-calculados (SLA Radar, Status Aging, Backlog Aging, FCR, Throughput)
   └── ctl  : Controle de marcas d'água, auditoria e logs de execução
        │
        ▼
[Apache Superset (BI)] ─── Dashboards Gerenciais e Executivos
```

---

## 🚀 Como Rodar o Projeto na Sua Máquina (Windows 11)

### 1. Criar o Banco e Tabelas no SQL Server Local (1 Comando)
Abra o **PowerShell** na raiz do projeto e execute:
```powershell
powershell -ExecutionPolicy Bypass -File .\deploy_local.ps1
```
Esse script executa automaticamente em ordem:
- `database/00_banco.sql` (Cria o banco `MovideskDM`)
- `database/01_tabelas.sql` (Cria os schemas `raw`, `core`, `mart`, `ctl`, `sec` e tabelas fato/dimensão)
- `database/02_carga_auxiliares.sql` (Popula status mapeados, calendário 2022-2030 e parâmetros)
- `database/04_procedure_processamento.sql` (Cria a procedure de normalização RAW -> CORE)
- `database/03_views_kpis.sql` (Cria todas as views consumidas pelo Superset)
- Compila o Worker C# e faz uma carga de teste com os 50 tickets mais recentes da API.

---

### 2. Cargas do Ingestor C# (.NET 8)

Entre na pasta do Ingestor:
```powershell
cd src\Movidesk.Ingestion
```

Comandos disponíveis:

* **Carga de Teste Rápida (50 tickets mais recentes):**
  ```powershell
  dotnet run -- teste
  ```
* **Carga Histórica Completa (~55 mil tickets desde 2022):**
  > **Dica:** O Movidesk tem limite de 10 requisições por minuto durante o dia (07:01 às 18:59). **A partir das 19h o acesso é irrestrito!** Recomenda-se rodar a carga histórica completa à noite para terminar em poucos minutos.
  ```powershell
  dotnet run -- historico
  ```
* **Carga Incremental Contínua (a cada 5 minutos em background):**
  ```powershell
  dotnet run -- incremental
  ```
* **Sincronizar Cadastro de Empresas/Pessoas:**
  ```powershell
  dotnet run -- pessoas
  ```

---

### 3. Subir o Apache Superset (Windows 11 sem Docker)

Consulte o passo a passo detalhado em [`superset/README.md`](file:///home/antigravity/goncajeff-ui/MovideskDashboard/superset/README.md).

Em resumo, via **WSL2** (Ubuntu):
```bash
# 1. Ativar ambiente e rodar o Superset
source ~/superset-env/bin/activate
export SUPERSET_SECRET_KEY="movidesk_superset_super_secret_key_2026"
superset run -p 8088 --with-threads --reload --debugger
```
Acesse no navegador: **`http://localhost:8088`** (admin / admin).

---

## 📊 Módulos e KPIs Disponíveis

### A. Módulo de Gestão de Fila e Eficiência
* **SLA Radar (`mart.vw_SlaRadar`):** Termômetro preditivo por cores. Exibe tickets que estourarão nas próximas horas (`Crítico < 2h`, `Alerta < 4h`, `Atenção < 8h`).
* **Termômetro de Gargalos (`mart.vw_StatusAging`):** Tempo médio e total gasto em "Dependência Dev (Ticket Filho)" vs "Aguardando Cliente" vs "Com Analista".
* **Backlog Aging (`mart.vw_BacklogAging`):** Distribuição da idade da fila (0-2d, 3-5d, >30d) e flag para chamados sem interação há mais de 48 horas.
* **Throughput Diário (`mart.vw_ThroughputDiario`):** Volume de chamados Abertos vs Resolvidos por dia e saldo líquido.
* **FCR (First Contact Resolution):** % de chamados resolvidos na primeira interação.

### B. Módulo de Inteligência de Clientes
* **Raio-X do Cliente (`mart.vw_ClienteRaioX`):** Total histórico, chamados abertos, % de cumprimento de SLA e data do último ticket.
* **Radar de Clientes Silenciosos:** Clientes ativos que não abrem chamado há mais de 60 dias (mitigação proativa de Churn).
* **Mapa de Demanda (`mart.vw_MapaDemanda`):** Volumetria agrupada por Categoria, Urgência e Versão de Software (ex: KN1, e-Guardian, Aquilla).
