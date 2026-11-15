/* =============================================================================
   03 - Views Analíticas (Camada MART para consumo do Superset)
   - Todas as datas em core.* já estão normalizadas para Horário de Brasília (BRT)
   - Padroniza fallback de EhFinal via StatusBase caso surja status novo
   - Lê parâmetros dinâmicos de ctl.Parametro (48h, 4h, 60d)
   - Inclui mart.vw_BacklogEvolucao sobre core.Fato_SnapshotBacklog
   ============================================================================= */
USE [MovideskDM];
GO

/* ----------------------------------------------------------------------------
   1. mart.vw_VisaoGeralKpis (Big Numbers para o topo do painel)
---------------------------------------------------------------------------- */
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
    -- Backlog Atual (desconsidera Resolvido/Fechado/Cancelado)
    COUNT(CASE WHEN b.EhFinal = 0 THEN 1 END) AS BacklogAtual,
    -- SLA Vencido (abertos cujo prazo já expirou e cujo SLA não está pausado)
    COUNT(CASE WHEN b.EhFinal = 0 AND b.SlaDataSolucao < SYSDATETIME() AND b.SlaPausadoEfetivo = 0 THEN 1 END) AS SlaVencidos,
    -- SLA Iminente (parametrizado via ctl.Parametro: padrão <= 4 horas / 240 min)
    COUNT(CASE WHEN b.EhFinal = 0 AND b.SlaDataSolucao >= SYSDATETIME() AND DATEDIFF(MINUTE, SYSDATETIME(), b.SlaDataSolucao) <= b.MinutosSlaIminente AND b.SlaPausadoEfetivo = 0 THEN 1 END) AS SlaIminente4h,
    -- SLA Pausado (aguardando cliente/status pausado)
    COUNT(CASE WHEN b.EhFinal = 0 AND b.SlaPausadoEfetivo = 1 THEN 1 END) AS SlaPausados,
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
   3. mart.vw_BacklogAging (Idade dos chamados em aberto)
---------------------------------------------------------------------------- */
CREATE OR ALTER VIEW mart.vw_BacklogAging
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
   4. mart.vw_StatusAging (Onde os chamados passam a maior parte do tempo)
      Inclui tanto as passagens encerradas quanto o tempo em curso do status aberto atual
---------------------------------------------------------------------------- */
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
GO

/* ----------------------------------------------------------------------------
   5. mart.vw_ThroughputDiario (Abertos vs Resolvidos por dia)
---------------------------------------------------------------------------- */
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
GO

/* ----------------------------------------------------------------------------
   6. mart.vw_ClienteRaioX (Inteligência e Saúde de Clientes por Produto e Dono Atual)
---------------------------------------------------------------------------- */
-- Ajustado por Jefferson Gonçalves em 15/11/2026 para redefinir a posse do cliente com base no último ticket por produto
CREATE OR ALTER VIEW mart.vw_ClienteRaioX
AS
WITH Parametros AS (
    SELECT ISNULL(TRY_CAST((SELECT Valor FROM ctl.Parametro WHERE Chave = 'DIAS_CLIENTE_SILENCIOSO') AS INT), 60) AS DiasSilenciosoCritico
),
TicketsBase AS (
    SELECT
        t.TicketId,
        t.EmpresaId,
        ISNULL(t.ServicoN1, N'Não Informado') AS Servico,
        ISNULL(NULLIF(LTRIM(RTRIM(t.Equipe)), N''), N'Sem Equipe') AS Equipe,
        t.DataCriacao,
        t.DataResolucao,
        t.SlaDataSolucao,
        ISNULL(st.EhFinal, CASE WHEN t.StatusBase IN ('Resolved', 'Closed', 'Canceled') THEN 1 ELSE 0 END) AS EhFinal
    FROM core.Fato_Ticket t
    LEFT JOIN core.Dim_Status st ON t.Status = st.Nome
),
-- Identifica o último chamado para cada combinação de Cliente + Serviço
UltimoTicket AS (
    SELECT
        EmpresaId,
        Servico,
        Equipe AS EquipeAtual,
        DataCriacao AS DataUltimoTicket,
        ROW_NUMBER() OVER(PARTITION BY EmpresaId, Servico ORDER BY DataCriacao DESC) AS rn
    FROM TicketsBase
),
-- Isola apenas a linha mais recente (rn = 1) que ditará quem é o Dono Atual
DonoAtual AS (
    SELECT EmpresaId, Servico, EquipeAtual, DataUltimoTicket
    FROM UltimoTicket
    WHERE rn = 1
),
-- Agrega os históricos de saúde separadamente mantendo a granularidade
Agregacao AS (
    SELECT
        EmpresaId,
        Servico,
        COUNT(TicketId) AS TotalTicketsHistorico,
        COUNT(CASE WHEN EhFinal = 0 THEN 1 END) AS TicketsAtualmenteAbertos,
        COUNT(CASE WHEN DataResolucao IS NOT NULL AND DataResolucao <= SlaDataSolucao THEN 1 END) AS TicketsDentroSla,
        COUNT(CASE WHEN DataResolucao IS NOT NULL AND SlaDataSolucao IS NOT NULL THEN 1 END) AS TotalSlaValido
    FROM TicketsBase
    GROUP BY EmpresaId, Servico
)
SELECT
    c.ClienteId,
    c.Nome AS Cliente,
    c.RazaoSocial,
    ISNULL(d.Servico, N'Sem Serviço') AS Servico,
    ISNULL(d.EquipeAtual, N'Sem Equipe') AS Equipe,
    ISNULL(a.TotalTicketsHistorico, 0) AS TotalTicketsHistorico,
    ISNULL(a.TicketsAtualmenteAbertos, 0) AS TicketsAtualmenteAbertos,
    ISNULL(a.TicketsDentroSla, 0) AS TicketsDentroSla,
    CAST(ROUND(100.0 * a.TicketsDentroSla / NULLIF(a.TotalSlaValido, 0), 1) AS DECIMAL(5,1)) AS SlaCumpridoPct,
    d.DataUltimoTicket,
    DATEDIFF(DAY, d.DataUltimoTicket, SYSDATETIME()) AS DiasDesdeUltimoTicket,
    CASE
        WHEN d.DataUltimoTicket IS NULL OR DATEDIFF(DAY, d.DataUltimoTicket, SYSDATETIME()) >= p.DiasSilenciosoCritico THEN 'Risco Churn (Silencioso > 60d)'
        WHEN DATEDIFF(DAY, d.DataUltimoTicket, SYSDATETIME()) >= (p.DiasSilenciosoCritico / 2) THEN 'Atenção (Silencioso 30-60d)'
        ELSE 'Ativo (< 30d)'
    END AS StatusRelacionamento
FROM core.Dim_Cliente c
LEFT JOIN DonoAtual d ON c.ClienteId = d.EmpresaId
LEFT JOIN Agregacao a ON c.ClienteId = a.EmpresaId AND d.Servico = a.Servico
CROSS JOIN Parametros p
WHERE
    (ISNULL(c.TipoPessoa, 2) IN (2, 4) OR (c.EmpresaId IS NULL AND EXISTS (SELECT 1 FROM core.Fato_Ticket tk WHERE tk.EmpresaId = c.ClienteId)))
    AND ISNULL(c.Ativo, 1) = 1;
GO

/* ----------------------------------------------------------------------------
   7. mart.vw_MapaDemanda (Pareto de Serviços, Categorias e Versões de Release)
---------------------------------------------------------------------------- */
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
LEFT JOIN core.Fato_CampoCustomizado cf ON t.TicketId = cf.TicketId AND cf.CampoId = 133948 -- Versão Release
GROUP BY
    ISNULL(NULLIF(LTRIM(RTRIM(t.Equipe)), N''), N'Sem Equipe'),
    ISNULL(t.ServicoN1, N'Não Informado'),
    t.Categoria,
    t.Urgencia,
    ISNULL(cf.Valor, N'Não Informada');
GO

/* ----------------------------------------------------------------------------
   8. mart.vw_BacklogEvolucao (Curva Histórica Diária do Backlog e SLA Vencido)
      Alimenta o gráfico de evolução diária da fila no Apache Superset
---------------------------------------------------------------------------- */
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
GO

/* ----------------------------------------------------------------------------
   9. mart.vw_TicketsPorClientePeriodo (Distribuição de Tickets por Cliente no Período)
      Alimenta o gráfico Donut e o Grid detalhado de Tickets Abertos por Cliente/Equipe
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
    ISNULL(t.ServicoN1, N'Não Informado') AS Servico,
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
