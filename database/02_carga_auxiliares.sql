/* =============================================================================
   02 - Carga de dados auxiliares e mapeamento de Status / Equipes
   ============================================================================= */
USE [MovideskDM];
GO

/* ----------------------------------------------------------------------------
   1. Popula core.Dim_Status com os status reais e seus grupos analíticos
---------------------------------------------------------------------------- */
MERGE core.Dim_Status AS T
USING (VALUES
    (N'Novo',                             N'Fila (Não Iniciado)',             1, 0, 0, 0, '#3498db'),
    (N'Em atendimento',                   N'Com Analista',                    2, 0, 0, 0, '#f39c12'),
    (N'Aguardando',                       N'Aguardando Cliente',              3, 1, 0, 0, '#95a5a6'),
    (N'Aguardando Retorno do cliente',    N'Aguardando Cliente',              3, 1, 0, 0, '#95a5a6'),
    (N'Aguardando desenvolvimento',       N'Dependência Dev (Ticket Filho)',  4, 0, 1, 0, '#e74c3c'),
    (N'Aguardando liberação de Versão',   N'Dependência Release/Versão',      5, 0, 1, 0, '#9b59b6'),
    (N'Resolvido',                        N'Resolvido (Aguardando Fechamento)',6, 1, 0, 0, '#2ecc71'),
    (N'Fechado',                          N'Encerrado',                       7, 1, 0, 1, '#27ae60'),
    (N'Cancelado',                        N'Cancelado',                       8, 1, 0, 1, '#7f8c8d')
) AS S (Nome, GrupoStatus, OrdemFluxo, PausaSla, EhDependenciaTerceiro, EhFinal, Cor)
ON T.Nome = S.Nome
WHEN MATCHED THEN
    UPDATE SET 
        T.GrupoStatus = S.GrupoStatus,
        T.OrdemFluxo = S.OrdemFluxo,
        T.PausaSla = S.PausaSla,
        T.EhDependenciaTerceiro = S.EhDependenciaTerceiro,
        T.EhFinal = S.EhFinal,
        T.Cor = S.Cor
WHEN NOT MATCHED THEN
    INSERT (Nome, GrupoStatus, OrdemFluxo, PausaSla, EhDependenciaTerceiro, EhFinal, Cor)
    VALUES (S.Nome, S.GrupoStatus, S.OrdemFluxo, S.PausaSla, S.EhDependenciaTerceiro, S.EhFinal, S.Cor);
GO

/* ----------------------------------------------------------------------------
   2. Popula core.Dim_Calendario de 2022 a 2030
---------------------------------------------------------------------------- */
SET DATEFIRST 7; -- 1 = Domingo

;WITH Datas AS (
    SELECT CAST('2022-01-01' AS DATE) AS Data
    UNION ALL
    SELECT DATEADD(DAY, 1, Data)
    FROM Datas
    WHERE Data < '2030-12-31'
)
MERGE core.Dim_Calendario AS T
USING (
    SELECT 
        Data,
        YEAR(Data) AS Ano,
        DATEPART(QUARTER, Data) AS Trimestre,
        MONTH(Data) AS Mes,
        CASE MONTH(Data)
            WHEN 1 THEN N'Janeiro'   WHEN 2 THEN N'Fevereiro' WHEN 3 THEN N'Março'
            WHEN 4 THEN N'Abril'     WHEN 5 THEN N'Maio'      WHEN 6 THEN N'Junho'
            WHEN 7 THEN N'Julho'     WHEN 8 THEN N'Agosto'    WHEN 9 THEN N'Setembro'
            WHEN 10 THEN N'Outubro'  WHEN 11 THEN N'Novembro' WHEN 12 THEN N'Dezembro'
        END AS NomeMes,
        CONVERT(CHAR(7), Data, 126) AS AnoMes,
        DATEPART(WEEK, Data) AS Semana,
        DATEPART(WEEKDAY, Data) AS DiaSemana,
        CASE DATEPART(WEEKDAY, Data)
            WHEN 1 THEN N'Domingo'   WHEN 2 THEN N'Segunda-feira'
            WHEN 3 THEN N'Terça-feira' WHEN 4 THEN N'Quarta-feira'
            WHEN 5 THEN N'Quinta-feira' WHEN 6 THEN N'Sexta-feira'
            WHEN 7 THEN N'Sábado'
        END AS NomeDiaSemana,
        CASE WHEN DATEPART(WEEKDAY, Data) IN (1, 7) THEN 1 ELSE 0 END AS EhFimDeSemana,
        0 AS EhFeriado,
        NULL AS NomeFeriado,
        CASE WHEN DATEPART(WEEKDAY, Data) IN (1, 7) THEN 0 ELSE 1 END AS EhDiaUtil
    FROM Datas
) AS S
ON T.Data = S.Data
WHEN NOT MATCHED THEN
    INSERT (Data, Ano, Trimestre, Mes, NomeMes, AnoMes, Semana, DiaSemana, NomeDiaSemana, EhFimDeSemana, EhFeriado, NomeFeriado, EhDiaUtil)
    VALUES (S.Data, S.Ano, S.Trimestre, S.Mes, S.NomeMes, S.AnoMes, S.Semana, S.DiaSemana, S.NomeDiaSemana, S.EhFimDeSemana, S.EhFeriado, S.NomeFeriado, S.EhDiaUtil)
OPTION (MAXRECURSION 0);
GO

/* ----------------------------------------------------------------------------
   3. Parâmetros iniciais de controle
---------------------------------------------------------------------------- */
MERGE ctl.Parametro AS T
USING (VALUES
    ('HORAS_SEM_INTERACAO_ALERTA', '48', 'Limite em horas para considerar chamado em Backlog Aging crítico'),
    ('HORAS_RADAR_SLA_IMINENTE',   '4',  'Janela de horas para alertar risco iminente de quebra de SLA'),
    ('DIAS_CLIENTE_SILENCIOSO',    '60', 'Dias sem chamados para classificar como cliente silencioso')
) AS S (Chave, Valor, Descricao)
ON T.Chave = S.Chave
WHEN NOT MATCHED THEN
    INSERT (Chave, Valor, Descricao) VALUES (S.Chave, S.Valor, S.Descricao);
GO
