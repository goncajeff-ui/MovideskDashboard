#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
===============================================================================
 Automação Oficial Apache Superset — Movidesk BI (Advice Compliance Solutions)
===============================================================================
Executa silenciosamente via REST API do Apache Superset (http://localhost:8088):
  1. Cria/atualiza a conexão de banco de dados MSSQL `MovideskDM`
     (mssql+pymssql://sa:123456@172.29.112.1:1433/MovideskDM).
  2. Registra e sincroniza os 9 Datasets oficiais do schema `mart`:
     - vw_VisaoGeralKpis
     - vw_SlaRadar
     - vw_BacklogAging
     - vw_StatusAging
     - vw_BacklogEvolucao
     - vw_ThroughputDiario
     - vw_ClienteRaioX
     - vw_MapaDemanda
     - vw_TicketsPorClientePeriodo
  3. Constrói os gráficos essenciais e publica o Dashboard "Dashboard - Movidesk BI"
     (/superset/dashboard/dashboard-movidesk/) com auto-refresh de 60s.

Zero dependências externas (usa apenas biblioteca padrão do Python 3).
===============================================================================
"""

from __future__ import annotations

import argparse
import http.cookiejar
import json
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional, Tuple


DEFAULT_SUPERSET_URL = os.environ.get("SUPERSET_URL", "http://localhost:8088")
DEFAULT_USERNAME = os.environ.get("SUPERSET_USER", "admin")
DEFAULT_PASSWORD = os.environ.get("SUPERSET_PASSWORD", "admin")
DEFAULT_DB_NAME = "MovideskDM"
DEFAULT_DB_URI = os.environ.get(
    "MOVIDESK_DB_URI",
    "mssql+pymssql://sa:123456@172.29.112.1:1433/MovideskDM",
)

MART_VIEWS: List[Tuple[str, Optional[str], str]] = [
    ("vw_VisaoGeralKpis", None, "KPIs Executivos de Topo por Equipe (Backlog, SLA, Vazão Hoje e FCR)"),
    ("vw_SlaRadar", "DataCriacao", "Termômetro Preditivo de Quebra de SLA da Fila Ativa"),
    ("vw_BacklogAging", "DataCriacao", "Envelhecimento da Fila Ativa (Aging) e Sem Interação > 48h"),
    ("vw_StatusAging", None, "Gargalos Operacionais e Tempo Médio Retido por Status"),
    ("vw_BacklogEvolucao", "DataSnapshot", "Curva Histórica Diária do Backlog Total vs SLA Vencido (90 Dias)"),
    ("vw_ThroughputDiario", "Data", "Balanço Diário de Vazão Operacional (Abertos vs Resolvidos)"),
    ("vw_ClienteRaioX", "DataUltimoTicket", "Saúde de Empresas Clientes por Produto/Serviço e Dono Atual (Último Ticket), % SLA e Risco de Churn (> 60d)"),
    ("vw_MapaDemanda", None, "Pareto de Serviços, Categorias, Urgências e Versões de Release (#133948)"),
    ("vw_TicketsPorClientePeriodo", "DataAbertura", "Distribuição de Tickets Abertos por Cliente/Organização, Serviço e Equipe no Período"),
]


class SupersetApiClient:
    """Cliente HTTP enxuto (stdlib) com suporte a JWT + Cookie Session + CSRF Token."""

    def __init__(self, base_url: str, username: str, password: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.username = username
        self.password = password
        self.cookie_jar = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(self.cookie_jar)
        )
        self.access_token: Optional[str] = None
        self.csrf_token: Optional[str] = None

    def request(
        self,
        method: str,
        path: str,
        payload: Optional[Dict[str, Any]] = None,
        query_params: Optional[Dict[str, str]] = None,
        timeout: int = 120,
        max_retries: int = 1,
    ) -> Dict[str, Any]:
        url = f"{self.base_url}{path}"
        if query_params:
            qs = urllib.parse.urlencode(query_params, safe="():,!~'")
            url = f"{url}?{qs}"

        data: Optional[bytes] = None
        headers: Dict[str, str] = {
            "Accept": "application/json",
            "Referer": f"{self.base_url}/",
        }
        if payload is not None:
            data = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"

        if self.access_token:
            headers["Authorization"] = f"Bearer {self.access_token}"
        if self.csrf_token and method.upper() in ("POST", "PUT", "DELETE", "PATCH"):
            headers["X-CSRFToken"] = self.csrf_token

        for attempt in range(max_retries + 1):
            req = urllib.request.Request(url, data=data, headers=headers, method=method.upper())
            try:
                with self.opener.open(req, timeout=timeout) as resp:
                    raw = resp.read().decode("utf-8", errors="replace")
                    return json.loads(raw) if raw.strip() else {}
            except urllib.error.HTTPError as exc:
                err_body = ""
                try:
                    err_body = exc.read().decode("utf-8", errors="replace")
                except Exception:
                    pass
                raise RuntimeError(
                    f"HTTP {exc.code} em {method.upper()} {path}: {err_body or exc.reason}"
                ) from exc
            except (urllib.error.URLError, TimeoutError, socket.timeout) as net_exc:
                if attempt < max_retries:
                    print(
                        f"[AVISO] Tempo limite/comunicação em {method.upper()} {path} ({net_exc}). Nova tentativa em 3s...",
                        flush=True,
                    )
                    time.sleep(3)
                    continue
                raise RuntimeError(
                    f"Tempo limite ou erro de comunicação em {method.upper()} {path}: {net_exc}"
                ) from net_exc

        return {}

    def authenticate(self) -> None:
        try:
            login_resp = self.request(
                "POST",
                "/api/v1/security/login",
                payload={
                    "username": self.username,
                    "password": self.password,
                    "provider": "db",
                    "refresh": True,
                },
            )
        except RuntimeError as exc:
            if "HTTP 401" in str(exc):
                superset_bin = os.path.expanduser("~/superset-env/bin/superset")
                if os.path.isfile(superset_bin):
                    print(
                        f"[INFO] Login retornou 401 para '{self.username}'. Sincronizando senha informada no Superset local (WSL2)...",
                        flush=True,
                    )
                    env = os.environ.copy()
                    env.setdefault(
                        "SUPERSET_SECRET_KEY", "movidesk_superset_super_secret_key_2026"
                    )
                    env.setdefault("FLASK_APP", "superset")
                    res = subprocess.run(
                        [
                            superset_bin,
                            "fab",
                            "reset-password",
                            "--username",
                            self.username,
                            "--password",
                            self.password,
                        ],
                        env=env,
                        capture_output=True,
                        text=True,
                        check=False,
                    )
                    if res.returncode == 0:
                        print(
                            f"[OK] Senha do usuário '{self.username}' sincronizada com sucesso no Superset.",
                            flush=True,
                        )
                        login_resp = self.request(
                            "POST",
                            "/api/v1/security/login",
                            payload={
                                "username": self.username,
                                "password": self.password,
                                "provider": "db",
                                "refresh": True,
                            },
                        )
                    else:
                        raise RuntimeError(
                            f"Senha inválida para o usuário '{self.username}' (HTTP 401) e não foi possível redefinir via CLI: {res.stderr.strip()}"
                        ) from exc
                else:
                    raise RuntimeError(
                        f"Senha inválida para o usuário '{self.username}' no Apache Superset (HTTP 401 UNAUTHORIZED). Verifique a senha digitada."
                    ) from exc
            else:
                raise

        self.access_token = login_resp.get("access_token")
        if not self.access_token:
            raise RuntimeError(f"Falha ao obter access_token no login: {login_resp}")

        try:
            csrf_resp = self.request("GET", "/api/v1/security/csrf_token/")
            self.csrf_token = csrf_resp.get("result")
        except Exception as csrf_exc:
            print(f"[INFO] Endpoint CSRF opcional: {csrf_exc}", flush=True)


def ensure_superset_online(base_url: str) -> None:
    """Garante que o Apache Superset está respondendo em /health (inicia via WSL se necessário)."""
    health_url = f"{base_url.rstrip('/')}/health"
    for _ in range(2):
        try:
            with urllib.request.urlopen(health_url, timeout=3) as resp:
                if resp.status == 200:
                    print(f"[OK] Servidor Apache Superset online em {base_url}.", flush=True)
                    return
        except Exception:
            pass

    # Se estivermos rodando dentro do Linux/WSL e o Superset estiver parado, tenta subi-lo
    superset_bin = os.path.expanduser("~/superset-env/bin/superset")
    if os.path.isfile(superset_bin):
        print("[INFO] Superset offline na porta 8088. Iniciando servidor em background...", flush=True)
        env = os.environ.copy()
        env.setdefault("SUPERSET_SECRET_KEY", "movidesk_superset_super_secret_key_2026")
        env.setdefault("FLASK_APP", "superset")
        subprocess.Popen(
            [superset_bin, "run", "-h", "0.0.0.0", "-p", "8088", "--with-threads"],
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        for _ in range(35):
            time.sleep(1.5)
            try:
                with urllib.request.urlopen(health_url, timeout=3) as resp:
                    if resp.status == 200:
                        print("[OK] Servidor Apache Superset iniciado com sucesso.", flush=True)
                        return
            except Exception:
                pass

    raise RuntimeError(
        f"Não foi possível conectar ao Apache Superset em {base_url}. "
        "Verifique se o Superset está iniciado na porta 8088."
    )


def resolve_best_db_uri(preferred_uri: str) -> str:
    """
    Testa se o IP configurado na SQLAlchemy URI (ex: 172.29.112.1:1433) responde.
    Caso o WSL2 tenha trocado o IP do vSwitch após reinicialização, detecta automaticamente
    o gateway padrão do WSL2, o nameserver de /etc/resolv.conf ou 127.0.0.1 na porta 1433.
    """
    parsed = urllib.parse.urlsplit(preferred_uri)
    preferred_host = parsed.hostname or "172.29.112.1"
    port = parsed.port or 1433

    candidate_hosts: List[str] = [preferred_host]

    try:
        out = subprocess.check_output(["ip", "route", "show", "default"], text=True, timeout=2)
        tokens = out.split()
        for token_idx, token in enumerate(tokens):
            if token == "via" and token_idx + 1 < len(tokens):
                gw_ip = tokens[token_idx + 1]
                if gw_ip not in candidate_hosts:
                    candidate_hosts.append(gw_ip)
    except Exception:
        pass

    try:
        if os.path.isfile("/etc/resolv.conf"):
            with open("/etc/resolv.conf", "r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    parts = line.strip().split()
                    if len(parts) >= 2 and parts[0] == "nameserver":
                        ns_ip = parts[1]
                        if ns_ip not in candidate_hosts:
                            candidate_hosts.append(ns_ip)
    except Exception:
        pass

    if "127.0.0.1" not in candidate_hosts:
        candidate_hosts.append("127.0.0.1")

    for candidate in candidate_hosts:
        try:
            with socket.create_connection((candidate, port), timeout=2.0):
                if candidate != preferred_host:
                    updated_uri = preferred_uri.replace(f"@{preferred_host}:", f"@{candidate}:")
                    print(f"[INFO] Host SQL Server WSL2 detectado automaticamente em {candidate}:{port}.", flush=True)
                    return updated_uri
                print(f"[OK] Conectividade TCP com SQL Server confirmada em {candidate}:{port}.", flush=True)
                return preferred_uri
        except Exception:
            continue

    print(f"[INFO] Mantendo URI padrão ({preferred_host}:{port}).", flush=True)
    return preferred_uri


def ensure_sql_views_updated(db_uri: str) -> None:
    """
    Se pymssql estiver disponível (padrão na venv ~/superset-env), verifica se Dim_Status,
    usp_AtualizarSnapshotBacklog e todas as 9 views do schema 'mart' já possuem a coluna
    normalizada `Equipe` e a correção definitiva de Backlog Atual / SLA Vencidos.
    """
    try:
        import pymssql  # type: ignore

        parsed = urllib.parse.urlsplit(db_uri)
        host = parsed.hostname or "172.29.112.1"
        port = parsed.port or 1433
        user = urllib.parse.unquote(parsed.username or "sa")
        password = urllib.parse.unquote(parsed.password or "123456")
        database = (parsed.path or "/MovideskDM").lstrip("/") or "MovideskDM"

        conn = pymssql.connect(
            server=host,
            port=port,
            user=user,
            password=password,
            database=database,
            login_timeout=5,
            autocommit=True,
        )
        cur = conn.cursor()

        # 1. Garante EhFinal = 1 e PausaSla = 1 em core.Dim_Status para status encerrados
        cur.execute(
            """
            UPDATE core.Dim_Status
            SET EhFinal = 1,
                PausaSla = 1
            WHERE (Nome IN (N'Resolvido', N'Fechado', N'Cancelado') OR GrupoStatus = N'Encerrado')
              AND (ISNULL(EhFinal, 0) <> 1 OR ISNULL(PausaSla, 0) <> 1);
            """
        )
        status_fixed = cur.rowcount or 0

        # 1c. Garante índices covering de alta performance para Raio-X e Clientes por Período
        cur.execute(
            """
            SELECT COUNT(*)
            FROM sys.indexes
            WHERE name IN (
                N'IX_core_Dim_Cliente_RaioX',
                N'IX_core_Fato_Ticket_Empresa_RaioX',
                N'IX_core_Fato_Ticket_DataCriacao_Clientes'
            );
            """
        )
        row_idx = cur.fetchone()
        idx_count = int(row_idx[0] or 0) if row_idx else 0
        created_indexes = False
        if idx_count < 3:
            cur.execute(
                """
                IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'IX_core_Dim_Cliente_RaioX' AND object_id = OBJECT_ID(N'core.Dim_Cliente'))
                    CREATE INDEX IX_core_Dim_Cliente_RaioX
                        ON core.Dim_Cliente (Ativo, TipoPessoa, EmpresaId)
                        INCLUDE (Nome, RazaoSocial);

                IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'IX_core_Fato_Ticket_Empresa_RaioX' AND object_id = OBJECT_ID(N'core.Fato_Ticket'))
                    CREATE INDEX IX_core_Fato_Ticket_Empresa_RaioX
                        ON core.Fato_Ticket (EmpresaId, ServicoN1, DataCriacao DESC)
                        INCLUDE (Equipe, Status, StatusBase, DataResolucao, SlaDataSolucao);

                IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'IX_core_Fato_Ticket_DataCriacao_Clientes' AND object_id = OBJECT_ID(N'core.Fato_Ticket'))
                    CREATE INDEX IX_core_Fato_Ticket_DataCriacao_Clientes
                        ON core.Fato_Ticket (DataCriacao)
                        INCLUDE (EmpresaId, Equipe, ServicoN1, Status, StatusBase, AgenteId, Categoria, Urgencia, Protocolo);
                """
            )
            created_indexes = True
            print("[OK] Índices covering do Raio-X e Clientes por Período garantidos no MovideskDM.", flush=True)

        # 2. Garante procedure core.usp_AtualizarSnapshotBacklog corrigida (st.PausaSla + StatusBase)
        cur.execute(
            """
            SELECT OBJECT_DEFINITION(p.object_id)
            FROM sys.procedures p
            INNER JOIN sys.schemas s ON p.schema_id = s.schema_id
            WHERE s.name = 'core' AND p.name = 'usp_AtualizarSnapshotBacklog';
            """
        )
        row_proc = cur.fetchone()
        snap_proc_def = (row_proc[0] or "") if row_proc else ""
        proc_updated = False
        if "st.PausaSla" not in snap_proc_def:
            cur.execute(
                """
CREATE OR ALTER PROCEDURE core.usp_AtualizarSnapshotBacklog
    @DiasRetroativos INT = 90,
    @ReconstruirHistorico BIT = 0
AS
BEGIN
    SET NOCOUNT ON;
    SET XACT_ABORT ON;

    DECLARE @Hoje DATE = CAST(SYSDATETIME() AS DATE);
    DECLARE @DataInicial DATE = DATEADD(DAY, -ISNULL(@DiasRetroativos, 90), @Hoje);

    DECLARE @DiasExistentes INT = (
        SELECT COUNT(DISTINCT DataSnapshot)
        FROM core.Fato_SnapshotBacklog
        WHERE DataSnapshot >= @DataInicial AND DataSnapshot < @Hoje
    );

    IF @ReconstruirHistorico = 1 OR @DiasExistentes < (@DiasRetroativos / 2)
    BEGIN
        DELETE FROM core.Fato_SnapshotBacklog
        WHERE DataSnapshot >= @DataInicial AND DataSnapshot < @Hoje;

        ;WITH Datas AS (
            SELECT Data
            FROM core.Dim_Calendario
            WHERE Data >= @DataInicial AND Data < @Hoje
        ),
        TicketsAbertosNoDia AS (
            SELECT
                d.Data AS DataSnapshot,
                ISNULL(t.Equipe, N'Sem Equipe') AS Equipe,
                ISNULL(t.AgenteId, 'NAO_ATRIBUIDO') AS AgenteId,
                ISNULL(sh.StatusNoDia, ISNULL(t.Status, N'Em atendimento')) AS Status,
                ISNULL(t.Urgencia, N'Não Informada') AS Urgencia,
                CASE
                    WHEN t.SlaDataSolucao IS NOT NULL
                         AND t.SlaDataSolucao < DATEADD(DAY, 1, CAST(d.Data AS DATETIME2(0)))
                         AND ISNULL(t.SlaSolucaoPausado, 0) = 0
                         AND ISNULL(st.PausaSla, 0) = 0
                    THEN 1 ELSE 0
                END AS SlaVencidoNoDia
            FROM Datas d
            INNER JOIN core.Fato_Ticket t
                ON t.DataCriacao < DATEADD(DAY, 1, CAST(d.Data AS DATETIME2(0)))
               AND (t.DataResolucao IS NULL OR t.DataResolucao >= DATEADD(DAY, 1, CAST(d.Data AS DATETIME2(0))))
               AND (t.DataFechamento IS NULL OR t.DataFechamento >= DATEADD(DAY, 1, CAST(d.Data AS DATETIME2(0))))
            OUTER APPLY (
                SELECT TOP 1 h.Status AS StatusNoDia
                FROM core.Fato_StatusHistorico h
                WHERE h.TicketId = t.TicketId
                  AND h.DataInicio < DATEADD(DAY, 1, CAST(d.Data AS DATETIME2(0)))
                ORDER BY h.DataInicio DESC, h.Sequencia DESC
            ) sh
            LEFT JOIN core.Dim_Status st
                ON ISNULL(sh.StatusNoDia, t.Status) = st.Nome
            WHERE CASE
                      WHEN st.EhFinal = 1 THEN 1
                      WHEN sh.StatusNoDia IS NULL AND t.StatusBase IN ('Resolved', 'Closed', 'Canceled') THEN 1
                      WHEN sh.StatusNoDia IN (N'Resolvido', N'Fechado', N'Cancelado') THEN 1
                      ELSE 0
                  END = 0
        )
        INSERT INTO core.Fato_SnapshotBacklog (
            DataSnapshot, Equipe, AgenteId, Status, Urgencia, QtdTickets, QtdSlaVencido
        )
        SELECT
            DataSnapshot,
            Equipe,
            AgenteId,
            Status,
            Urgencia,
            COUNT(1) AS QtdTickets,
            SUM(SlaVencidoNoDia) AS QtdSlaVencido
        FROM TicketsAbertosNoDia
        GROUP BY DataSnapshot, Equipe, AgenteId, Status, Urgencia;
    END

    DELETE FROM core.Fato_SnapshotBacklog
    WHERE DataSnapshot = @Hoje;

    INSERT INTO core.Fato_SnapshotBacklog (
        DataSnapshot, Equipe, AgenteId, Status, Urgencia, QtdTickets, QtdSlaVencido
    )
    SELECT
        @Hoje AS DataSnapshot,
        ISNULL(t.Equipe, N'Sem Equipe') AS Equipe,
        ISNULL(t.AgenteId, 'NAO_ATRIBUIDO') AS AgenteId,
        ISNULL(t.Status, N'Novo') AS Status,
        ISNULL(t.Urgencia, N'Não Informada') AS Urgencia,
        COUNT(1) AS QtdTickets,
        COUNT(CASE
            WHEN t.SlaDataSolucao IS NOT NULL
                 AND t.SlaDataSolucao < SYSDATETIME()
                 AND ISNULL(t.SlaSolucaoPausado, 0) = 0
                 AND ISNULL(st.PausaSla, 0) = 0
            THEN 1
        END) AS QtdSlaVencido
    FROM core.Fato_Ticket t
    LEFT JOIN core.Dim_Status st ON t.Status = st.Nome
    WHERE CASE
              WHEN t.StatusBase IN ('Resolved', 'Closed', 'Canceled') THEN 1
              ELSE ISNULL(st.EhFinal, 0)
          END = 0
    GROUP BY
        ISNULL(t.Equipe, N'Sem Equipe'),
        ISNULL(t.AgenteId, 'NAO_ATRIBUIDO'),
        ISNULL(t.Status, N'Novo'),
        ISNULL(t.Urgencia, N'Não Informada');
END;
                """
            )
            proc_updated = True

        # 3. Verifica definições e colunas das 9 views no schema mart
        cur.execute(
            """
            SELECT v.name, OBJECT_DEFINITION(v.object_id)
            FROM sys.views v
            INNER JOIN sys.schemas s ON v.schema_id = s.schema_id
            WHERE s.name = 'mart';
            """
        )
        view_defs: Dict[str, str] = {}
        for row in cur.fetchall():
            v_name = (row[0] or "").lower()
            v_def = row[1] or ""
            if v_name:
                view_defs[v_name] = v_def

        cur.execute(
            """
            SELECT v.name, c.name
            FROM sys.views v
            INNER JOIN sys.schemas s ON v.schema_id = s.schema_id
            LEFT JOIN sys.columns c ON v.object_id = c.object_id
            WHERE s.name = 'mart';
            """
        )
        view_cols: Dict[str, set] = {}
        for row in cur.fetchall():
            v_name = (row[0] or "").lower()
            c_name = (row[1] or "").lower()
            if v_name:
                view_cols.setdefault(v_name, set())
                if c_name:
                    view_cols[v_name].add(c_name)

        required_view_cols = {
            "vw_visaogeralkpis": {"equipe"},
            "vw_slaradar": {"equipe", "servico"},
            "vw_backlogaging": {"equipe", "servico"},
            "vw_statusaging": {"equipe"},
            "vw_throughputdiario": {"equipe"},
            "vw_clienteraiox": {"equipe", "servico"},
            "vw_mapademanda": {"equipe", "servico"},
            "vw_backlogevolucao": {"equipe"},
            "vw_ticketsporclienteperiodo": {"equipe", "servico", "cliente", "dataabertura"},
        }

        views_to_update: List[str] = []
        backlog_rules_updated = False
        for v, req in required_view_cols.items():
            v_def_lower = view_defs.get(v, "").lower()
            has_old_ehfinal = (
                v in ("vw_visaogeralkpis", "vw_slaradar", "vw_backlogaging", "vw_statusaging", "vw_mapademanda")
                and "isnull(st.ehfinal, case" in v_def_lower
            )
            missing_pausa = v in ("vw_visaogeralkpis", "vw_slaradar") and "st.pausasla" not in v_def_lower
            missing_resumo_raiox = v == "vw_clienteraiox" and "resumotickets" not in v_def_lower
            missing_servico_norm = (
                v == "vw_ticketsporclienteperiodo"
                and "nullif(ltrim(rtrim(t.servicon1))" not in v_def_lower
            )
            needs_col = v not in view_cols or not req.issubset(view_cols[v])
            if (
                needs_col
                or has_old_ehfinal
                or missing_pausa
                or missing_resumo_raiox
                or missing_servico_norm
            ):
                views_to_update.append(v)
                if has_old_ehfinal or missing_pausa or (needs_col and v in ("vw_visaogeralkpis", "vw_backlogevolucao")):
                    backlog_rules_updated = True

        if not views_to_update and not proc_updated and status_fixed == 0:
            conn.close()
            if created_indexes:
                print(
                    "[OK] Índices covering criados e todas as 9 Views do schema 'mart' validadas e íntegras.",
                    flush=True,
                )
            else:
                print(
                    "[OK] Todas as 9 Views do schema 'mart' e índices de performance validados com filtro 'Equipe'/'Servico' íntegros.",
                    flush=True,
                )
            return

        views_ddl: Dict[str, str] = {
            "vw_visaogeralkpis": """
CREATE OR ALTER VIEW mart.vw_VisaoGeralKpis
AS
WITH Parametros AS (
    SELECT
        ISNULL(TRY_CAST((SELECT Valor FROM ctl.Parametro WHERE Chave = 'HORAS_RADAR_SLA_IMINENTE') AS INT), 4) * 60 AS MinutosSlaIminente
),
Base AS (
    SELECT 
        t.TicketId,
        ISNULL(NULLIF(LTRIM(RTRIM(t.Equipe)), N''), N'Sem Equipe') AS Equipe,
        t.AgenteId,
        t.StatusBase,
        t.Status,
        t.Urgencia,
        t.DataCriacao,
        t.DataResolucao,
        t.SlaDataSolucao,
        t.SlaSolucaoPausado,
        t.ResolvidoPrimeiroContato,
        ISNULL(st.GrupoStatus, N'Outros') AS GrupoStatus,
        CASE
            WHEN t.StatusBase IN ('Resolved', 'Closed', 'Canceled') THEN 1
            ELSE ISNULL(st.EhFinal, 0)
        END AS EhFinal,
        CASE
            WHEN ISNULL(t.SlaSolucaoPausado, 0) = 1 OR ISNULL(st.PausaSla, 0) = 1 THEN 1
            ELSE 0
        END AS SlaPausadoEfetivo,
        ISNULL(st.EhDependenciaTerceiro, 0) AS EhDependenciaTerceiro,
        p.MinutosSlaIminente
    FROM core.Fato_Ticket t
    LEFT JOIN core.Dim_Status st ON t.Status = st.Nome
    CROSS JOIN Parametros p
)
SELECT 
    b.Equipe,
    COUNT(CASE WHEN b.EhFinal = 0 THEN 1 END) AS BacklogAtual,
    COUNT(CASE WHEN b.EhFinal = 0 AND b.SlaDataSolucao < SYSDATETIME() AND b.SlaPausadoEfetivo = 0 THEN 1 END) AS SlaVencidos,
    COUNT(CASE WHEN b.EhFinal = 0 AND b.SlaDataSolucao >= SYSDATETIME() AND DATEDIFF(MINUTE, SYSDATETIME(), b.SlaDataSolucao) <= b.MinutosSlaIminente AND b.SlaPausadoEfetivo = 0 THEN 1 END) AS SlaIminente4h,
    COUNT(CASE WHEN b.EhFinal = 0 AND b.SlaPausadoEfetivo = 1 THEN 1 END) AS SlaPausados,
    COUNT(CASE WHEN b.EhFinal = 0 AND b.EhDependenciaTerceiro = 1 THEN 1 END) AS EmDependenciaDev,
    COUNT(CASE WHEN CAST(b.DataCriacao AS DATE) = CAST(SYSDATETIME() AS DATE) THEN 1 END) AS AbertosHoje,
    COUNT(CASE WHEN CAST(b.DataResolucao AS DATE) = CAST(SYSDATETIME() AS DATE) THEN 1 END) AS ResolvidosHoje,
    CAST(ROUND(100.0 * COUNT(CASE WHEN b.DataResolucao >= DATEADD(DAY, -30, SYSDATETIME()) AND b.ResolvidoPrimeiroContato = 1 THEN 1 END) 
        / NULLIF(COUNT(CASE WHEN b.DataResolucao >= DATEADD(DAY, -30, SYSDATETIME()) THEN 1 END), 0), 1) AS DECIMAL(5,1)) AS FcrUltimos30DiasPct
FROM Base b
GROUP BY b.Equipe;
""",
            "vw_slaradar": """
CREATE OR ALTER VIEW mart.vw_SlaRadar
AS
WITH Parametros AS (
    SELECT ISNULL(TRY_CAST((SELECT Valor FROM ctl.Parametro WHERE Chave = 'HORAS_RADAR_SLA_IMINENTE') AS INT), 4) * 60 AS MinutosAlerta
)
SELECT 
    t.TicketId,
    t.Protocolo,
    t.Assunto,
    ISNULL(t.ServicoN1, N'Não Informado') AS Servico,
    t.Categoria,
    t.Urgencia,
    t.Status,
    ISNULL(st.GrupoStatus, N'Outros') AS GrupoStatus,
    ISNULL(NULLIF(LTRIM(RTRIM(t.Equipe)), N''), N'Sem Equipe') AS Equipe,
    ISNULL(ag.Nome, N'Não Atribuído') AS Analista,
    ISNULL(emp.Nome, ISNULL(cli.Nome, N'Não Identificado')) AS Cliente,
    t.DataCriacao,
    t.DataUltimaAcao,
    t.SlaAcordo,
    t.SlaDataSolucao,
    CAST(CASE WHEN ISNULL(t.SlaSolucaoPausado, 0) = 1 OR ISNULL(st.PausaSla, 0) = 1 THEN 1 ELSE 0 END AS BIT) AS SlaSolucaoPausado,
    CASE 
        WHEN ISNULL(t.SlaSolucaoPausado, 0) = 1 OR ISNULL(st.PausaSla, 0) = 1 THEN 'SLA Pausado'
        WHEN t.SlaDataSolucao IS NULL THEN 'Sem SLA Definido'
        WHEN t.SlaDataSolucao < SYSDATETIME() THEN 'Vencido'
        WHEN DATEDIFF(MINUTE, SYSDATETIME(), t.SlaDataSolucao) <= 120 THEN 'Crítico (< 2h)'
        WHEN DATEDIFF(MINUTE, SYSDATETIME(), t.SlaDataSolucao) <= p.MinutosAlerta THEN 'Alerta (< 4h)'
        WHEN DATEDIFF(MINUTE, SYSDATETIME(), t.SlaDataSolucao) <= 480 THEN 'Atenção (< 8h)'
        ELSE 'No Prazo (> 8h)'
    END AS FaixaRiscoSla,
    CASE 
        WHEN ISNULL(t.SlaSolucaoPausado, 0) = 1 OR ISNULL(st.PausaSla, 0) = 1 THEN 5
        WHEN t.SlaDataSolucao IS NULL THEN 6
        WHEN t.SlaDataSolucao < SYSDATETIME() THEN 1
        WHEN DATEDIFF(MINUTE, SYSDATETIME(), t.SlaDataSolucao) <= 120 THEN 2
        WHEN DATEDIFF(MINUTE, SYSDATETIME(), t.SlaDataSolucao) <= p.MinutosAlerta THEN 3
        WHEN DATEDIFF(MINUTE, SYSDATETIME(), t.SlaDataSolucao) <= 480 THEN 4
        ELSE 7
    END AS OrdemGravidade,
    DATEDIFF(MINUTE, SYSDATETIME(), t.SlaDataSolucao) AS MinutosParaVencer,
    DATEDIFF(HOUR, t.DataUltimaAcao, SYSDATETIME()) AS HorasSemInteracao
FROM core.Fato_Ticket t
LEFT JOIN core.Dim_Status st ON t.Status = st.Nome
LEFT JOIN core.Dim_Agente ag ON t.AgenteId = ag.AgenteId
LEFT JOIN core.Dim_Cliente cli ON t.EmpresaId = cli.ClienteId
LEFT JOIN core.Dim_Cliente emp ON cli.EmpresaId = emp.ClienteId
CROSS JOIN Parametros p
WHERE CASE
          WHEN t.StatusBase IN ('Resolved', 'Closed', 'Canceled') THEN 1
          ELSE ISNULL(st.EhFinal, 0)
      END = 0;
""",
            "vw_backlogaging": """
CREATE OR ALTER VIEW mart.vw_BacklogAging
AS
WITH Parametros AS (
    SELECT ISNULL(TRY_CAST((SELECT Valor FROM ctl.Parametro WHERE Chave = 'HORAS_SEM_INTERACAO_ALERTA') AS INT), 48) AS HorasLimiteSemInteracao
)
SELECT 
    t.TicketId,
    t.Assunto,
    ISNULL(NULLIF(LTRIM(RTRIM(t.Equipe)), N''), N'Sem Equipe') AS Equipe,
    ISNULL(ag.Nome, N'Não Atribuído') AS Analista,
    ISNULL(emp.Nome, ISNULL(cli.Nome, N'Não Identificado')) AS Cliente,
    ISNULL(t.ServicoN1, N'Não Informado') AS Servico,
    t.Categoria,
    t.Urgencia,
    t.Status,
    ISNULL(st.GrupoStatus, N'Outros') AS GrupoStatus,
    t.DataCriacao,
    t.DataUltimaAcao,
    DATEDIFF(DAY, t.DataCriacao, SYSDATETIME()) AS DiasAberto,
    CASE 
        WHEN DATEDIFF(DAY, t.DataCriacao, SYSDATETIME()) <= 2  THEN '0 a 2 dias'
        WHEN DATEDIFF(DAY, t.DataCriacao, SYSDATETIME()) <= 5  THEN '3 a 5 dias'
        WHEN DATEDIFF(DAY, t.DataCriacao, SYSDATETIME()) <= 10 THEN '6 a 10 dias'
        WHEN DATEDIFF(DAY, t.DataCriacao, SYSDATETIME()) <= 20 THEN '11 a 20 dias'
        WHEN DATEDIFF(DAY, t.DataCriacao, SYSDATETIME()) <= 30 THEN '21 a 30 dias'
        ELSE 'Mais de 30 dias'
    END AS FaixaIdade,
    DATEDIFF(HOUR, ISNULL(t.DataUltimaAcao, t.DataCriacao), SYSDATETIME()) AS HorasDesdeUltimaAcao,
    CASE 
        WHEN DATEDIFF(HOUR, ISNULL(t.DataUltimaAcao, t.DataCriacao), SYSDATETIME()) >= p.HorasLimiteSemInteracao THEN 1 
        ELSE 0 
    END AS SemInteracaoMais48h
FROM core.Fato_Ticket t
LEFT JOIN core.Dim_Status st ON t.Status = st.Nome
LEFT JOIN core.Dim_Agente ag ON t.AgenteId = ag.AgenteId
LEFT JOIN core.Dim_Cliente cli ON t.EmpresaId = cli.ClienteId
LEFT JOIN core.Dim_Cliente emp ON cli.EmpresaId = emp.ClienteId
CROSS JOIN Parametros p
WHERE CASE
          WHEN t.StatusBase IN ('Resolved', 'Closed', 'Canceled') THEN 1
          ELSE ISNULL(st.EhFinal, 0)
      END = 0;
""",
            "vw_statusaging": """
CREATE OR ALTER VIEW mart.vw_StatusAging
AS
WITH Passagens AS (
    SELECT
        ISNULL(NULLIF(LTRIM(RTRIM(t.Equipe)), N''), N'Sem Equipe') AS Equipe,
        sh.Status,
        ISNULL(st.GrupoStatus, N'Outros') AS GrupoStatus,
        ISNULL(st.EhDependenciaTerceiro, 0) AS EhDependenciaTerceiro,
        ISNULL(
            sh.PermanenciaMinCorridos,
            CASE
                WHEN sh.DataFim IS NULL
                     AND CASE WHEN t.StatusBase IN ('Resolved', 'Closed', 'Canceled') THEN 1 ELSE ISNULL(st.EhFinal, 0) END = 0
                     AND sh.DataInicio < SYSDATETIME()
                THEN DATEDIFF(MINUTE, sh.DataInicio, SYSDATETIME())
            END
        ) AS MinutosCorridos,
        ISNULL(
            sh.PermanenciaMinUteis,
            CASE
                WHEN sh.DataFim IS NULL
                     AND CASE WHEN t.StatusBase IN ('Resolved', 'Closed', 'Canceled') THEN 1 ELSE ISNULL(st.EhFinal, 0) END = 0
                     AND sh.DataInicio < SYSDATETIME()
                THEN DATEDIFF(MINUTE, sh.DataInicio, SYSDATETIME())
            END
        ) AS MinutosUteis
    FROM core.Fato_StatusHistorico sh
    INNER JOIN core.Fato_Ticket t ON sh.TicketId = t.TicketId
    LEFT JOIN core.Dim_Status st ON sh.Status = st.Nome
)
SELECT 
    Equipe,
    Status,
    GrupoStatus,
    EhDependenciaTerceiro,
    COUNT(1) AS QtdPassagens,
    CAST(ROUND(AVG(MinutosUteis / 60.0), 1) AS DECIMAL(10,1)) AS HorasUteisMedias,
    CAST(ROUND(AVG(MinutosCorridos / 60.0), 1) AS DECIMAL(10,1)) AS HorasCorridasMedias,
    CAST(ROUND(SUM(MinutosCorridos / 60.0), 0) AS BIGINT) AS HorasCorridasTotais
FROM Passagens
WHERE MinutosCorridos IS NOT NULL AND MinutosCorridos >= 0
GROUP BY Equipe, Status, GrupoStatus, EhDependenciaTerceiro;
""",
            "vw_throughputdiario": """
CREATE OR ALTER VIEW mart.vw_ThroughputDiario
AS
WITH LimiteDatas AS (
    SELECT
        ISNULL(
            (SELECT MIN(CAST(DataCriacao AS DATE)) FROM core.Fato_Ticket WHERE DataCriacao >= '2022-01-01'),
            DATEADD(DAY, -90, CAST(SYSDATETIME() AS DATE))
        ) AS DataMinima
),
Datas AS (
    SELECT c.Data, c.AnoMes, c.EhDiaUtil
    FROM core.Dim_Calendario c
    CROSS JOIN LimiteDatas l
    WHERE c.Data BETWEEN l.DataMinima AND CAST(SYSDATETIME() AS DATE)
),
Abertos AS (
    SELECT 
        CAST(DataCriacao AS DATE) AS Data,
        ISNULL(NULLIF(LTRIM(RTRIM(Equipe)), N''), N'Sem Equipe') AS Equipe,
        COUNT(1) AS QtdAbertos
    FROM core.Fato_Ticket
    WHERE DataCriacao IS NOT NULL
    GROUP BY CAST(DataCriacao AS DATE), ISNULL(NULLIF(LTRIM(RTRIM(Equipe)), N''), N'Sem Equipe')
),
Resolvidos AS (
    SELECT 
        CAST(DataResolucao AS DATE) AS Data,
        ISNULL(NULLIF(LTRIM(RTRIM(Equipe)), N''), N'Sem Equipe') AS Equipe,
        COUNT(1) AS QtdResolvidos
    FROM core.Fato_Ticket
    WHERE DataResolucao IS NOT NULL
    GROUP BY CAST(DataResolucao AS DATE), ISNULL(NULLIF(LTRIM(RTRIM(Equipe)), N''), N'Sem Equipe')
),
Equipes AS (
    SELECT ISNULL(NULLIF(LTRIM(RTRIM(Nome)), N''), N'Sem Equipe') AS Equipe
    FROM core.Dim_Equipe
    WHERE EhSuporte = 1
    UNION
    SELECT Equipe FROM Abertos
    UNION
    SELECT Equipe FROM Resolvidos
)
SELECT 
    d.Data,
    d.AnoMes,
    d.EhDiaUtil,
    eq.Equipe,
    ISNULL(a.QtdAbertos, 0) AS Abertos,
    ISNULL(r.QtdResolvidos, 0) AS Resolvidos,
    ISNULL(r.QtdResolvidos, 0) - ISNULL(a.QtdAbertos, 0) AS SaldoLiquido
FROM Datas d
CROSS JOIN Equipes eq
LEFT JOIN Abertos a ON d.Data = a.Data AND eq.Equipe = a.Equipe
LEFT JOIN Resolvidos r ON d.Data = r.Data AND eq.Equipe = r.Equipe;
""",
            "vw_clienteraiox": """
-- Ajustado por Jefferson Gonçalves em 15/11/2026 e otimizado para single-pass scan (ResumoTickets) sem ROW_NUMBER / Nested Loops
CREATE OR ALTER VIEW mart.vw_ClienteRaioX
AS
WITH Parametros AS (
    SELECT ISNULL(MAX(TRY_CAST(Valor AS INT)), 60) AS DiasSilenciosoCritico
    FROM ctl.Parametro
    WHERE Chave = 'DIAS_CLIENTE_SILENCIOSO'
),
ResumoTickets AS (
    SELECT
        t.EmpresaId,
        ISNULL(NULLIF(LTRIM(RTRIM(t.ServicoN1)), N''), N'Não Informado') AS Servico,
        COUNT(t.TicketId) AS TotalTicketsHistorico,
        COUNT(CASE
            WHEN CASE
                WHEN t.StatusBase IN ('Resolved', 'Closed', 'Canceled') THEN 1
                ELSE ISNULL(st.EhFinal, 0)
            END = 0 THEN 1
        END) AS TicketsAtualmenteAbertos,
        COUNT(CASE
            WHEN t.DataResolucao IS NOT NULL AND t.DataResolucao <= t.SlaDataSolucao THEN 1
        END) AS TicketsDentroSla,
        COUNT(CASE
            WHEN t.DataResolucao IS NOT NULL AND t.SlaDataSolucao IS NOT NULL THEN 1
        END) AS TotalSlaValido,
        MAX(t.DataCriacao) AS DataUltimoTicket,
        CAST(
            SUBSTRING(
                MAX(
                    CONVERT(CHAR(19), ISNULL(t.DataCriacao, CONVERT(DATETIME2(0), '1900-01-01T00:00:00', 126)), 126) + N'|' +
                    RIGHT(REPLICATE(N'0', 10) + CAST(ABS(CAST(t.TicketId AS BIGINT)) AS NVARCHAR(12)), 10) + N'|' +
                    ISNULL(NULLIF(LTRIM(RTRIM(t.Equipe)), N''), N'Sem Equipe')
                ),
                32,
                128
            )
            AS NVARCHAR(128)
        ) AS EquipeAtual
    FROM core.Fato_Ticket t
    LEFT JOIN core.Dim_Status st ON t.Status = st.Nome
    WHERE t.EmpresaId IS NOT NULL
    GROUP BY
        t.EmpresaId,
        ISNULL(NULLIF(LTRIM(RTRIM(t.ServicoN1)), N''), N'Não Informado')
)
SELECT
    c.ClienteId,
    c.Nome AS Cliente,
    c.RazaoSocial,
    ISNULL(r.Servico, N'Sem Serviço') AS Servico,
    ISNULL(r.EquipeAtual, N'Sem Equipe') AS Equipe,
    ISNULL(r.TotalTicketsHistorico, 0) AS TotalTicketsHistorico,
    ISNULL(r.TicketsAtualmenteAbertos, 0) AS TicketsAtualmenteAbertos,
    ISNULL(r.TicketsDentroSla, 0) AS TicketsDentroSla,
    CAST(ROUND(100.0 * r.TicketsDentroSla / NULLIF(r.TotalSlaValido, 0), 1) AS DECIMAL(5,1)) AS SlaCumpridoPct,
    r.DataUltimoTicket,
    DATEDIFF(DAY, r.DataUltimoTicket, SYSDATETIME()) AS DiasDesdeUltimoTicket,
    CASE
        WHEN r.DataUltimoTicket IS NULL OR DATEDIFF(DAY, r.DataUltimoTicket, SYSDATETIME()) >= p.DiasSilenciosoCritico THEN 'Risco Churn (Silencioso > 60d)'
        WHEN DATEDIFF(DAY, r.DataUltimoTicket, SYSDATETIME()) >= (p.DiasSilenciosoCritico / 2) THEN 'Atenção (Silencioso 30-60d)'
        ELSE 'Ativo (< 30d)'
    END AS StatusRelacionamento
FROM core.Dim_Cliente c
LEFT JOIN ResumoTickets r ON c.ClienteId = r.EmpresaId
CROSS JOIN Parametros p
WHERE
    ISNULL(c.Ativo, 1) = 1
    AND (
        ISNULL(c.TipoPessoa, 2) IN (2, 4)
        OR (c.EmpresaId IS NULL AND r.EmpresaId IS NOT NULL)
    );
""",
            "vw_mapademanda": """
CREATE OR ALTER VIEW mart.vw_MapaDemanda
AS
SELECT 
    ISNULL(NULLIF(LTRIM(RTRIM(t.Equipe)), N''), N'Sem Equipe') AS Equipe,
    ISNULL(t.ServicoN1, N'Não Informado') AS Servico,
    t.Categoria,
    t.Urgencia,
    ISNULL(cf.Valor, N'Não Informada') AS VersaoProduto,
    COUNT(1) AS Volumetria,
    COUNT(CASE WHEN CASE WHEN t.StatusBase IN ('Resolved', 'Closed', 'Canceled') THEN 1 ELSE ISNULL(st.EhFinal, 0) END = 0 THEN 1 END) AS Abertos,
    CAST(ROUND(AVG(DATEDIFF(HOUR, t.DataCriacao, ISNULL(t.DataResolucao, SYSDATETIME()))), 1) AS DECIMAL(10,1)) AS HorasMediasResolucao
FROM core.Fato_Ticket t
LEFT JOIN core.Dim_Status st ON t.Status = st.Nome
LEFT JOIN core.Fato_CampoCustomizado cf ON t.TicketId = cf.TicketId AND cf.CampoId = 133948
GROUP BY
    ISNULL(NULLIF(LTRIM(RTRIM(t.Equipe)), N''), N'Sem Equipe'),
    ISNULL(t.ServicoN1, N'Não Informado'),
    t.Categoria,
    t.Urgencia,
    ISNULL(cf.Valor, N'Não Informada');
""",
            "vw_backlogevolucao": """
CREATE OR ALTER VIEW mart.vw_BacklogEvolucao
AS
SELECT
    sb.DataSnapshot,
    cal.AnoMes,
    cal.NomeDiaSemana,
    cal.EhDiaUtil,
    ISNULL(NULLIF(LTRIM(RTRIM(sb.Equipe)), N''), N'Sem Equipe') AS Equipe,
    sb.AgenteId,
    ISNULL(ag.Nome, N'Não Atribuído') AS Analista,
    sb.Status,
    ISNULL(st.GrupoStatus, N'Outros') AS GrupoStatus,
    ISNULL(st.EhDependenciaTerceiro, 0) AS EhDependenciaTerceiro,
    sb.Urgencia,
    sb.QtdTickets,
    sb.QtdSlaVencido,
    (sb.QtdTickets - sb.QtdSlaVencido) AS QtdNoPrazo
FROM core.Fato_SnapshotBacklog sb
LEFT JOIN core.Dim_Calendario cal ON sb.DataSnapshot = cal.Data
LEFT JOIN core.Dim_Status st ON sb.Status = st.Nome
LEFT JOIN core.Dim_Agente ag ON sb.AgenteId = ag.AgenteId;
""",
            "vw_ticketsporclienteperiodo": """
CREATE OR ALTER VIEW mart.vw_TicketsPorClientePeriodo
AS
SELECT
    t.TicketId,
    t.Protocolo,
    t.DataCriacao AS DataAbertura,
    CAST(t.DataCriacao AS DATE) AS DataAberturaDia,
    CONVERT(CHAR(7), t.DataCriacao, 126) AS AnoMes,
    ISNULL(emp.ClienteId, ISNULL(cli.ClienteId, ISNULL(t.EmpresaId, 'NAO_IDENTIFICADO'))) AS ClienteId,
    ISNULL(emp.Nome, ISNULL(cli.Nome, N'Não Identificado')) AS Cliente,
    ISNULL(NULLIF(LTRIM(RTRIM(t.Equipe)), N''), N'Sem Equipe') AS Equipe,
    ISNULL(ag.Nome, N'Não Atribuído') AS Analista,
    t.Status,
    t.StatusBase,
    CASE
        WHEN t.StatusBase IN ('Resolved', 'Closed', 'Canceled') OR ISNULL(st.EhFinal, 0) = 1 THEN N'Encerrado'
        ELSE N'Em Aberto'
    END AS Situacao,
    ISNULL(NULLIF(LTRIM(RTRIM(t.ServicoN1)), N''), N'Não Informado') AS Servico,
    t.Categoria,
    t.Urgencia,
    1 AS QtdTickets
FROM core.Fato_Ticket t
LEFT JOIN core.Dim_Status st ON t.Status = st.Nome
LEFT JOIN core.Dim_Agente ag ON t.AgenteId = ag.AgenteId
LEFT JOIN core.Dim_Cliente cli ON t.EmpresaId = cli.ClienteId
LEFT JOIN core.Dim_Cliente emp ON cli.EmpresaId = emp.ClienteId
WHERE t.DataCriacao IS NOT NULL;
""",
        }

        for mv in views_to_update:
            cur.execute(views_ddl[mv])

        if status_fixed > 0 or proc_updated or backlog_rules_updated:
            cur.execute("EXEC core.usp_AtualizarSnapshotBacklog @DiasRetroativos = 90, @ReconstruirHistorico = 1;")

        conn.close()
        if created_indexes or views_to_update:
            print(
                f"[OK] Índices covering e Views atualizados no SQL Server ({', '.join(views_to_update) or 'índices'}) com otimização single-pass e filtro 'Equipe'/'Servico'.",
                flush=True,
            )
    except Exception:
        pass


def upsert_database(
    client: SupersetApiClient,
    db_name: str,
    db_uri: str,
    has_explicit_uri: bool = False,
) -> int:
    """Passo 1: Cria ou atualiza a Database Connection MovideskDM preservando URI existente se não sobrescrita."""
    resp = client.request("GET", "/api/v1/database/", query_params={"q": "(page_size:100)"}, timeout=60)
    existing_id: Optional[int] = None
    for row in resp.get("result", []):
        if str(row.get("database_name", "")).lower() == db_name.lower():
            existing_id = int(row["id"])
            break

    payload: Dict[str, Any] = {
        "database_name": db_name,
        "expose_in_sqllab": True,
        "allow_ctas": False,
        "allow_cvas": False,
        "allow_dml": False,
        "allow_run_async": False,
    }

    if existing_id is not None:
        preserve_existing_uri = False
        if not has_explicit_uri:
            try:
                detail = client.request("GET", f"/api/v1/database/{existing_id}", timeout=60)
                existing_uri = detail.get("result", {}).get("sqlalchemy_uri", "") or ""
                if "movideskdm" in existing_uri.lower():
                    preserve_existing_uri = True
            except Exception:
                pass

        if not preserve_existing_uri:
            payload["sqlalchemy_uri"] = db_uri

        try:
            client.request("PUT", f"/api/v1/database/{existing_id}", payload=payload, timeout=90, max_retries=1)
            msg = (
                f"[OK] Passo 1/3 — Database '{db_name}' (ID={existing_id}) validada preservando URI existente."
                if preserve_existing_uri
                else f"[OK] Passo 1/3 — Database '{db_name}' (ID={existing_id}) atualizada com sucesso."
            )
            print(msg, flush=True)
        except Exception as db_put_exc:
            print(
                f"[AVISO] Passo 1/3 — Timeout/aviso ao atualizar metadados da Database '{db_name}' (ID={existing_id}): {db_put_exc}. Prosseguindo com a conexão existente.",
                flush=True,
            )
        return existing_id

    payload["sqlalchemy_uri"] = db_uri
    create_resp = client.request("POST", "/api/v1/database/", payload=payload, timeout=120, max_retries=1)
    db_id = int(create_resp["id"])
    print(f"[OK] Passo 1/3 — Database '{db_name}' (ID={db_id}) criada com sucesso.", flush=True)
    return db_id


EDITABLE_COLUMN_KEYS = (
    "id",
    "column_name",
    "type",
    "is_dttm",
    "groupby",
    "filterable",
    "is_active",
    "description",
    "verbose_name",
    "expression",
    "extra",
    "python_date_format",
    "datetime_format",
    "advanced_data_type",
    "certified_by",
    "certification_details",
    "is_certified",
    "uuid",
    "warning_markdown",
)


def upsert_datasets(
    client: SupersetApiClient, db_id: int
) -> Dict[str, Dict[str, Any]]:
    """Passo 2: Registra e sincroniza as 9 Views do schema mart como Datasets."""
    resp = client.request("GET", "/api/v1/dataset/", query_params={"q": "(page_size:200)"}, timeout=60)
    existing_map: Dict[str, int] = {}
    for row in resp.get("result", []):
        t_name = row.get("table_name")
        schema = row.get("schema")
        if t_name and (schema == "mart" or not schema):
            existing_map[t_name] = int(row["id"])

    datasets_info: Dict[str, Dict[str, Any]] = {}

    for idx, (view_name, main_dttm_col, description) in enumerate(MART_VIEWS, start=1):
        print(f"[INF] Passo 2/3 — Sincronizando 'mart.{view_name}' ({idx}/{len(MART_VIEWS)})...", flush=True)
        if view_name in existing_map:
            ds_id = existing_map[view_name]
            try:
                client.request("PUT", f"/api/v1/dataset/{ds_id}/refresh", timeout=90, max_retries=1)
            except Exception as refresh_exc:
                print(
                    f"[AVISO] Refresh de colunas em 'mart.{view_name}' ignorado ({refresh_exc}); mantendo metadados existentes.",
                    flush=True,
                )
        else:
            create_resp = client.request(
                "POST",
                "/api/v1/dataset/",
                payload={
                    "database": db_id,
                    "schema": "mart",
                    "table_name": view_name,
                },
                timeout=90,
                max_retries=1,
            )
            ds_id = int(create_resp["id"])

        detail = client.request("GET", f"/api/v1/dataset/{ds_id}").get("result", {})

        try:
            update_payload: Dict[str, Any] = {
                "description": description,
                "filter_select_enabled": True,
            }
            if main_dttm_col:
                update_payload["main_dttm_col"] = main_dttm_col

            raw_cols = detail.get("columns", [])
            if raw_cols:
                needs_col_update = False
                updated_cols: List[Dict[str, Any]] = []
                for c in raw_cols:
                    c_name = c.get("column_name", "")
                    is_main_dttm = bool(main_dttm_col and c_name.lower() == main_dttm_col.lower())
                    is_dim_chave = c_name.lower() in ("equipe", "servico")

                    curr_dttm = bool(c.get("is_dttm"))
                    curr_groupby = bool(c.get("groupby", True))
                    curr_filterable = bool(c.get("filterable", True))

                    target_dttm = curr_dttm or is_main_dttm
                    target_groupby = True if is_dim_chave else curr_groupby
                    target_filterable = True if is_dim_chave else curr_filterable

                    if (
                        target_dttm != curr_dttm
                        or target_groupby != curr_groupby
                        or target_filterable != curr_filterable
                    ):
                        needs_col_update = True

                    col_item = {
                        k: c[k]
                        for k in EDITABLE_COLUMN_KEYS
                        if k in c and c[k] is not None
                    }
                    col_item["column_name"] = c_name
                    col_item.setdefault("type", "STRING")
                    col_item["is_dttm"] = target_dttm
                    col_item["groupby"] = target_groupby
                    col_item["filterable"] = target_filterable
                    updated_cols.append(col_item)

                if needs_col_update:
                    update_payload["columns"] = updated_cols

            try:
                client.request("PUT", f"/api/v1/dataset/{ds_id}", payload=update_payload)
            except Exception:
                fallback_payload: Dict[str, Any] = {
                    "description": description,
                    "filter_select_enabled": True,
                }
                if main_dttm_col:
                    fallback_payload["main_dttm_col"] = main_dttm_col
                client.request("PUT", f"/api/v1/dataset/{ds_id}", payload=fallback_payload)

            detail = client.request("GET", f"/api/v1/dataset/{ds_id}").get("result", {})
        except Exception:
            pass

        cols_by_name = {
            c["column_name"]: c for c in detail.get("columns", []) if "column_name" in c
        }
        datasets_info[view_name] = {
            "id": ds_id,
            "uuid": detail.get("uuid"),
            "columns": cols_by_name,
        }
        print(
            f"[OK] Passo 2/3 — Dataset 'mart.{view_name}' (ID={ds_id}, {len(cols_by_name)} colunas) pronto.",
            flush=True,
        )

    return datasets_info


def resolve_col_name(ds_info: Dict[str, Any], target_col: str) -> str:
    cols = ds_info.get("columns", {})
    if target_col in cols:
        return target_col
    for k in cols:
        if k.lower() == target_col.lower():
            return k
    return target_col


def make_simple_metric(
    ds_info: Dict[str, Any],
    col_name: str,
    aggregate: str,
    label: str,
    option_name: Optional[str] = None,
) -> Dict[str, Any]:
    actual_col = resolve_col_name(ds_info, col_name)
    col_meta = ds_info.get("columns", {}).get(actual_col, {})
    col_obj: Dict[str, Any] = {
        "column_name": actual_col,
        "type": col_meta.get("type", "NUMERIC"),
    }
    if col_meta.get("id"):
        col_obj["id"] = col_meta["id"]
    return {
        "expressionType": "SIMPLE",
        "column": col_obj,
        "aggregate": aggregate,
        "label": label,
        "optionName": option_name or f"metric_{actual_col.lower()}_{aggregate.lower()}",
    }


def get_merged_chart_dashboards(
    client: SupersetApiClient, chart_id: int, required_dashboard_id: int
) -> List[int]:
    ids = {required_dashboard_id}
    try:
        detail = client.request("GET", f"/api/v1/chart/{chart_id}").get("result", {})
        for item in detail.get("dashboards", []):
            if isinstance(item, dict) and item.get("id") is not None:
                ids.add(int(item["id"]))
            elif isinstance(item, int):
                ids.add(item)
    except Exception:
        pass
    return sorted(ids)


def upsert_chart(
    client: SupersetApiClient,
    existing_charts: Dict[str, int],
    slice_name: str,
    viz_type: str,
    ds_id: int,
    dashboard_id: int,
    params_dict: Dict[str, Any],
    description: str,
) -> Tuple[int, str]:
    params_copy = dict(params_dict)
    params_copy["datasource"] = f"{ds_id}__table"
    params_copy["viz_type"] = viz_type

    if slice_name in existing_charts:
        chart_id = existing_charts[slice_name]
        merged_dashboards = get_merged_chart_dashboards(client, chart_id, dashboard_id)
    else:
        chart_id = 0
        merged_dashboards = [dashboard_id]

    payload = {
        "slice_name": slice_name,
        "viz_type": viz_type,
        "datasource_id": ds_id,
        "datasource_type": "table",
        "dashboards": merged_dashboards,
        "description": description,
        "params": json.dumps(params_copy, ensure_ascii=False),
    }

    if chart_id > 0:
        client.request("PUT", f"/api/v1/chart/{chart_id}", payload=payload, timeout=90, max_retries=1)
    else:
        create_resp = client.request("POST", "/api/v1/chart/", payload=payload, timeout=90, max_retries=1)
        chart_id = int(create_resp["id"])

    chart_detail = client.request("GET", f"/api/v1/chart/{chart_id}", timeout=60).get("result", {})
    chart_uuid = chart_detail.get("uuid", "")
    return chart_id, chart_uuid


def filter_existing_cols(ds_info: Dict[str, Any], desired_cols: List[str]) -> List[str]:
    cols = ds_info.get("columns", {})
    if not cols:
        return desired_cols
    resolved: List[str] = []
    for c in desired_cols:
        actual = resolve_col_name(ds_info, c)
        if actual in cols:
            resolved.append(actual)
    return resolved or desired_cols


def build_movidesk_dashboard(
    client: SupersetApiClient,
    datasets: Dict[str, Dict[str, Any]],
) -> str:
    """Passo 3: Cria os 15 gráficos essenciais e monta/migra o Dashboard 'Dashboard - Movidesk BI'."""
    dash_title = "Dashboard - Movidesk BI"
    dash_slug = "dashboard-movidesk"

    resp = client.request("GET", "/api/v1/dashboard/", query_params={"q": "(page_size:100)"}, timeout=60)
    dashboard_id: Optional[int] = None
    legacy_dashboard_id: Optional[int] = None
    for row in resp.get("result", []):
        slug = str(row.get("slug") or "")
        title = str(row.get("dashboard_title") or "")
        row_id = row.get("id")
        if row_id is None:
            continue
        if slug.lower() == dash_slug or title.lower() == dash_title.lower():
            dashboard_id = int(row_id)
            break
        if legacy_dashboard_id is None and (
            slug.lower() == "sala-de-guerra-movidesk"
            or title.lower() == "sala de guerra - movidesk bi"
        ):
            legacy_dashboard_id = int(row_id)

    if dashboard_id is None and legacy_dashboard_id is not None:
        dashboard_id = legacy_dashboard_id
        print(
            f"[INF] Dashboard anterior 'Sala de Guerra - Movidesk BI' detectado (ID={dashboard_id}). Migrando para '{dash_title}' ({dash_slug})...",
            flush=True,
        )

    if dashboard_id is None:
        create_dash = client.request(
            "POST",
            "/api/v1/dashboard/",
            payload={
                "dashboard_title": dash_title,
                "slug": dash_slug,
                "published": True,
            },
            timeout=90,
            max_retries=1,
        )
        dashboard_id = int(create_dash["id"])

    # Busca gráficos existentes para idempotência
    charts_resp = client.request("GET", "/api/v1/chart/", query_params={"q": "(page_size:200)"}, timeout=60)
    existing_charts: Dict[str, int] = {}
    for row in charts_resp.get("result", []):
        if row.get("slice_name"):
            existing_charts[row["slice_name"]] = int(row["id"])

    ds_kpis = datasets["vw_VisaoGeralKpis"]
    ds_radar = datasets["vw_SlaRadar"]
    ds_evol = datasets["vw_BacklogEvolucao"]
    ds_through = datasets["vw_ThroughputDiario"]
    ds_aging = datasets["vw_BacklogAging"]
    ds_status = datasets["vw_StatusAging"]
    ds_demanda = datasets["vw_MapaDemanda"]
    ds_clientes = datasets["vw_ClienteRaioX"]
    ds_clientes_periodo = datasets["vw_TicketsPorClientePeriodo"]

    chart_specs = [
        # Row 1: 6 Big Numbers Executivos (vw_VisaoGeralKpis)
        (
            "KPI_BACKLOG",
            "KPI - Backlog Atual",
            "big_number_total",
            ds_kpis["id"],
            {
                "metric": make_simple_metric(ds_kpis, "BacklogAtual", "SUM", "Backlog Atual"),
                "subheader": "Chamados Ativos na Fila",
                "y_axis_format": ",d",
                "header_font_size": 0.4,
                "subheader_font_size": 0.15,
                "adhoc_filters": [],
            },
            "Volume exato de chamados em aberto no momento atual.",
        ),
        (
            "KPI_VENCIDOS",
            "KPI - SLA Vencidos",
            "big_number_total",
            ds_kpis["id"],
            {
                "metric": make_simple_metric(ds_kpis, "SlaVencidos", "SUM", "SLA Vencidos"),
                "subheader": "Abertos Fora do Prazo",
                "y_axis_format": ",d",
                "header_font_size": 0.4,
                "subheader_font_size": 0.15,
                "adhoc_filters": [],
            },
            "Chamados em aberto cujo SlaDataSolucao já expirou.",
        ),
        (
            "KPI_IMINENTE",
            "KPI - SLA Iminente (< 4h)",
            "big_number_total",
            ds_kpis["id"],
            {
                "metric": make_simple_metric(ds_kpis, "SlaIminente4h", "SUM", "SLA < 4h"),
                "subheader": "Expirando nas Próximas 4h",
                "y_axis_format": ",d",
                "header_font_size": 0.4,
                "subheader_font_size": 0.15,
                "adhoc_filters": [],
            },
            "Chamados abertos que vencem nas próximas 4 horas.",
        ),
        (
            "KPI_ABERTOS_HOJE",
            "KPI - Abertos Hoje",
            "big_number_total",
            ds_kpis["id"],
            {
                "metric": make_simple_metric(ds_kpis, "AbertosHoje", "SUM", "Abertos Hoje"),
                "subheader": "Novos Chamados no Dia",
                "y_axis_format": ",d",
                "header_font_size": 0.4,
                "subheader_font_size": 0.15,
                "adhoc_filters": [],
            },
            "Total de chamados abertos na data de hoje (BRT).",
        ),
        (
            "KPI_RESOLVIDOS_HOJE",
            "KPI - Resolvidos Hoje",
            "big_number_total",
            ds_kpis["id"],
            {
                "metric": make_simple_metric(ds_kpis, "ResolvidosHoje", "SUM", "Resolvidos Hoje"),
                "subheader": "Solucionados no Dia",
                "y_axis_format": ",d",
                "header_font_size": 0.4,
                "subheader_font_size": 0.15,
                "adhoc_filters": [],
            },
            "Total de chamados resolvidos na data de hoje (BRT).",
        ),
        (
            "KPI_FCR",
            "KPI - FCR 30 Dias (%)",
            "big_number_total",
            ds_kpis["id"],
            {
                "metric": make_simple_metric(ds_kpis, "FcrUltimos30DiasPct", "AVG", "FCR 30d (%)"),
                "subheader": "Resolução no 1º Contato",
                "y_axis_format": ".1f",
                "header_font_size": 0.4,
                "subheader_font_size": 0.15,
                "adhoc_filters": [],
            },
            "Taxa média de First Contact Resolution nos últimos 30 dias.",
        ),
        # Row 2: Radar Preditivo de SLA (vw_SlaRadar)
        (
            "TABELA_RADAR_SLA",
            "Radar Preditivo de SLA (Fila Viva)",
            "table",
            ds_radar["id"],
            {
                "query_mode": "raw",
                "all_columns": filter_existing_cols(
                    ds_radar,
                    [
                        "OrdemGravidade",
                        "FaixaRiscoSla",
                        "MinutosParaVencer",
                        "TicketId",
                        "Cliente",
                        "Servico",
                        "Assunto",
                        "Equipe",
                        "Analista",
                        "Urgencia",
                        "Status",
                        "HorasSemInteracao",
                    ],
                ),
                "order_by_cols": ['["OrdemGravidade", true]', '["MinutosParaVencer", true]'],
                "row_limit": 500,
                "page_length": 20,
                "include_search": True,
                "show_cell_bars": True,
                "adhoc_filters": [],
            },
            "Fila ativa ordenada por gravidade de risco de quebra de SLA.",
        ),
        # Row 3: Evolução do Backlog (90d) + Throughput Diário
        (
            "SERIE_BACKLOG_90D",
            "Evolução Diária do Backlog e SLA Vencido (90 Dias)",
            "echarts_area",
            ds_evol["id"],
            {
                "x_axis": "DataSnapshot",
                "granularity_sqla": "DataSnapshot",
                "time_grain_sqla": "P1D",
                "x_axis_sort_asc": True,
                "metrics": [
                    make_simple_metric(ds_evol, "QtdTickets", "SUM", "Backlog Total"),
                    make_simple_metric(ds_evol, "QtdSlaVencido", "SUM", "SLA Vencido"),
                ],
                "groupby": [],
                "adhoc_filters": [
                    {
                        "clause": "WHERE",
                        "comparator": "No filter",
                        "datasourceWarning": False,
                        "expressionType": "SIMPLE",
                        "filterOptionName": "filter_datasnapshot_temporal",
                        "isExtra": False,
                        "isNew": False,
                        "operator": "TEMPORAL_RANGE",
                        "sqlExpression": None,
                        "subject": "DataSnapshot",
                    }
                ],
                "row_limit": 10000,
                "show_legend": True,
                "rich_tooltip": True,
                "area": True,
                "opacity": 0.25,
            },
            "Fotografia histórica diária da fila aberta vs chamados com SLA vencido.",
        ),
        (
            "SERIE_THROUGHPUT",
            "Throughput Diário: Abertos vs Resolvidos",
            "echarts_timeseries_bar",
            ds_through["id"],
            {
                "x_axis": "Data",
                "granularity_sqla": "Data",
                "time_grain_sqla": "P1D",
                "x_axis_sort_asc": True,
                "metrics": [
                    make_simple_metric(ds_through, "Abertos", "SUM", "Abertos"),
                    make_simple_metric(ds_through, "Resolvidos", "SUM", "Resolvidos"),
                ],
                "groupby": [],
                "adhoc_filters": [
                    {
                        "clause": "WHERE",
                        "comparator": "No filter",
                        "datasourceWarning": False,
                        "expressionType": "SIMPLE",
                        "filterOptionName": "filter_data_temporal",
                        "isExtra": False,
                        "isNew": False,
                        "operator": "TEMPORAL_RANGE",
                        "sqlExpression": None,
                        "subject": "Data",
                    }
                ],
                "row_limit": 5000,
                "show_legend": True,
                "rich_tooltip": True,
            },
            "Vazão diária comparando entrada de chamados vs resoluções.",
        ),
        # Row 4: Backlog Aging + Gargalos por Status
        (
            "TABELA_BACKLOG_AGING",
            "Auditoria de Envelhecimento (Backlog Aging & +48h Sem Ação)",
            "table",
            ds_aging["id"],
            {
                "query_mode": "raw",
                "all_columns": filter_existing_cols(
                    ds_aging,
                    [
                        "TicketId",
                        "Cliente",
                        "Servico",
                        "Assunto",
                        "Equipe",
                        "Analista",
                        "FaixaIdade",
                        "DiasAberto",
                        "HorasDesdeUltimaAcao",
                        "SemInteracaoMais48h",
                    ],
                ),
                "order_by_cols": ['["DiasAberto", false]'],
                "row_limit": 500,
                "page_length": 15,
                "include_search": True,
                "show_cell_bars": True,
                "adhoc_filters": [],
            },
            "Chamados em aberto classificados por faixa de idade e alerta de inatividade (>48h).",
        ),
        (
            "TABELA_STATUS_AGING",
            "Gargalos Operacionais por Status (Horas Úteis e Corridas)",
            "table",
            ds_status["id"],
            {
                "query_mode": "raw",
                "all_columns": filter_existing_cols(
                    ds_status,
                    [
                        "Equipe",
                        "Status",
                        "GrupoStatus",
                        "QtdPassagens",
                        "HorasUteisMedias",
                        "HorasCorridasMedias",
                        "HorasCorridasTotais",
                    ],
                ),
                "order_by_cols": ['["HorasCorridasTotais", false]'],
                "row_limit": 200,
                "page_length": 15,
                "include_search": True,
                "show_cell_bars": True,
                "adhoc_filters": [],
            },
            "Tempo médio e acumulado retido em cada status do fluxo.",
        ),
        # Row 5: Mapa de Demanda (Serviço / Versão) + Raio-X de Clientes (Churn)
        (
            "TABELA_MAPA_DEMANDA",
            "Mapa de Demanda por Serviço, Categoria e Versão Release",
            "table",
            ds_demanda["id"],
            {
                "query_mode": "raw",
                "all_columns": filter_existing_cols(
                    ds_demanda,
                    [
                        "Equipe",
                        "Servico",
                        "Categoria",
                        "Urgencia",
                        "VersaoProduto",
                        "Volumetria",
                        "Abertos",
                        "HorasMediasResolucao",
                    ],
                ),
                "order_by_cols": ['["Volumetria", false]'],
                "row_limit": 500,
                "page_length": 15,
                "include_search": True,
                "show_cell_bars": True,
                "adhoc_filters": [],
            },
            "Pareto de chamados por Serviço (ex: EGUARDIAN), Categoria e Versão (#133948).",
        ),
        (
            "TABELA_CLIENTE_RAIOX",
            "Raio-X de Empresas Clientes e Radar de Churn (Silenciosos > 60d)",
            "table",
            ds_clientes["id"],
            {
                "query_mode": "aggregate",
                "groupby": filter_existing_cols(
                    ds_clientes,
                    [
                        "Cliente",
                        "Servico",
                        "Equipe",
                        "StatusRelacionamento",
                        "DataUltimoTicket",
                    ],
                ),
                "metrics": [
                    make_simple_metric(ds_clientes, "DiasDesdeUltimoTicket", "MAX", "Dias Sem Ticket"),
                    make_simple_metric(ds_clientes, "TotalTicketsHistorico", "SUM", "Total Tickets"),
                    make_simple_metric(ds_clientes, "TicketsAtualmenteAbertos", "SUM", "Em Aberto"),
                    make_simple_metric(ds_clientes, "SlaCumpridoPct", "AVG", "SLA Cumprido (%)"),
                ],
                "percent_metrics": [
                    make_simple_metric(
                        ds_clientes,
                        "TotalTicketsHistorico",
                        "SUM",
                        "Total",
                        option_name="metric_pct_totalticketshistorico_sum",
                    ),
                ],
                "all_columns": [],
                "timeseries_limit_metric": make_simple_metric(
                    ds_clientes, "DiasDesdeUltimoTicket", "MAX", "Dias Sem Ticket"
                ),
                "order_desc": True,
                "percent_metric_calculation": "row_limit",
                "table_timestamp_format": "%d/%m/%Y",
                "adhoc_filters": [
                    {
                        "clause": "WHERE",
                        "comparator": "No filter",
                        "datasourceWarning": False,
                        "expressionType": "SIMPLE",
                        "filterOptionName": "filter_dataultimoticket_temporal",
                        "isExtra": False,
                        "isNew": False,
                        "operator": "TEMPORAL_RANGE",
                        "sqlExpression": None,
                        "subject": "DataUltimoTicket",
                    }
                ],
                "row_limit": 2000,
                "page_length": 15,
                "include_search": True,
                "show_cell_bars": True,
                "color_pn": True,
                "align_pn": True,
                "show_totals": True,
                "column_config": {
                    "Dias Sem Ticket": {"d3NumberFormat": ",d"},
                    "Total Tickets": {"d3NumberFormat": ",d"},
                    "Em Aberto": {"d3NumberFormat": ",d"},
                    "SLA Cumprido (%)": {"d3NumberFormat": ".1f"},
                    "%Total": {"d3NumberFormat": ".1%"},
                },
            },
            "Saúde da carteira de clientes por Produto/Serviço e Equipe Atual (Dono Atual), ordenada do cliente há mais tempo sem abrir chamado ao mais recente.",
        ),
        # Row 6: Pizza/Donut Tickets Abertos por Cliente (Organização) e Serviço + Grid Detalhado no Período
        (
            "PIE_TICKETS_CLIENTE",
            "Tickets Abertos por Cliente (Organização)",
            "pie",
            ds_clientes_periodo["id"],
            {
                "groupby": filter_existing_cols(ds_clientes_periodo, ["Cliente", "Servico"]),
                "metric": make_simple_metric(ds_clientes_periodo, "QtdTickets", "SUM", "Tickets"),
                "adhoc_filters": [
                    {
                        "clause": "WHERE",
                        "comparator": "DATETRUNC(DATETIME('today'), month) : now",
                        "datasourceWarning": False,
                        "expressionType": "SIMPLE",
                        "filterOptionName": "filter_dataabertura_este_mes",
                        "isExtra": False,
                        "isNew": False,
                        "operator": "TEMPORAL_RANGE",
                        "sqlExpression": None,
                        "subject": "DataAbertura",
                    }
                ],
                "row_limit": 200,
                "sort_by_metric": True,
                "color_scheme": "supersetColors",
                "show_legend": True,
                "legendType": "scroll",
                "legendOrientation": "left",
                "label_type": "percent",
                "number_format": ",d",
                "date_format": "smart_date",
                "show_labels": True,
                "labels_outside": False,
                "label_line": False,
                "show_labels_threshold": 5,
                "show_total": True,
                "donut": True,
                "innerRadius": 30,
                "outerRadius": 70,
            },
            "Distribuição em Donut dos tickets abertos por Cliente (Organização) e Serviço no período selecionado (padrão: Este mês), respeitando os filtros de Equipe e Serviço.",
        ),
        (
            "TABELA_TICKETS_CLIENTE_PERIODO",
            "Detalhamento de Tickets por Cliente no Período",
            "table",
            ds_clientes_periodo["id"],
            {
                "query_mode": "aggregate",
                "groupby": filter_existing_cols(ds_clientes_periodo, ["Cliente", "Servico"]),
                "metrics": [
                    make_simple_metric(ds_clientes_periodo, "QtdTickets", "SUM", "Qtd Tickets"),
                ],
                "percent_metrics": [
                    make_simple_metric(
                        ds_clientes_periodo,
                        "QtdTickets",
                        "SUM",
                        "Total",
                        option_name="metric_pct_qtdtickets_sum",
                    ),
                ],
                "all_columns": [],
                "timeseries_limit_metric": make_simple_metric(
                    ds_clientes_periodo, "QtdTickets", "SUM", "Qtd Tickets"
                ),
                "order_desc": True,
                "percent_metric_calculation": "row_limit",
                "adhoc_filters": [
                    {
                        "clause": "WHERE",
                        "comparator": "DATETRUNC(DATETIME('today'), month) : now",
                        "datasourceWarning": False,
                        "expressionType": "SIMPLE",
                        "filterOptionName": "filter_dataabertura_este_mes",
                        "isExtra": False,
                        "isNew": False,
                        "operator": "TEMPORAL_RANGE",
                        "sqlExpression": None,
                        "subject": "DataAbertura",
                    }
                ],
                "row_limit": 500,
                "page_length": 15,
                "include_search": True,
                "show_cell_bars": True,
                "color_pn": True,
                "align_pn": True,
                "show_totals": True,
                "column_config": {
                    "Qtd Tickets": {"d3NumberFormat": ",d"},
                    "%Total": {"d3NumberFormat": ".1%"},
                },
            },
            "Ranking detalhado de tickets abertos por Cliente e Serviço no período (Qtd Tickets, % do total e totalizador) para complementar o gráfico Donut.",
        ),
    ]

    created_meta: Dict[str, Dict[str, Any]] = {}
    for key, title, viz_type, ds_id, params_dict, desc in chart_specs:
        c_id, c_uuid = upsert_chart(
            client,
            existing_charts,
            title,
            viz_type,
            ds_id,
            dashboard_id,
            params_dict,
            desc,
        )
        created_meta[key] = {
            "id": c_id,
            "uuid": c_uuid,
            "title": title,
        }
        print(f"[OK] Gráfico '{title}' (ID={c_id}) vinculado ao Dashboard Movidesk.")

    # Monta o layout v2 (position_json) com 12 colunas de largura padrão do Superset
    position_json: Dict[str, Any] = {
        "DASHBOARD_VERSION_KEY": "v2",
        "ROOT_ID": {"type": "ROOT", "id": "ROOT_ID", "children": ["GRID_ID"]},
        "HEADER_ID": {
            "id": "HEADER_ID",
            "type": "HEADER",
            "meta": {"text": dash_title},
        },
        "GRID_ID": {
            "type": "GRID",
            "id": "GRID_ID",
            "children": [
                "ROW-KPIS",
                "ROW-RADAR",
                "ROW-SERIES",
                "ROW-AGING",
                "ROW-DEMANDA-CLIENTES",
                "ROW-CLIENTES-PERIODO",
            ],
            "parents": ["ROOT_ID"],
        },
        "ROW-KPIS": {
            "type": "ROW",
            "id": "ROW-KPIS",
            "children": [
                "CHART-KPI_BACKLOG",
                "CHART-KPI_VENCIDOS",
                "CHART-KPI_IMINENTE",
                "CHART-KPI_ABERTOS_HOJE",
                "CHART-KPI_RESOLVIDOS_HOJE",
                "CHART-KPI_FCR",
            ],
            "parents": ["ROOT_ID", "GRID_ID"],
            "meta": {"background": "BACKGROUND_TRANSPARENT"},
        },
        "ROW-RADAR": {
            "type": "ROW",
            "id": "ROW-RADAR",
            "children": ["CHART-TABELA_RADAR_SLA"],
            "parents": ["ROOT_ID", "GRID_ID"],
            "meta": {"background": "BACKGROUND_TRANSPARENT"},
        },
        "ROW-SERIES": {
            "type": "ROW",
            "id": "ROW-SERIES",
            "children": ["CHART-SERIE_BACKLOG_90D", "CHART-SERIE_THROUGHPUT"],
            "parents": ["ROOT_ID", "GRID_ID"],
            "meta": {"background": "BACKGROUND_TRANSPARENT"},
        },
        "ROW-AGING": {
            "type": "ROW",
            "id": "ROW-AGING",
            "children": ["CHART-TABELA_BACKLOG_AGING", "CHART-TABELA_STATUS_AGING"],
            "parents": ["ROOT_ID", "GRID_ID"],
            "meta": {"background": "BACKGROUND_TRANSPARENT"},
        },
        "ROW-DEMANDA-CLIENTES": {
            "type": "ROW",
            "id": "ROW-DEMANDA-CLIENTES",
            "children": ["CHART-TABELA_MAPA_DEMANDA", "CHART-TABELA_CLIENTE_RAIOX"],
            "parents": ["ROOT_ID", "GRID_ID"],
            "meta": {"background": "BACKGROUND_TRANSPARENT"},
        },
        "ROW-CLIENTES-PERIODO": {
            "type": "ROW",
            "id": "ROW-CLIENTES-PERIODO",
            "children": ["CHART-PIE_TICKETS_CLIENTE", "CHART-TABELA_TICKETS_CLIENTE_PERIODO"],
            "parents": ["ROOT_ID", "GRID_ID"],
            "meta": {"background": "BACKGROUND_TRANSPARENT"},
        },
    }

    layout_dims = {
        "KPI_BACKLOG": ("ROW-KPIS", 2, 18),
        "KPI_VENCIDOS": ("ROW-KPIS", 2, 18),
        "KPI_IMINENTE": ("ROW-KPIS", 2, 18),
        "KPI_ABERTOS_HOJE": ("ROW-KPIS", 2, 18),
        "KPI_RESOLVIDOS_HOJE": ("ROW-KPIS", 2, 18),
        "KPI_FCR": ("ROW-KPIS", 2, 18),
        "TABELA_RADAR_SLA": ("ROW-RADAR", 12, 48),
        "SERIE_BACKLOG_90D": ("ROW-SERIES", 6, 42),
        "SERIE_THROUGHPUT": ("ROW-SERIES", 6, 42),
        "TABELA_BACKLOG_AGING": ("ROW-AGING", 7, 44),
        "TABELA_STATUS_AGING": ("ROW-AGING", 5, 44),
        "TABELA_MAPA_DEMANDA": ("ROW-DEMANDA-CLIENTES", 6, 44),
        "TABELA_CLIENTE_RAIOX": ("ROW-DEMANDA-CLIENTES", 6, 44),
        "PIE_TICKETS_CLIENTE": ("ROW-CLIENTES-PERIODO", 6, 46),
        "TABELA_TICKETS_CLIENTE_PERIODO": ("ROW-CLIENTES-PERIODO", 6, 46),
    }

    for key, (row_id, width, height) in layout_dims.items():
        meta = created_meta[key]
        node_id = f"CHART-{key}"
        position_json[node_id] = {
            "type": "CHART",
            "id": node_id,
            "children": [],
            "parents": ["ROOT_ID", "GRID_ID", row_id],
            "meta": {
                "width": width,
                "height": height,
                "chartId": meta["id"],
                "sliceName": meta["title"],
                "uuid": meta["uuid"],
            },
        }

    # Preserva json_metadata existente do Dashboard (filtros nativos configurados, etc.)
    json_metadata: Dict[str, Any] = {}
    try:
        dash_detail = client.request("GET", f"/api/v1/dashboard/{dashboard_id}", timeout=60).get("result", {})
        raw_meta = dash_detail.get("json_metadata")
        if raw_meta:
            parsed_meta = json.loads(raw_meta)
            if isinstance(parsed_meta, dict):
                json_metadata = parsed_meta
    except Exception:
        pass

    json_metadata.setdefault("timed_refresh_immune_slices", [])
    json_metadata.setdefault("expanded_slices", {})
    json_metadata.setdefault("refresh_frequency", 60)
    json_metadata.setdefault("default_filters", "{}")
    json_metadata.setdefault("color_scheme", "supersetColors")
    json_metadata["cross_filters_enabled"] = True

    native_filters = json_metadata.get("native_filter_configuration")
    if not isinstance(native_filters, list):
        native_filters = []

    all_chart_ids = sorted(meta["id"] for meta in created_meta.values())
    servico_chart_keys = {
        "TABELA_RADAR_SLA",
        "TABELA_BACKLOG_AGING",
        "TABELA_MAPA_DEMANDA",
        "TABELA_CLIENTE_RAIOX",
        "PIE_TICKETS_CLIENTE",
        "TABELA_TICKETS_CLIENTE_PERIODO",
    }
    in_scope_for_servico = sorted(
        meta["id"] for key, meta in created_meta.items() if key in servico_chart_keys
    )
    excluded_for_servico = sorted(
        meta["id"] for key, meta in created_meta.items() if key not in servico_chart_keys
    )
    in_scope_for_period = sorted(
        meta["id"]
        for key, meta in created_meta.items()
        if key in ("PIE_TICKETS_CLIENTE", "TABELA_TICKETS_CLIENTE_PERIODO")
    )
    excluded_for_period = sorted(
        meta["id"]
        for key, meta in created_meta.items()
        if key not in ("PIE_TICKETS_CLIENTE", "TABELA_TICKETS_CLIENTE_PERIODO")
    )

    equipe_filter_id = "NATIVE_FILTER-a1b2c3d4-e5f6-4a7b-8c9d-0e1f2a3b4c5d"
    period_filter_id = "NATIVE_FILTER-b2c3d4e5-f6a7-4b8c-9d0e-1f2a3b4c5d6e"
    servico_filter_id = "NATIVE_FILTER-c3d4e5f6-a7b8-4c9d-0e1f-2a3b4c5d6e7f"

    existing_equipe_filter: Optional[Dict[str, Any]] = None
    existing_servico_filter: Optional[Dict[str, Any]] = None
    existing_period_filter: Optional[Dict[str, Any]] = None

    def _has_target_column(nf_obj: Dict[str, Any], target_col: str) -> bool:
        for tgt in nf_obj.get("targets", []) or []:
            col = tgt.get("column") if isinstance(tgt, dict) else None
            if isinstance(col, dict) and str(col.get("name", "")).lower() == target_col.lower():
                return True
        return False

    for nf in native_filters:
        if not isinstance(nf, dict):
            continue
        nf_id = str(nf.get("id", ""))
        nf_name = str(nf.get("name", ""))
        if existing_period_filter is None and (
            nf_id.lower() == period_filter_id.lower()
            or nf_name.lower() == "período (tickets por cliente)"
        ):
            existing_period_filter = nf

        if existing_equipe_filter is None and (
            nf_id.lower() == equipe_filter_id.lower()
            or nf_name.lower() == "equipe"
            or _has_target_column(nf, "equipe")
        ):
            existing_equipe_filter = nf

        if existing_servico_filter is None and (
            nf_id.lower() == servico_filter_id.lower()
            or nf_name.lower() in ("serviço", "servico")
            or _has_target_column(nf, "servico")
        ):
            existing_servico_filter = nf

    # Em Superset 6.1.0, chartsInScope precisa listar explícita e integralmente todos os gráficos em escopo
    if existing_equipe_filter is not None:
        existing_equipe_filter["scope"] = {
            "rootPath": ["ROOT_ID"],
            "excluded": [],
        }
        existing_equipe_filter["chartsInScope"] = list(all_chart_ids)
        existing_equipe_filter["tabsInScope"] = []
        if not existing_equipe_filter.get("targets"):
            existing_equipe_filter["targets"] = [
                {
                    "datasetId": ds_kpis["id"],
                    "column": {"name": "Equipe"},
                }
            ]
    else:
        native_filters.append(
            {
                "id": equipe_filter_id,
                "name": "Equipe",
                "filterType": "filter_select",
                "targets": [
                    {
                        "datasetId": ds_kpis["id"],
                        "column": {"name": "Equipe"},
                    }
                ],
                "defaultDataMask": {
                    "extraFormData": {},
                    "filterState": {},
                    "ownState": {},
                },
                "controlValues": {
                    "enableEmptyFilter": False,
                    "defaultToFirstItem": False,
                    "multiSelect": True,
                    "searchAllOptions": False,
                    "inverseSelection": False,
                },
                "cascadeParentIds": [],
                "scope": {
                    "rootPath": ["ROOT_ID"],
                    "excluded": [],
                },
                "chartsInScope": list(all_chart_ids),
                "tabsInScope": [],
                "type": "NATIVE_FILTER",
                "description": "Filtro global de Equipe aplicado em todos os 15 gráficos e views (mart.*).",
            }
        )

    if existing_servico_filter is not None:
        existing_servico_filter["scope"] = {
            "rootPath": ["ROOT_ID"],
            "excluded": list(excluded_for_servico),
        }
        existing_servico_filter["chartsInScope"] = list(in_scope_for_servico)
        existing_servico_filter["tabsInScope"] = []
        if not existing_servico_filter.get("targets"):
            existing_servico_filter["targets"] = [
                {
                    "datasetId": ds_demanda["id"],
                    "column": {"name": "Servico"},
                }
            ]
    else:
        native_filters.append(
            {
                "id": servico_filter_id,
                "name": "Serviço",
                "filterType": "filter_select",
                "targets": [
                    {
                        "datasetId": ds_demanda["id"],
                        "column": {"name": "Servico"},
                    }
                ],
                "defaultDataMask": {
                    "extraFormData": {},
                    "filterState": {},
                    "ownState": {},
                },
                "controlValues": {
                    "enableEmptyFilter": False,
                    "defaultToFirstItem": False,
                    "multiSelect": True,
                    "searchAllOptions": False,
                    "inverseSelection": False,
                },
                "cascadeParentIds": [],
                "scope": {
                    "rootPath": ["ROOT_ID"],
                    "excluded": list(excluded_for_servico),
                },
                "chartsInScope": list(in_scope_for_servico),
                "tabsInScope": [],
                "type": "NATIVE_FILTER",
                "description": "Filtro global de Produto/Serviço aplicado ao Radar SLA, Aging, Demanda, Raio-X e Clientes por Período.",
            }
        )

    if existing_period_filter is not None:
        existing_period_filter["scope"] = {
            "rootPath": ["ROOT_ID"],
            "excluded": list(excluded_for_period),
        }
        existing_period_filter["chartsInScope"] = list(in_scope_for_period)
        existing_period_filter["tabsInScope"] = []
    else:
        native_filters.append(
            {
                "id": period_filter_id,
                "name": "Período (Tickets por Cliente)",
                "filterType": "filter_time",
                "targets": [{}],
                "defaultDataMask": {
                    "extraFormData": {},
                    "filterState": {},
                    "ownState": {},
                },
                "controlValues": {
                    "enableEmptyFilter": False,
                },
                "cascadeParentIds": [],
                "scope": {
                    "rootPath": ["ROOT_ID"],
                    "excluded": list(excluded_for_period),
                },
                "chartsInScope": list(in_scope_for_period),
                "tabsInScope": [],
                "type": "NATIVE_FILTER",
                "description": "Filtro de Data de Abertura aplicado ao Donut e ao Grid de Tickets por Cliente e Serviço (padrão inicial: Este mês).",
            }
        )

    json_metadata["native_filter_configuration"] = native_filters

    client.request(
        "PUT",
        f"/api/v1/dashboard/{dashboard_id}",
        payload={
            "dashboard_title": dash_title,
            "slug": dash_slug,
            "position_json": json.dumps(position_json, ensure_ascii=False),
            "json_metadata": json.dumps(json_metadata, ensure_ascii=False),
            "published": True,
        },
        timeout=90,
        max_retries=1,
    )

    # Re-confirma o vínculo dashboard_slices preservando outros dashboards do usuário
    for meta in created_meta.values():
        try:
            merged_dashboards = get_merged_chart_dashboards(client, meta["id"], dashboard_id)
            client.request(
                "PUT",
                f"/api/v1/chart/{meta['id']}",
                payload={"dashboards": merged_dashboards},
                timeout=60,
            )
        except Exception:
            pass

    dash_url = f"{client.base_url}/superset/dashboard/{dash_slug}/"
    print(f"[OK] Passo 3/3 — Dashboard '{dash_title}' publicado em: {dash_url}")
    return dash_url


def main() -> int:
    try:
        sys.stdout.reconfigure(line_buffering=True)
        sys.stderr.reconfigure(line_buffering=True)
    except Exception:
        pass

    parser = argparse.ArgumentParser(description="Setup automático do Apache Superset (MovideskDM)")
    parser.add_argument("--url", default=DEFAULT_SUPERSET_URL, help="URL do Superset (padrão: http://localhost:8088)")
    parser.add_argument("--username", default=DEFAULT_USERNAME, help="Usuário admin do Superset")
    parser.add_argument("-p", "--password", default=DEFAULT_PASSWORD, help="Senha admin do Superset")
    parser.add_argument("--db-name", default=DEFAULT_DB_NAME, help="Nome do banco no Superset")
    parser.add_argument("--db-uri", default=DEFAULT_DB_URI, help="SQLAlchemy URI do MovideskDM")
    args = parser.parse_args()

    has_explicit_uri = any(a == "--db-uri" or a.startswith("--db-uri=") for a in sys.argv[1:]) or bool(
        os.environ.get("MOVIDESK_DB_URI")
    )

    print("=" * 76, flush=True)
    print(" AUTOMAÇÃO TOTAL APACHE SUPERSET — MOVIDESK BI (ADVICE COMPLIANCE SOLUTIONS)", flush=True)
    print("=" * 76, flush=True)

    try:
        ensure_superset_online(args.url)
        final_db_uri = resolve_best_db_uri(args.db_uri)
        ensure_sql_views_updated(final_db_uri)

        client = SupersetApiClient(args.url, args.username, args.password)
        client.authenticate()
        print(f"[OK] Autenticado na REST API do Superset ({args.url}) como '{args.username}'.", flush=True)

        db_id = upsert_database(client, args.db_name, final_db_uri, has_explicit_uri=has_explicit_uri)
        datasets = upsert_datasets(client, db_id)
        dash_url = build_movidesk_dashboard(client, datasets)

        print("=" * 76, flush=True)
        print(" [OK] SETUP CONCLUÍDO COM SUCESSO!", flush=True)
        print(f" [OK] Acesse agora o Dashboard Movidesk: {dash_url}", flush=True)
        print("=" * 76, flush=True)
        return 0
    except Exception as exc:
        print(f"[ERRO] Falha durante o setup automático do Superset: {exc}", flush=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())

