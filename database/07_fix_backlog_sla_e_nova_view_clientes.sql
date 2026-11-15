/* =============================================================================
   07 - Correção Definitiva Backlog Atual / SLA Vencidos + Nova View de Clientes por Período
   - Execute diretamente no SQL Server Management Studio (SSMS)
   - Corrige:
     1) core.Dim_Status: garante EhFinal = 1 e PausaSla = 1 para Resolvido, Fechado e Cancelado
     2) Precedência de t.StatusBase IN ('Resolved', 'Closed', 'Canceled') em todas as Views
        e na Procedure de Snapshot (eliminando tickets resolvidos do Backlog Atual e SLA Vencidos)
     3) Considera st.PausaSla = 1 além de SlaSolucaoPausado = 1 (evita que tickets parados
        aguardando cliente sejam contados como SLA Vencido)
     4) Cria a 9ª view mart.vw_TicketsPorClientePeriodo (com coluna Equipe e DataAbertura)
        para o gráfico de Pizza/Donut "Tickets Abertos por Cliente no Período" + Grid detalhado
   ============================================================================= */
USE [MovideskDM];
GO

/* ----------------------------------------------------------------------------
   1. Atualiza core.Dim_Status (Resolvido/Fechado/Cancelado como EhFinal = 1)
---------------------------------------------------------------------------- */
UPDATE core.Dim_Status
SET EhFinal = 1,
    PausaSla = 1
WHERE Nome IN (N'Resolvido', N'Fechado', N'Cancelado')
   OR GrupoStatus = N'Encerrado';
GO

/* ----------------------------------------------------------------------------
   2. Atualiza Procedure core.usp_AtualizarSnapshotBacklog
---------------------------------------------------------------------------- */
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
GO

/* ----------------------------------------------------------------------------
   3. ALTER VIEW mart.vw_VisaoGeralKpis
---------------------------------------------------------------------------- */
ALTER VIEW mart.vw_VisaoGeralKpis
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
GO

/* ----------------------------------------------------------------------------
   4. ALTER VIEW mart.vw_SlaRadar
---------------------------------------------------------------------------- */
ALTER VIEW mart.vw_SlaRadar
AS
WITH Parametros AS (
    SELECT
        ISNULL(TRY_CAST((SELECT Valor FROM ctl.Parametro WHERE Chave = 'HORAS_RADAR_SLA_IMINENTE') AS INT), 4) * 60 AS MinutosAlerta
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
GO

/* ----------------------------------------------------------------------------
   5. ALTER VIEW mart.vw_BacklogAging
---------------------------------------------------------------------------- */
ALTER VIEW mart.vw_BacklogAging
AS
WITH Parametros AS (
    SELECT
        ISNULL(TRY_CAST((SELECT Valor FROM ctl.Parametro WHERE Chave = 'HORAS_SEM_INTERACAO_ALERTA') AS INT), 48) AS HorasLimiteSemInteracao
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
GO

/* ----------------------------------------------------------------------------
   6. ALTER VIEW mart.vw_StatusAging
---------------------------------------------------------------------------- */
ALTER VIEW mart.vw_StatusAging
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
GO

/* ----------------------------------------------------------------------------
   7. ALTER VIEW mart.vw_ClienteRaioX
---------------------------------------------------------------------------- */
-- Ajustado por Jefferson Gonçalves em 15/11/2026 e otimizado para single-pass scan (ResumoTickets) sem ROW_NUMBER / Nested Loops
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
   8. ALTER VIEW mart.vw_MapaDemanda
---------------------------------------------------------------------------- */
ALTER VIEW mart.vw_MapaDemanda
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
LEFT JOIN core.Fato_CampoCustomizado cf ON t.TicketId = cf.TicketId AND cf.CampoId = 133948 -- Versão Release
GROUP BY
    ISNULL(NULLIF(LTRIM(RTRIM(t.Equipe)), N''), N'Sem Equipe'),
    ISNULL(t.ServicoN1, N'Não Informado'),
    t.Categoria,
    t.Urgencia,
    ISNULL(cf.Valor, N'Não Informada');
GO

/* ----------------------------------------------------------------------------
   9. CREATE OR ALTER VIEW mart.vw_TicketsPorClientePeriodo (9ª View)
      Alimenta o Gráfico Donut "Tickets Abertos por Cliente (Organização)" e o Grid
---------------------------------------------------------------------------- */
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
GO

/* ----------------------------------------------------------------------------
   10. Reconstrói Snapshot Diário dos últimos 90 dias + Hoje já sem Resolvidos
---------------------------------------------------------------------------- */
EXEC core.usp_AtualizarSnapshotBacklog @DiasRetroativos = 90, @ReconstruirHistorico = 1;
GO

/* ----------------------------------------------------------------------------
   [OPCIONAL - DIAGNÓSTICO SSMS]
   Descomente e execute o bloco abaixo caso queira auditar status por status
   os chamados abertos da equipe "Sustentação Eguardian RJ":

   SELECT
       t.StatusBase,
       t.Status,
       st.PausaSla,
       t.SlaSolucaoPausado,
       COUNT(*) AS QtdTickets,
       COUNT(CASE WHEN t.SlaDataSolucao < SYSDATETIME()
                   AND ISNULL(t.SlaSolucaoPausado, 0) = 0
                   AND ISNULL(st.PausaSla, 0) = 0 THEN 1 END) AS SlaVencidosContados
   FROM core.Fato_Ticket t
   LEFT JOIN core.Dim_Status st ON t.Status = st.Nome
   WHERE t.Equipe = N'Sustentação Eguardian RJ'
     AND CASE WHEN t.StatusBase IN ('Resolved', 'Closed', 'Canceled') THEN 1 ELSE ISNULL(st.EhFinal, 0) END = 0
   GROUP BY t.StatusBase, t.Status, st.PausaSla, t.SlaSolucaoPausado
   ORDER BY QtdTickets DESC;
---------------------------------------------------------------------------- */
