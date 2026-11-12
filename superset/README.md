# Guia de Instalação e Execução do Apache Superset no Windows 11 (Sem Docker)

Este guia ensina o caminho mais rápido e oficial para rodar o **Apache Superset** no Windows 11 conectando ao seu SQL Server Developer local.

---

## Método Recomendado: Via WSL2 (Ubuntu no Windows 11)

Como o Superset foi feito para ambientes Linux/Unix, rodar no WSL2 leva menos de 5 minutos, não polui seu Windows e é 10x mais estável que compilar pacotes C++ no Python do Windows.

### Passo 1: Abrir o PowerShell como Administrador e instalar o WSL (se ainda não tiver)
```powershell
wsl --install
```
*(Caso já tenha o Ubuntu no Windows, basta abrir o terminal do Ubuntu).*

### Passo 2: No terminal do Ubuntu (WSL), instalar os pré-requisitos e o Superset
```bash
# 1. Atualizar pacotes e instalar dependências do ODBC e Python
sudo apt update && sudo apt install -y python3-pip python3-venv unixodbc unixodbc-dev curl gnupg

# 2. Instalar o Microsoft ODBC Driver 18 para SQL Server no Ubuntu
curl -fsSL https://packages.microsoft.com/keys/microsoft.asc | sudo gpg --dearmor -o /usr/share/keyrings/microsoft-prod.gpg
curl -fsSL https://packages.microsoft.com/config/ubuntu/22.04/prod.list | sudo tee /etc/apt/sources.list.d/mssql-release.list
sudo apt update
sudo ACCEPT_EULA=Y apt install -y msodbcsql18

# 3. Criar o ambiente virtual e instalar o Apache Superset + conector SQL Server
python3 -m venv ~/superset-env
source ~/superset-env/bin/activate
pip install --upgrade pip
pip install apache-superset pyodbc pymssql pillow

# 4. Inicializar o banco de metadados do Superset e criar o usuário administrador
export SUPERSET_SECRET_KEY="movidesk_superset_super_secret_key_2026"
superset db upgrade
superset fab create-admin --username admin --firstname Admin --lastname Movidesk --email admin@advice.com.br --password admin
superset init
```

### Passo 3: Iniciar o Superset
```bash
export SUPERSET_SECRET_KEY="movidesk_superset_super_secret_key_2026"
superset run -p 8088 --with-threads --reload --debugger
```

Abra o seu navegador no Windows em: **`http://localhost:8088`**
- **Usuário:** `admin`
- **Senha:** `admin`

---

## Como conectar o Superset no seu SQL Server Local

1. No menu superior direito do Superset, clique em **+ → Data → Connect Database**.
2. No popup, selecione **Microsoft SQL Server**.
3. No campo **SQLAlchemy URI**, preencha:
   ```text
   mssql+pyodbc://sa:123456@localhost:1433/MovideskDM?driver=ODBC+Driver+18+for+SQL+Server&TrustServerCertificate=yes
   ```
   *(Dica: Se estiver dentro do WSL2 conectando ao SQL Server que está no Windows host, use o IP do host ou `host.docker.internal` se configurado, ou o IP local da sua máquina exibido em `ipconfig` no Windows).*
4. Clique em **Test Connection**. Ao aparecer o check verde ✅, clique em **Connect**.

---

## Datasets Prontos (Views para Adicionar)

Vá em **Datasets → + Dataset** e adicione as seguintes views do schema `mart`:

1. `mart.vw_VisaoGeralKpis` → Cards com Big Numbers (Backlog Atual, SLA Vencido, SLA Iminente 4h, Vazão Hoje, % FCR).
2. `mart.vw_SlaRadar` → Tabela preditiva com contagem regressiva para estourar SLA, cores de urgência e links.
3. `mart.vw_StatusAging` → Gráfico de barras empilhadas: tempo médio gasto em dependência de terceiros/dev vs analista.
4. `mart.vw_BacklogAging` → Gráfico de barras por faixa de idade (0-2d, 3-5d, >30d) e flag de chamados sem interação há >48h.
5. `mart.vw_ThroughputDiario` → Gráfico de linha temporal: Abertos vs Resolvidos por dia.
6. `mart.vw_ClienteRaioX` → Tabela de saúde e risco de cancelamento (clientes sem chamados há mais de 60 dias).
7. `mart.vw_MapaDemanda` → Gráfico de Pareto por Versão de Software (KN1, e-Guardian, etc.) e Categoria.
