# Guia de Instalação e Automação do Apache Superset no Windows 11 (WSL2 — Sem Docker)

Este guia ensina como preparar o **Apache Superset 6.1.0** no Windows 11 via **WSL2 (Ubuntu)**, conectar ao **Microsoft SQL Server (`MovideskDM`)** e provisionar automaticamente todo o **`Dashboard - Movidesk BI`** (Database + **9 Datasets `mart`** + **15 Gráficos** + **3 Filtros Nativos Globais**).

---

## 1. Instalação Base do Apache Superset no WSL2 (Ubuntu)

> Como o Superset foi projetado para ambientes Linux/Unix, executá-lo no WSL2 evita compilações pesadas no Python do Windows e mantém o ambiente isolado e estável.

### Passo 1: Instalar WSL2 + Ubuntu (caso ainda não tenha)
No **PowerShell como Administrador**:
```powershell
wsl --install
```

### Passo 2: Instalar dependências, drivers SQL Server e Apache Superset no Ubuntu (WSL)
```bash
# 1. Atualizar pacotes e instalar dependências ODBC / FreeTDS / Python
sudo apt update && sudo apt install -y python3-pip python3-venv unixodbc unixodbc-dev freetds-dev freetds-bin curl gnupg

# 2. (Opcional se for usar pyodbc além de pymssql) Microsoft ODBC Driver 18 para SQL Server
curl -fsSL https://packages.microsoft.com/keys/microsoft.asc | sudo gpg --dearmor -o /usr/share/keyrings/microsoft-prod.gpg
curl -fsSL https://packages.microsoft.com/config/ubuntu/22.04/prod.list | sudo tee /etc/apt/sources.list.d/mssql-release.list
sudo apt update && sudo ACCEPT_EULA=Y apt install -y msodbcsql18

# 3. Criar ambiente virtual e instalar Superset + conectores SQL Server
python3 -m venv ~/superset-env
source ~/superset-env/bin/activate
pip install --upgrade pip
pip install apache-superset pymssql pyodbc pillow

# 4. Aplicar superset_config.py do repositório (pt_BR, BRT, Timeout 120s e Feature Flags)
mkdir -p ~/.superset
cp /mnt/c/<CAMINHO_DO_REPO>/MovideskDashboard/superset/superset_config.py ~/.superset/superset_config.py

# 5. Inicializar metadados do Superset e criar usuário administrador
export SUPERSET_SECRET_KEY="movidesk_superset_super_secret_key_2026"
export SUPERSET_CONFIG_PATH="$HOME/.superset/superset_config.py"
superset db upgrade
superset fab create-admin --username admin --firstname Admin --lastname Movidesk --email admin@advice.com.br --password admin
superset init
```

> **Dica de Timeout (`superset_config.py`):** O arquivo [`superset_config.py`](superset_config.py) do projeto já define `SUPERSET_WEBSERVER_TIMEOUT = 120`, `ROW_LIMIT = 50000`, `BABEL_DEFAULT_LOCALE = "pt_BR"`, `BABEL_DEFAULT_TIMEZONE = "America/Sao_Paulo"` e habilita `DASHBOARD_NATIVE_FILTERS`, `DASHBOARD_CROSS_FILTERS` e `GENERIC_CHART_AXES`.

### Passo 3: Iniciar o Superset
* **Pelo Painel de Controle Windows (Recomendado):** Abra `MovideskControlPanel.exe` e clique em **"Iniciar Superset (WSL2)"** (ele sobe o servidor silenciosamente na porta `8088` e monitora `/health`).
* **Ou manualmente no terminal WSL2:**
  ```bash
  source ~/superset-env/bin/activate
  export SUPERSET_SECRET_KEY="movidesk_superset_super_secret_key_2026"
  export SUPERSET_CONFIG_PATH="$HOME/.superset/superset_config.py"
  superset run -h 0.0.0.0 -p 8088 --with-threads
  ```

Acesse no navegador: **`http://localhost:8088`** (`admin` / `admin`).

---

## 2. Provisionamento Automático do Dashboard (Recomendado)

Com o Superset **Online** em `http://localhost:8088` e o banco `MovideskDM` criado no SQL Server, **não é necessário criar datasets nem gráficos na mão**.

### Opção A — Diretamente pelo Painel de Controle Windows (`MovideskControlPanel.exe`) *(Mais Simples)*
1. No card **"Configuração Inicial do Superset"** do Painel de Controle, digite a senha do usuário `admin`.
2. Clique em **"Executar Setup Automático"**.
3. O motor **nativo em C# (`HttpClient` via REST API, sem depender de terminal WSL)** executa automaticamente em sequência:
   * Garante que todas as Views `mart.*` e índices no SQL Server estão atualizados;
   * Cria/valida a Database Connection `MovideskDM`;
   * Registra e sincroniza colunas/dimensões dos **9 Datasets** do schema `mart`;
   * Cria/atualiza todos os **15 Gráficos** e publica **`Dashboard - Movidesk BI`** (`/superset/dashboard/dashboard-movidesk/`);
   * Vincula corretamente o `chartsInScope` dos **3 Filtros Nativos (`Equipe`, `Serviço`, `Período`)**.

### Opção B — Via Script Python CLI (Zero Dependências Externas)
Se estiver direto no Ubuntu/WSL2, execute [`setup_superset_auto.py`](setup_superset_auto.py):
```bash
python3 setup_superset_auto.py --url http://localhost:8088 --username admin --password admin
```
*(Aceita também `--db-uri "mssql+pymssql://sa:123456@<IP_WINDOWS>:1433/MovideskDM"` para sobrescrever o IP detectado automaticamente).*

---

## 3. Referência da Conexão SQL Server & Catálogo Oficial

### SQLAlchemy URI (WSL2 → SQL Server no Windows Host)
* **Driver padrão recomendado (sem necessidade de driver ODBC externo no container/WSL):**
  ```text
  mssql+pymssql://sa:123456@<IP_DO_HOST_WINDOWS>:1433/MovideskDM
  ```
  *(Para descobrir o IP do host Windows dentro do WSL2: `ip route | awk '/default/ {print $3}'`)*.
* **Alternativa ODBC Driver 18:**
  ```text
  mssql+pyodbc://sa:123456@<IP_DO_HOST_WINDOWS>:1433/MovideskDM?driver=ODBC+Driver+18+for+SQL+Server&TrustServerCertificate=yes
  ```

### Datasets Oficiais (`schema mart`) & Mapa dos 15 Gráficos

| # | Dataset (`mart.vw_*`) | Coluna Temporal | Gráficos Alimentados no `Dashboard - Movidesk BI` |
| :-: | :--- | :--- | :--- |
| 1 | `mart.vw_VisaoGeralKpis` | *Snapshot Atual* | **6 Big Numbers de Topo:** `KPI - Backlog Atual`, `KPI - SLA Vencidos`, `KPI - SLA Iminente (< 4h)`, `KPI - Abertos Hoje`, `KPI - Resolvidos Hoje`, `KPI - FCR 30 Dias (%)`. |
| 2 | `mart.vw_SlaRadar` | `DataCriacao` | `Radar Preditivo de SLA (Fila Viva)` — Tabela ordenada por `OrdemGravidade` e `MinutosParaVencer` *(Filtro: Equipe + Serviço)*. |
| 3 | `mart.vw_BacklogEvolucao` | `DataSnapshot` | `Evolução Diária do Backlog e SLA Vencido (90 Dias)` — Gráfico `echarts_area` *(Filtro: Equipe)*. |
| 4 | `mart.vw_ThroughputDiario` | `Data` | `Throughput Diário: Abertos vs Resolvidos` — Gráfico `echarts_timeseries_bar` *(Filtro: Equipe)*. |
| 5 | `mart.vw_BacklogAging` | `DataCriacao` | `Auditoria de Envelhecimento (Backlog Aging & +48h Sem Ação)` — *(Filtro: Equipe + Serviço)*. |
| 6 | `mart.vw_StatusAging` | *Agregado* | `Gargalos Operacionais por Status (Horas Úteis e Corridas)` — *(Filtro: Equipe)*. |
| 7 | `mart.vw_MapaDemanda` | *Agregado* | `Mapa de Demanda por Serviço, Categoria e Versão Release` (`#133948`) — *(Filtro: Equipe + Serviço)*. |
| 8 | `mart.vw_ClienteRaioX` | `DataUltimoTicket` | `Raio-X de Empresas Clientes e Radar de Churn (Silenciosos > 60d)` — Agregação por **Cliente + Serviço** e **Equipe Dono Atual (Último Ticket)** *(Filtro: Equipe + Serviço)*. |
| 9 | `mart.vw_TicketsPorClientePeriodo` | `DataAbertura` | **Donut** `Tickets Abertos por Cliente (Organização)` (`pie`) + **Grid** `Detalhamento de Tickets por Cliente no Período` (`table` com `%Total`) por **Cliente + Serviço** *(Filtros: Equipe + Serviço + Período)*. |

> **Manual Ilustrado:** Para instruções detalhadas de acesso para Diretoria (*Role `Gamma`*), publicação via *Ngrok* e leitura operacional de cada gráfico, consulte [`../docs/manuais/Manual_02_Configuracao_Apache_Superset_Corporativo.pdf`](../docs/manuais/Manual_02_Configuracao_Apache_Superset_Corporativo.pdf) e [`../docs/manuais/Manual_04_Leitura_Executiva_Dashboard_Movidesk_BI.pdf`](../docs/manuais/Manual_04_Leitura_Executiva_Dashboard_Movidesk_BI.pdf).
