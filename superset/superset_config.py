# Configurações do Apache Superset para o Projeto Movidesk
import os

SECRET_KEY = os.environ.get("SUPERSET_SECRET_KEY") or "movidesk_superset_super_secret_key_2026"

ROW_LIMIT = 50000
SUPERSET_WEBSERVER_PORT = 8088
SUPERSET_WEBSERVER_TIMEOUT = 120

# Compatibilidade com proxy reverso / acesso HTTP interno ou túnel
ENABLE_PROXY_FIX = True
TALISMAN_ENABLED = False
WTF_CSRF_ENABLED = False
CONTENT_SECURITY_POLICY_WARNING = False

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
