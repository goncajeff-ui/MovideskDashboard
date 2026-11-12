/* =============================================================================
   03 - Views Analíticas (Camada MART para consumo do Superset)
   ============================================================================= */
USE [MovideskDM];
GO

/* ----------------------------------------------------------------------------
   1. mart.vw_VisaoGeralKpis (Big Numbers para o topo do painel)
---------------------------------------------------------------------------- */
CREATE OR ALTER VIEW mart.vw_VisaoGeralKpis
AS
WITH Base AS (
    SELECT 
        t.TicketId,
        t.Equipe,
        t.AgenteId,
        t.StatusBase,
        t.Status,
        t.Urgencia,
        t.DataCriacao,
        t.DataResolucao,
        t.SlaDataSolucao,
        t.SlaSolucaoPausado,
        t.ResolvidoPrimeiroContato,
        st.GrupoStatus,
        st.EhFinal,
        st.EhDependenciaTerceiro
    FROM core.Fato_Ticket t
    LEFT JOIN core.Dim_Status st ON t.Status = st.Nome
)
SELECT 
    b.Equipe,
    -- Backlog Atual
    COUNT(CASE WHEN b.EhFinal = 0 THEN 1 END) AS BacklogAtual,
    -- SLA Vencido (abertos cujo prazo já expirou)
    COUNT(CASE WHEN b.EhFinal = 0 AND b.SlaDataSolucao < SYSDATETIME() AND ISNULL(b.SlaSolucaoPausado, 0) = 0 THEN 1 END) AS SlaVencidos,
    -- SLA Iminente (< 4 horas para vencer)
    COUNT(CASE WHEN b.EhFinal = 0 AND b.SlaDataSolucao >= SYSDATETIME() AND DATEDIFF(MINUTE, SYSDATETIME(), b.SlaDataSolucao) <= 240 AND ISNULL(b.SlaSolucaoPausado, 0) = 0 THEN 1 END) AS SlaIminente4h,
    -- SLA Pausado (aguardando cliente/versão)
    COUNT(CASE WHEN b.EhFinal = 0 AND b.SlaSolucaoPausado = 1 THEN 1 END) AS SlaPausados,
    -- Dependência de Terceiros / Dev
    COUNT(CASE WHEN b.EhFinal = 0 AND b.EhDependenciaTerceiro = 1 THEN 1 END) AS EmDependenciaDev,
    -- Abertos Hoje
    COUNT(CASE WHEN CAST(b.DataCriacao AS DATE) = CAST(SYSDATETIME() AS DATE) THEN 1 END) AS AbertosHoje,
    -- Resolvidos Hoje
    COUNT(CASE WHEN CAST(b.DataResolucao AS DATE) = CAST(SYSDATETIME() AS DATE) THEN 1 END) AS ResolvidosHoje,
    -- Taxa FCR dos últimos 30 dias (%)
    CAST(ROUND(100.0 * COUNT(CASE WHEN b.DataResolucao >= DATEADD(DAY, -30, SYSDATETIME()) AND b.ResolvidoPrimeiroContato = 1 THEN 1 END) 
        / NULLIF(COUNT(CASE WHEN b.DataResolucao >= DATEADD(DAY, -30, SYSDATETIME()) THEN 1 END), 0), 1) AS DECIMAL(5,1)) AS FcrUltimos30DiasPct
FROM Base b
GROUP BY b.Equipe;
GO

/* ----------------------------------------------------------------------------
   2. mart.vw_SlaRadar (Termômetro preditivo de quebra de SLA da fila ativa)
---------------------------------------------------------------------------- */
CREATE OR ALTER VIEW mart.vw_SlaRadar
AS
SELECT 
    t.TicketId,
    t.Protocolo,
    t.Assunto,
    t.Categoria,
    t.Urgencia,
    t.Status,
    st.GrupoStatus,
    t.Equipe,
    ISNULL(ag.Nome, 'Não Atribuído') AS Analista,
    ISNULL(cli.Nome, 'Não Identificado') AS Cliente,
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
        WHEN DATEDIFF(MINUTE, SYSDATETIME(), t.SlaDataSolucao) <= 240 THEN 'Alerta (< 4h)'
        WHEN DATEDIFF(MINUTE, SYSDATETIME(), t.SlaDataSolucao) <= 480 THEN 'Atenção (< 8h)'
        ELSE 'No Prazo (> 8h)'
    END AS FaixaRiscoSla,
    CASE 
        WHEN t.SlaSolucaoPausado = 1 THEN 5
        WHEN t.SlaDataSolucao IS NULL THEN 6
        WHEN t.SlaDataSolucao < SYSDATETIME() THEN 1
        WHEN DATEDIFF(MINUTE, SYSDATETIME(), t.SlaDataSolucao) <= 120 THEN 2
        WHEN DATEDIFF(MINUTE, SYSDATETIME(), t.SlaDataSolucao) <= 240 THEN 3
        WHEN DATEDIFF(MINUTE, SYSDATETIME(), t.SlaDataSolucao) <= 480 THEN 4
        ELSE 7
    END AS OrdemGravidade,
    DATEDIFF(MINUTE, SYSDATETIME(), t.SlaDataSolucao) AS MinutosParaVencer,
    DATEDIFF(HOUR, t.DataUltimaAcao, SYSDATETIME()) AS HorasSemInteracao
FROM core.Fato_Ticket t
LEFT JOIN core.Dim_Status st ON t.Status = st.Nome
LEFT JOIN core.Dim_Agente ag ON t.AgenteId = ag.AgenteId
LEFT JOIN core.Dim_Cliente cli ON t.EmpresaId = cli.ClienteId
WHERE ISNULL(st.EhFinal, 0) = 0;
GO

/* ----------------------------------------------------------------------------
   3. mart.vw_BacklogAging (Idade dos chamados em aberto)
---------------------------------------------------------------------------- */
CREATE OR ALTER VIEW mart.vw_BacklogAging
AS
SELECT 
    t.TicketId,
    t.Assunto,
    t.Equipe,
    ISNULL(ag.Nome, 'Não Atribuído') AS Analista,
    ISNULL(cli.Nome, 'Não Identificado') AS Cliente,
    t.Categoria,
    t.Urgencia,
    t.Status,
    st.GrupoStatus,
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
    DATEDIFF(HOUR, t.DataUltimaAcao, SYSDATETIME()) AS HorasDesdeUltimaAcao,
    CASE 
        WHEN DATEDIFF(HOUR, t.DataUltimaAcao, SYSDATETIME()) >= 48 THEN 1 
        ELSE 0 
    END AS SemInteracaoMais48h
FROM core.Fato_Ticket t
LEFT JOIN core.Dim_Status st ON t.Status = st.Nome
LEFT JOIN core.Dim_Agente ag ON t.AgenteId = ag.AgenteId
LEFT JOIN core.Dim_Cliente cli ON t.EmpresaId = cli.ClienteId
WHERE ISNULL(st.EhFinal, 0) = 0;
GO

/* ----------------------------------------------------------------------------
   4. mart.vw_StatusAging (Onde os chamados passam a maior parte do tempo)
---------------------------------------------------------------------------- */
CREATE OR ALTER VIEW mart.vw_StatusAging
AS
SELECT 
    t.Equipe,
    sh.Status,
    ISNULL(st.GrupoStatus, 'Outros') AS GrupoStatus,
    ISNULL(st.EhDependenciaTerceiro, 0) AS EhDependenciaTerceiro,
    COUNT(1) AS QtdPassagens,
    CAST(ROUND(AVG(sh.PermanenciaMinUteis / 60.0), 1) AS DECIMAL(10,1)) AS HorasUteisMedias,
    CAST(ROUND(AVG(sh.PermanenciaMinCorridos / 60.0), 1) AS DECIMAL(10,1)) AS HorasCorridasMedias,
    CAST(ROUND(SUM(sh.PermanenciaMinCorridos / 60.0), 0) AS BIGINT) AS HorasCorridasTotais
FROM core.Fato_StatusHistorico sh
INNER JOIN core.Fato_Ticket t ON sh.TicketId = t.TicketId
LEFT JOIN core.Dim_Status st ON sh.Status = st.Nome
WHERE sh.PermanenciaMinCorridos IS NOT NULL
GROUP BY t.Equipe, sh.Status, st.GrupoStatus, st.EhDependenciaTerceiro;
GO

/* ----------------------------------------------------------------------------
   5. mart.vw_ThroughputDiario (Abertos vs Resolvidos por dia)
---------------------------------------------------------------------------- */
CREATE OR ALTER VIEW mart.vw_ThroughputDiario
AS
WITH Datas AS (
    SELECT Data, AnoMes, EhDiaUtil
    FROM core.Dim_Calendario
    WHERE Data BETWEEN DATEADD(DAY, -90, CAST(SYSDATETIME() AS DATE)) AND CAST(SYSDATETIME() AS DATE)
),
Abertos AS (
    SELECT 
        CAST(DataCriacao AS DATE) AS Data,
        Equipe,
        COUNT(1) AS QtdAbertos
    FROM core.Fato_Ticket
    GROUP BY CAST(DataCriacao AS DATE), Equipe
),
Resolvidos AS (
    SELECT 
        CAST(DataResolucao AS DATE) AS Data,
        Equipe,
        COUNT(1) AS QtdResolvidos
    FROM core.Fato_Ticket
    WHERE DataResolucao IS NOT NULL
    GROUP BY CAST(DataResolucao AS DATE), Equipe
)
SELECT 
    d.Data,
    d.AnoMes,
    d.EhDiaUtil,
    eq.Nome AS Equipe,
    ISNULL(a.QtdAbertos, 0) AS Abertos,
    ISNULL(r.QtdResolvidos, 0) AS Resolvidos,
    ISNULL(r.QtdResolvidos, 0) - ISNULL(a.QtdAbertos, 0) AS SaldoLiquido
FROM Datas d
CROSS JOIN core.Dim_Equipe eq
LEFT JOIN Abertos a ON d.Data = a.Data AND eq.Nome = a.Equipe
LEFT JOIN Resolvidos r ON d.Data = r.Data AND eq.Nome = r.Equipe;
GO

/* ----------------------------------------------------------------------------
   6. mart.vw_ClienteRaioX (Inteligência e Saúde de Clientes)
---------------------------------------------------------------------------- */
CREATE OR ALTER VIEW mart.vw_ClienteRaioX
AS
SELECT 
    c.ClienteId,
    c.Nome AS Cliente,
    c.RazaoSocial,
    COUNT(t.TicketId) AS TotalTicketsHistorico,
    COUNT(CASE WHEN st.EhFinal = 0 THEN 1 END) AS TicketsAtualmenteAbertos,
    COUNT(CASE WHEN t.DataResolucao IS NOT NULL AND t.DataResolucao <= t.SlaDataSolucao THEN 1 END) AS TicketsDentroSla,
    CAST(ROUND(100.0 * COUNT(CASE WHEN t.DataResolucao IS NOT NULL AND t.DataResolucao <= t.SlaDataSolucao THEN 1 END) 
        / NULLIF(COUNT(CASE WHEN t.DataResolucao IS NOT NULL AND t.SlaDataSolucao IS NOT NULL THEN 1 END), 0), 1) AS DECIMAL(5,1)) AS SlaCumpridoPct,
    MAX(t.DataCriacao) AS DataUltimoTicket,
    DATEDIFF(DAY, MAX(t.DataCriacao), SYSDATETIME()) AS DiasDesdeUltimoTicket,
    CASE 
        WHEN DATEDIFF(DAY, MAX(t.DataCriacao), SYSDATETIME()) >= 60 THEN 'Risco Churn (Silencioso > 60d)'
        WHEN DATEDIFF(DAY, MAX(t.DataCriacao), SYSDATETIME()) >= 30 THEN 'Atenção (Silencioso 30-60d)'
        ELSE 'Ativo (< 30d)'
    END AS StatusRelacionamento
FROM core.Dim_Cliente c
LEFT JOIN core.Fato_Ticket t ON c.ClienteId = t.EmpresaId
LEFT JOIN core.Dim_Status st ON t.Status = st.Nome
GROUP BY c.ClienteId, c.Nome, c.RazaoSocial;
GO

/* ----------------------------------------------------------------------------
   7. mart.vw_MapaDemanda (Pareto de Categorias e Versões de Release)
---------------------------------------------------------------------------- */
CREATE OR ALTER VIEW mart.vw_MapaDemanda
AS
SELECT 
    t.Equipe,
    t.Categoria,
    t.Urgencia,
    ISNULL(cf.Valor, 'Não Informada') AS VersaoProduto,
    COUNT(1) AS Volumetria,
    COUNT(CASE WHEN st.EhFinal = 0 THEN 1 END) AS Abertos,
    CAST(ROUND(AVG(DATEDIFF(HOUR, t.DataCriacao, ISNULL(t.DataResolucao, SYSDATETIME()))), 1) AS DECIMAL(10,1)) AS HorasMediasResolucao
FROM core.Fato_Ticket t
LEFT JOIN core.Dim_Status st ON t.Status = st.Nome
LEFT JOIN core.Fato_CampoCustomizado cf ON t.TicketId = cf.TicketId AND cf.CampoId = 133948 -- Versão Release
GROUP BY t.Equipe, t.Categoria, t.Urgencia, cf.Valor;
GO
