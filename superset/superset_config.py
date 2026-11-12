# Configurações do Apache Superset para o Projeto Movidesk
import os

ROW_LIMIT = 50000
SUPERSET_WEBSERVER_PORT = 8088

# Fuso Horário de Brasília
BABEL_DEFAULT_LOCALE = "pt_BR"
BABEL_DEFAULT_TIMEZONE = "America/Sao_Paulo"

# Habilita filtros avançados e Dashboard Cross Filters
FEATURE_FLAGS = {
    "DASHBOARD_CROSS_FILTERS": True,
    "DASHBOARD_NATIVE_FILTERS": True,
    "GENERIC_CHART_AXES": True,
    "ALERT_REPORTS": True
}

# String de conexão sugerida para o SQL Server no Superset:
# mssql+pyodbc://sa:123456@localhost:1433/MovideskDM?driver=ODBC+Driver+18+for+SQL+Server&TrustServerCertificate=yes
