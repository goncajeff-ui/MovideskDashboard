/* =============================================================================
   08 - Otimização Definitiva mart.vw_ClienteRaioX (Fim do Timeout 60s no Superset)
        + Normalização de Serviço em mart.vw_TicketsPorClientePeriodo
   - Execute diretamente no SQL Server Management Studio (SSMS)
   - Também aplicado automaticamente pelo MovideskControlPanel na inicialização/carga
   ============================================================================= */
USE [MovideskDM];
GO

/* ----------------------------------------------------------------------------
   1. Índices Covering (Eliminam Key Lookups e TempDB Spills no Raio-X e Clientes)
---------------------------------------------------------------------------- */
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'IX_core_Dim_Cliente_RaioX' AND object_id = OBJECT_ID(N'core.Dim_Cliente'))
    CREATE INDEX IX_core_Dim_Cliente_RaioX
        ON core.Dim_Cliente (Ativo, TipoPessoa, EmpresaId)
        INCLUDE (Nome, RazaoSocial);
GO

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'IX_core_Fato_Ticket_Empresa_RaioX' AND object_id = OBJECT_ID(N'core.Fato_Ticket'))
    CREATE INDEX IX_core_Fato_Ticket_Empresa_RaioX
        ON core.Fato_Ticket (EmpresaId, ServicoN1, DataCriacao DESC)
        INCLUDE (Equipe, Status, StatusBase, DataResolucao, SlaDataSolucao);
GO

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'IX_core_Fato_Ticket_DataCriacao_Clientes' AND object_id = OBJECT_ID(N'core.Fato_Ticket'))
    CREATE INDEX IX_core_Fato_Ticket_DataCriacao_Clientes
        ON core.Fato_Ticket (DataCriacao)
        INCLUDE (EmpresaId, Equipe, ServicoN1, Status, StatusBase, AgenteId, Categoria, Urgencia, Protocolo);
GO

/* ----------------------------------------------------------------------------
   2. ALTER VIEW mart.vw_ClienteRaioX
      - Reescrita em single-pass scan (ResumoTickets) sem ROW_NUMBER(), sem
        múltiplos scans em core.Fato_Ticket e sem EXISTS correlacionado no WHERE.
      - Preserva 100% a regra de Dono Atual pelo último ticket por Cliente + Serviço.
---------------------------------------------------------------------------- */
ALTER VIEW mart.vw_ClienteRaioX
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
GO

/* ----------------------------------------------------------------------------
   3. ALTER VIEW mart.vw_TicketsPorClientePeriodo
      - Normaliza t.ServicoN1 (NULL/vazio -> 'Não Informado') e mantém Equipe
---------------------------------------------------------------------------- */
ALTER VIEW mart.vw_TicketsPorClientePeriodo
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
GO
