#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
===============================================================================
 Automação Oficial Apache Superset — Movidesk BI (Advice Compliance Solutions)
===============================================================================
Executa silenciosamente via REST API do Apache Superset (http://localhost:8088):
  1. Cria/atualiza a conexão de banco de dados MSSQL `MovideskDM`
     (mssql+pymssql://sa:123456@172.29.112.1:1433/MovideskDM).
  2. Registra e sincroniza os 8 Datasets oficiais do schema `mart`:
     - vw_VisaoGeralKpis
     - vw_SlaRadar
     - vw_BacklogAging
     - vw_StatusAging
     - vw_BacklogEvolucao
     - vw_ThroughputDiario
     - vw_ClienteRaioX
     - vw_MapaDemanda
  3. Constrói os gráficos essenciais e publica o Dashboard "Sala de Guerra - Movidesk BI"
     (/superset/dashboard/sala-de-guerra-movidesk/) com auto-refresh de 60s.

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
    ("vw_ClienteRaioX", "DataUltimoTicket", "Saúde de Empresas Clientes, % SLA e Risco de Churn (> 60d)"),
    ("vw_MapaDemanda", None, "Pareto de Serviços, Categorias, Urgências e Versões de Release (#133948)"),
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
        timeout: int = 30,
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
    Se pymssql estiver disponível (padrão na venv ~/superset-env), garante que as views
    mart.vw_SlaRadar, mart.vw_BacklogAging e mart.vw_MapaDemanda já contenham a coluna Servico.
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
        cur.execute(
            """
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
    ISNULL(t.Equipe, N'Sem Equipe') AS Equipe,
    ISNULL(ag.Nome, N'Não Atribuído') AS Analista,
    ISNULL(emp.Nome, ISNULL(cli.Nome, N'Não Identificado')) AS Cliente,
    t.DataCriacao,
    t.DataUltimaAcao,
    t.SlaAcordo,
    t.SlaDataSolucao,
    t.SlaSolucaoPausado,
    CASE 
        WHEN t.SlaSolucaoPausado = 1 THEN 'SLA Pausado'
        WHEN t.SlaDataSolucao IS NULL THEN 'Sem SLA Definido'
        WHEN t.SlaDataSolucao < SYSDATETIME() THEN 'Vencido'
        WHEN DATEDIFF(MINUTE, SYSDATETIME(), t.SlaDataSolucao) <= 120 THEN 'Crítico (< 2h)'
        WHEN DATEDIFF(MINUTE, SYSDATETIME(), t.SlaDataSolucao) <= p.MinutosAlerta THEN 'Alerta (< 4h)'
        WHEN DATEDIFF(MINUTE, SYSDATETIME(), t.SlaDataSolucao) <= 480 THEN 'Atenção (< 8h)'
        ELSE 'No Prazo (> 8h)'
    END AS FaixaRiscoSla,
    CASE 
        WHEN t.SlaSolucaoPausado = 1 THEN 5
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
WHERE ISNULL(st.EhFinal, CASE WHEN t.StatusBase IN ('Resolved', 'Closed', 'Canceled') THEN 1 ELSE 0 END) = 0;
"""
        )
        cur.execute(
            """
CREATE OR ALTER VIEW mart.vw_BacklogAging
AS
WITH Parametros AS (
    SELECT ISNULL(TRY_CAST((SELECT Valor FROM ctl.Parametro WHERE Chave = 'HORAS_SEM_INTERACAO_ALERTA') AS INT), 48) AS HorasLimiteSemInteracao
)
SELECT 
    t.TicketId,
    t.Assunto,
    ISNULL(t.Equipe, N'Sem Equipe') AS Equipe,
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
WHERE ISNULL(st.EhFinal, CASE WHEN t.StatusBase IN ('Resolved', 'Closed', 'Canceled') THEN 1 ELSE 0 END) = 0;
"""
        )
        cur.execute(
            """
CREATE OR ALTER VIEW mart.vw_MapaDemanda
AS
SELECT 
    ISNULL(t.Equipe, N'Sem Equipe') AS Equipe,
    ISNULL(t.ServicoN1, N'Não Informado') AS Servico,
    t.Categoria,
    t.Urgencia,
    ISNULL(cf.Valor, N'Não Informada') AS VersaoProduto,
    COUNT(1) AS Volumetria,
    COUNT(CASE WHEN ISNULL(st.EhFinal, CASE WHEN t.StatusBase IN ('Resolved', 'Closed', 'Canceled') THEN 1 ELSE 0 END) = 0 THEN 1 END) AS Abertos,
    CAST(ROUND(AVG(DATEDIFF(HOUR, t.DataCriacao, ISNULL(t.DataResolucao, SYSDATETIME()))), 1) AS DECIMAL(10,1)) AS HorasMediasResolucao
FROM core.Fato_Ticket t
LEFT JOIN core.Dim_Status st ON t.Status = st.Nome
LEFT JOIN core.Fato_CampoCustomizado cf ON t.TicketId = cf.TicketId AND cf.CampoId = 133948
GROUP BY ISNULL(t.Equipe, N'Sem Equipe'), ISNULL(t.ServicoN1, N'Não Informado'), t.Categoria, t.Urgencia, ISNULL(cf.Valor, N'Não Informada');
"""
        )
        cur.execute(
            """
CREATE OR ALTER VIEW mart.vw_ClienteRaioX
AS
WITH Parametros AS (
    SELECT
        ISNULL(TRY_CAST((SELECT Valor FROM ctl.Parametro WHERE Chave = 'DIAS_CLIENTE_SILENCIOSO') AS INT), 60) AS DiasSilenciosoCritico
)
SELECT 
    c.ClienteId,
    c.Nome AS Cliente,
    c.RazaoSocial,
    ISNULL(t.Equipe, N'Sem Equipe') AS Equipe,
    COUNT(t.TicketId) AS TotalTicketsHistorico,
    COUNT(CASE WHEN t.TicketId IS NOT NULL AND ISNULL(st.EhFinal, CASE WHEN t.StatusBase IN ('Resolved', 'Closed', 'Canceled') THEN 1 ELSE 0 END) = 0 THEN 1 END) AS TicketsAtualmenteAbertos,
    COUNT(CASE WHEN t.DataResolucao IS NOT NULL AND t.DataResolucao <= t.SlaDataSolucao THEN 1 END) AS TicketsDentroSla,
    CAST(ROUND(100.0 * COUNT(CASE WHEN t.DataResolucao IS NOT NULL AND t.DataResolucao <= t.SlaDataSolucao THEN 1 END) 
        / NULLIF(COUNT(CASE WHEN t.DataResolucao IS NOT NULL AND t.SlaDataSolucao IS NOT NULL THEN 1 END), 0), 1) AS DECIMAL(5,1)) AS SlaCumpridoPct,
    MAX(t.DataCriacao) AS DataUltimoTicket,
    DATEDIFF(DAY, MAX(t.DataCriacao), SYSDATETIME()) AS DiasDesdeUltimoTicket,
    CASE 
        WHEN MAX(t.DataCriacao) IS NULL OR DATEDIFF(DAY, MAX(t.DataCriacao), SYSDATETIME()) >= p.DiasSilenciosoCritico THEN 'Risco Churn (Silencioso > 60d)'
        WHEN DATEDIFF(DAY, MAX(t.DataCriacao), SYSDATETIME()) >= (p.DiasSilenciosoCritico / 2) THEN 'Atenção (Silencioso 30-60d)'
        ELSE 'Ativo (< 30d)'
    END AS StatusRelacionamento
FROM core.Dim_Cliente c
LEFT JOIN core.Fato_Ticket t ON c.ClienteId = t.EmpresaId
LEFT JOIN core.Dim_Status st ON t.Status = st.Nome
CROSS JOIN Parametros p
WHERE ISNULL(c.TipoPessoa, 2) IN (2, 4)
   OR (c.EmpresaId IS NULL AND EXISTS (SELECT 1 FROM core.Fato_Ticket tk WHERE tk.EmpresaId = c.ClienteId))
GROUP BY
    c.ClienteId,
    c.Nome,
    c.RazaoSocial,
    ISNULL(t.Equipe, N'Sem Equipe'),
    p.DiasSilenciosoCritico;
"""
        )
        conn.close()
        print("[OK] Views do schema 'mart' sincronizadas no SQL Server (Servico + vw_ClienteRaioX por Equipe).", flush=True)
    except Exception:
        pass


def upsert_database(client: SupersetApiClient, db_name: str, db_uri: str) -> int:
    """Passo 1: Cria ou atualiza a Database Connection MovideskDM."""
    resp = client.request("GET", "/api/v1/database/", query_params={"q": "(page_size:100)"})
    existing_id: Optional[int] = None
    for row in resp.get("result", []):
        if row.get("database_name") == db_name:
            existing_id = int(row["id"])
            break

    payload = {
        "database_name": db_name,
        "sqlalchemy_uri": db_uri,
        "expose_in_sqllab": True,
        "allow_ctas": False,
        "allow_cvas": False,
        "allow_dml": False,
        "allow_run_async": False,
    }

    if existing_id is not None:
        client.request("PUT", f"/api/v1/database/{existing_id}", payload=payload)
        print(f"[OK] Passo 1/3 — Database '{db_name}' (ID={existing_id}) atualizada com sucesso.", flush=True)
        return existing_id

    create_resp = client.request("POST", "/api/v1/database/", payload=payload)
    db_id = int(create_resp["id"])
    print(f"[OK] Passo 1/3 — Database '{db_name}' (ID={db_id}) criada com sucesso.", flush=True)
    return db_id


def upsert_datasets(
    client: SupersetApiClient, db_id: int
) -> Dict[str, Dict[str, Any]]:
    """Passo 2: Registra e sincroniza as 8 Views do schema mart como Datasets."""
    resp = client.request("GET", "/api/v1/dataset/", query_params={"q": "(page_size:200)"})
    existing_map: Dict[str, int] = {}
    for row in resp.get("result", []):
        t_name = row.get("table_name")
        schema = row.get("schema")
        if t_name and schema == "mart":
            existing_map[t_name] = int(row["id"])

    datasets_info: Dict[str, Dict[str, Any]] = {}

    for view_name, main_dttm_col, description in MART_VIEWS:
        if view_name in existing_map:
            ds_id = existing_map[view_name]
            try:
                client.request("PUT", f"/api/v1/dataset/{ds_id}/refresh")
            except Exception:
                pass
        else:
            create_resp = client.request(
                "POST",
                "/api/v1/dataset/",
                payload={
                    "database": db_id,
                    "schema": "mart",
                    "table_name": view_name,
                },
            )
            ds_id = int(create_resp["id"])

        detail = client.request("GET", f"/api/v1/dataset/{ds_id}").get("result", {})

        if main_dttm_col:
            try:
                update_payload: Dict[str, Any] = {
                    "main_dttm_col": main_dttm_col,
                    "description": description,
                }
                raw_cols = detail.get("columns", [])
                needs_dttm_flag = any(
                    c.get("column_name", "").lower() == main_dttm_col.lower() and not c.get("is_dttm")
                    for c in raw_cols
                )
                if needs_dttm_flag and raw_cols:
                    updated_cols = []
                    for c in raw_cols:
                        col_item: Dict[str, Any] = {
                            "id": c["id"],
                            "column_name": c["column_name"],
                            "type": c.get("type") or "STRING",
                            "is_dttm": bool(c.get("is_dttm"))
                            or (c.get("column_name", "").lower() == main_dttm_col.lower()),
                            "groupby": bool(c.get("groupby", True)),
                            "filterable": bool(c.get("filterable", True)),
                        }
                        updated_cols.append(col_item)
                    update_payload["columns"] = updated_cols

                client.request("PUT", f"/api/v1/dataset/{ds_id}", payload=update_payload)
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
    ds_info: Dict[str, Any], col_name: str, aggregate: str, label: str
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
        "optionName": f"metric_{actual_col.lower()}_{aggregate.lower()}",
    }


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

    payload = {
        "slice_name": slice_name,
        "viz_type": viz_type,
        "datasource_id": ds_id,
        "datasource_type": "table",
        "dashboards": [dashboard_id],
        "description": description,
        "params": json.dumps(params_copy, ensure_ascii=False),
    }

    if slice_name in existing_charts:
        chart_id = existing_charts[slice_name]
        client.request("PUT", f"/api/v1/chart/{chart_id}", payload=payload)
    else:
        create_resp = client.request("POST", "/api/v1/chart/", payload=payload)
        chart_id = int(create_resp["id"])

    chart_detail = client.request("GET", f"/api/v1/chart/{chart_id}").get("result", {})
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


def build_sala_de_guerra_dashboard(
    client: SupersetApiClient,
    datasets: Dict[str, Dict[str, Any]],
) -> str:
    """Passo 3: Cria os gráficos essenciais e monta o Dashboard 'Sala de Guerra - Movidesk BI'."""
    dash_title = "Sala de Guerra - Movidesk BI"
    dash_slug = "sala-de-guerra-movidesk"

    resp = client.request("GET", "/api/v1/dashboard/", query_params={"q": "(page_size:100)"})
    dashboard_id: Optional[int] = None
    for row in resp.get("result", []):
        if row.get("slug") == dash_slug or row.get("dashboard_title") == dash_title:
            dashboard_id = int(row["id"])
            break

    if dashboard_id is None:
        create_dash = client.request(
            "POST",
            "/api/v1/dashboard/",
            payload={
                "dashboard_title": dash_title,
                "slug": dash_slug,
                "published": True,
            },
        )
        dashboard_id = int(create_dash["id"])

    # Busca gráficos existentes para idempotência
    charts_resp = client.request("GET", "/api/v1/chart/", query_params={"q": "(page_size:200)"})
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
                "query_mode": "raw",
                "all_columns": filter_existing_cols(
                    ds_clientes,
                    [
                        "Cliente",
                        "Equipe",
                        "StatusRelacionamento",
                        "TicketsAtualmenteAbertos",
                        "TotalTicketsHistorico",
                        "SlaCumpridoPct",
                        "DiasDesdeUltimoTicket",
                        "DataUltimoTicket",
                    ],
                ),
                "order_by_cols": ['["TotalTicketsHistorico", false]'],
                "row_limit": 500,
                "page_length": 15,
                "include_search": True,
                "show_cell_bars": True,
                "adhoc_filters": [],
            },
            "Saúde da carteira de clientes por equipe, % SLA cumprido e alerta de clientes silenciosos.",
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
        print(f"[OK] Gráfico '{title}' (ID={c_id}) vinculado à Sala de Guerra.")

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

    json_metadata = {
        "timed_refresh_immune_slices": [],
        "expanded_slices": {},
        "refresh_frequency": 60,
        "default_filters": "{}",
        "color_scheme": "supersetColors",
        "cross_filters_enabled": True,
    }

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
    )

    # Re-confirma o vínculo dashboard_slices após atualização do position_json
    for meta in created_meta.values():
        try:
            client.request(
                "PUT",
                f"/api/v1/chart/{meta['id']}",
                payload={"dashboards": [dashboard_id]},
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

        db_id = upsert_database(client, args.db_name, final_db_uri)
        datasets = upsert_datasets(client, db_id)
        dash_url = build_sala_de_guerra_dashboard(client, datasets)

        print("=" * 76, flush=True)
        print(" [OK] SETUP CONCLUÍDO COM SUCESSO!", flush=True)
        print(f" [OK] Acesse agora a Sala de Guerra: {dash_url}", flush=True)
        print("=" * 76, flush=True)
        return 0
    except Exception as exc:
        print(f"[ERRO] Falha durante o setup automático do Superset: {exc}", flush=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())

