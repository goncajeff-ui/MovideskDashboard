/* =============================================================================
   05 - Atualização Completa (Itens 2 e 3):
        - Conversão de Fuso Horário UTC -> Brasília (E. South America Standard Time)
        - Auto-descoberta de Status não mapeados em core.Dim_Status (Mapeado = 0)
        - Gravação de CriadoPorId e Tags em core.Fato_Ticket
        - Cálculo de DataFim em core.Fato_StatusHistorico (LEAD)
        - Procedure core.usp_AtualizarSnapshotBacklog (Histórico 90d + Foto Hoje)
        - Nova View mart.vw_BacklogEvolucao + Padronização das 7 Views existentes
        - Reprocessamento automático dos tickets já salvos em raw.Ticket (sem custo de API)
   ============================================================================= */
USE [MovideskDM];
GO

/* ----------------------------------------------------------------------------
   1. Popula Dicionário de Campos Customizados (core.Dim_CampoCustomizado)
---------------------------------------------------------------------------- */
MERGE core.Dim_CampoCustomizado AS T
USING (VALUES
    (133948, N'Versão do Produto / Release', N'Versão do sistema informada no chamado (ex.: KN1, e-Guardian, Aquilla)'),
    (133947, N'Campo Customizado #133947',   N'Campo adicional de formulário de atendimento (regra 67477)'),
    (129731, N'Campo Customizado #129731',   N'Campo adicional de formulário de atendimento (regra 64915)'),
    (142628, N'Campo Customizado #142628',   N'Campo adicional de formulário de atendimento (regra 72075)'),
    (184522, N'Campo Customizado #184522',   N'Campo adicional de formulário de atendimento (regra 94167)')
) AS S (CampoId, Nome, Descricao)
ON T.CampoId = S.CampoId
WHEN MATCHED THEN
    UPDATE SET T.Nome = S.Nome, T.Descricao = S.Descricao
WHEN NOT MATCHED THEN
    INSERT (CampoId, Nome, Descricao) VALUES (S.CampoId, S.Nome, S.Descricao);
GO

/* ----------------------------------------------------------------------------
   2. Procedure de Snapshot Diário do Backlog (core.usp_AtualizarSnapshotBacklog)
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
            WHERE ISNULL(st.EhFinal, 0) = 0
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

    -- Atualiza sempre a foto de HOJE
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
            THEN 1
        END) AS QtdSlaVencido
    FROM core.Fato_Ticket t
    LEFT JOIN core.Dim_Status st ON t.Status = st.Nome
    WHERE ISNULL(st.EhFinal, CASE WHEN t.StatusBase IN ('Resolved', 'Closed', 'Canceled') THEN 1 ELSE 0 END) = 0
    GROUP BY
        ISNULL(t.Equipe, N'Sem Equipe'),
        ISNULL(t.AgenteId, 'NAO_ATRIBUIDO'),
        ISNULL(t.Status, N'Novo'),
        ISNULL(t.Urgencia, N'Não Informada');
END;
GO

/* ----------------------------------------------------------------------------
   3. Procedure Principal RAW -> CORE (core.usp_ProcessarTickets)
---------------------------------------------------------------------------- */
CREATE OR ALTER PROCEDURE core.usp_ProcessarTickets
AS
BEGIN
    SET NOCOUNT ON;
    SET XACT_ABORT ON;

    DECLARE @Inicio DATETIME2(0) = SYSDATETIME();
    DECLARE @QtdProcessados INT = 0;
    DECLARE @ExecucaoId INT;

    INSERT INTO ctl.ExecucaoCarga (Tipo, Inicio, Status)
    VALUES ('PROCESSAMENTO_CORE', @Inicio, 'EXECUTANDO');
    SET @ExecucaoId = SCOPE_IDENTITY();

    BEGIN TRY
        DROP TABLE IF EXISTS #Pendentes;
        SELECT TOP (5000) TicketId, Payload, LastUpdateUtc
        INTO #Pendentes
        FROM raw.Ticket
        WHERE Processado = 0;

        SELECT @QtdProcessados = COUNT(1) FROM #Pendentes;
        IF @QtdProcessados = 0
        BEGIN
            UPDATE ctl.ExecucaoCarga 
            SET Fim = SYSDATETIME(), Status = 'SUCESSO', QtdRegistros = 0, Mensagem = 'Nenhum ticket pendente.'
            WHERE ExecucaoId = @ExecucaoId;
            RETURN;
        END

        -- 1. Atualiza Dim_Equipe
        INSERT INTO core.Dim_Equipe (Nome)
        SELECT DISTINCT j.ownerTeam
        FROM #Pendentes p
        CROSS APPLY OPENJSON(p.Payload) WITH (ownerTeam NVARCHAR(128)) j
        WHERE j.ownerTeam IS NOT NULL
          AND NOT EXISTS (SELECT 1 FROM core.Dim_Equipe e WHERE e.Nome = j.ownerTeam);

        -- 1b. Auto-cadastra status novos/históricos em Dim_Status (Mapeado = 0)
        INSERT INTO core.Dim_Status (
            Nome, GrupoStatus, OrdemFluxo, PausaSla, EhDependenciaTerceiro, EhFinal, Cor, Mapeado
        )
        SELECT
            s.StatusNome,
            CASE
                WHEN s.BaseStatus IN ('Resolved', 'Closed', 'Canceled') THEN N'Encerrado'
                WHEN s.BaseStatus = 'Stopped' THEN N'Aguardando Cliente'
                WHEN s.BaseStatus = 'New' THEN N'Fila (Não Iniciado)'
                ELSE N'Com Analista'
            END AS GrupoStatus,
            CASE
                WHEN s.BaseStatus = 'New' THEN 1
                WHEN s.BaseStatus = 'Stopped' THEN 3
                WHEN s.BaseStatus = 'Resolved' THEN 6
                WHEN s.BaseStatus IN ('Closed', 'Canceled') THEN 7
                ELSE 2
            END AS OrdemFluxo,
            CASE WHEN s.BaseStatus IN ('Stopped', 'Resolved', 'Closed', 'Canceled') THEN 1 ELSE 0 END AS PausaSla,
            0 AS EhDependenciaTerceiro,
            CASE WHEN s.BaseStatus IN ('Resolved', 'Closed', 'Canceled') THEN 1 ELSE 0 END AS EhFinal,
            '#64748b' AS Cor,
            0 AS Mapeado
        FROM (
            SELECT
                j.status AS StatusNome,
                MAX(j.baseStatus) AS BaseStatus
            FROM #Pendentes p
            CROSS APPLY OPENJSON(p.Payload) WITH (
                status     NVARCHAR(128),
                baseStatus NVARCHAR(40)
            ) j
            WHERE j.status IS NOT NULL
            GROUP BY j.status
        ) s
        WHERE NOT EXISTS (SELECT 1 FROM core.Dim_Status d WHERE d.Nome = s.StatusNome);

        -- 2. Atualiza Dim_Agente
        MERGE core.Dim_Agente AS T
        USING (
            SELECT DISTINCT
                j.ownerId AS AgenteId,
                ISNULL(j.ownerName, 'Não Atribuído') AS Nome,
                j.ownerEmail AS Email
            FROM #Pendentes p
            CROSS APPLY OPENJSON(p.Payload) WITH (
                owner NVARCHAR(MAX) AS JSON
            ) o
            CROSS APPLY OPENJSON(o.owner) WITH (
                ownerId    VARCHAR(64)   '$.id',
                ownerName  NVARCHAR(256) '$.businessName',
                ownerEmail NVARCHAR(256) '$.email'
            ) j
            WHERE j.ownerId IS NOT NULL
        ) AS S
        ON T.AgenteId = S.AgenteId
        WHEN MATCHED THEN
            UPDATE SET T.Nome = S.Nome, T.Email = S.Email
        WHEN NOT MATCHED THEN
            INSERT (AgenteId, Nome, Email, Ativo)
            VALUES (S.AgenteId, S.Nome, S.Email, 1);

        -- 3. Atualiza Dim_Cliente
        MERGE core.Dim_Cliente AS T
        USING (
            SELECT DISTINCT
                c.id AS ClienteId,
                ISNULL(c.businessName, 'Sem Nome') AS Nome,
                c.corporateName AS RazaoSocial,
                c.personType AS TipoPessoa,
                1 AS Ativo
            FROM #Pendentes p
            CROSS APPLY OPENJSON(p.Payload, '$.clients') WITH (
                id            VARCHAR(64),
                businessName  NVARCHAR(256),
                corporateName NVARCHAR(256),
                personType    TINYINT
            ) c
            WHERE c.id IS NOT NULL
        ) AS S
        ON T.ClienteId = S.ClienteId
        WHEN MATCHED THEN
            UPDATE SET T.Nome = S.Nome, T.RazaoSocial = ISNULL(S.RazaoSocial, T.RazaoSocial)
        WHEN NOT MATCHED THEN
            INSERT (ClienteId, Nome, RazaoSocial, TipoPessoa, Ativo)
            VALUES (S.ClienteId, S.Nome, S.RazaoSocial, S.TipoPessoa, S.Ativo);

        -- 4. Atualiza core.Fato_Ticket (Datas convertidas de UTC -> Horário de Brasília + CriadoPorId/Tags)
        MERGE core.Fato_Ticket AS T
        USING (
            SELECT 
                p.TicketId,
                j.protocol,
                j.type,
                j.subject,
                j.category,
                j.urgency,
                j.status,
                j.baseStatus,
                j.justification,
                j.origin,
                j.ownerTeam,
                o.ownerId,
                j.createdById,
                cli.primeiroClienteId AS EmpresaId,
                j.serviceFirstLevel,
                j.serviceSecondLevel,
                j.serviceThirdLevel,
                LEFT(j.tags, 1000) AS Tags,
                CAST(TRY_CONVERT(DATETIME2(0), NULLIF(j.createdDate, '')) AT TIME ZONE 'UTC' AT TIME ZONE 'E. South America Standard Time' AS DATETIME2(0)) AS DataCriacao,
                CAST(TRY_CONVERT(DATETIME2(0), NULLIF(j.lastUpdate, '')) AT TIME ZONE 'UTC' AT TIME ZONE 'E. South America Standard Time' AS DATETIME2(0)) AS DataUltimaAtualizacao,
                CAST(TRY_CONVERT(DATETIME2(0), NULLIF(j.lastActionDate, '')) AT TIME ZONE 'UTC' AT TIME ZONE 'E. South America Standard Time' AS DATETIME2(0)) AS DataUltimaAcao,
                CAST(TRY_CONVERT(DATETIME2(0), NULLIF(j.resolvedIn, '')) AT TIME ZONE 'UTC' AT TIME ZONE 'E. South America Standard Time' AS DATETIME2(0)) AS DataResolucao,
                CAST(TRY_CONVERT(DATETIME2(0), NULLIF(j.closedIn, '')) AT TIME ZONE 'UTC' AT TIME ZONE 'E. South America Standard Time' AS DATETIME2(0)) AS DataFechamento,
                CAST(TRY_CONVERT(DATETIME2(0), NULLIF(j.reopenedIn, '')) AT TIME ZONE 'UTC' AT TIME ZONE 'E. South America Standard Time' AS DATETIME2(0)) AS DataReabertura,
                j.actionCount,
                j.slaAgreement,
                j.slaAgreementRule,
                j.slaSolutionTime AS SlaTempoSolucaoMin,
                j.slaResponseTime AS SlaTempoRespostaMin,
                CAST(TRY_CONVERT(DATETIME2(0), NULLIF(j.slaSolutionDate, '')) AT TIME ZONE 'UTC' AT TIME ZONE 'E. South America Standard Time' AS DATETIME2(0)) AS SlaDataSolucao,
                j.slaSolutionDateIsPaused,
                CAST(TRY_CONVERT(DATETIME2(0), NULLIF(j.slaResponseDate, '')) AT TIME ZONE 'UTC' AT TIME ZONE 'E. South America Standard Time' AS DATETIME2(0)) AS SlaDataResposta,
                CAST(TRY_CONVERT(DATETIME2(0), NULLIF(j.slaRealResponseDate, '')) AT TIME ZONE 'UTC' AT TIME ZONE 'E. South America Standard Time' AS DATETIME2(0)) AS SlaDataRespostaReal,
                j.resolvedInFirstCall
            FROM #Pendentes p
            CROSS APPLY OPENJSON(p.Payload) WITH (
                protocol                NVARCHAR(64),
                type                    TINYINT,
                subject                 NVARCHAR(400),
                category                NVARCHAR(128),
                urgency                 NVARCHAR(128),
                status                  NVARCHAR(128),
                baseStatus              NVARCHAR(40),
                justification           NVARCHAR(256),
                origin                  SMALLINT,
                ownerTeam               NVARCHAR(128),
                createdById             VARCHAR(64) '$.createdBy.id',
                serviceFirstLevel       NVARCHAR(256),
                serviceSecondLevel      NVARCHAR(256),
                serviceThirdLevel       NVARCHAR(256),
                tags                    NVARCHAR(MAX) AS JSON,
                createdDate             NVARCHAR(40),
                lastUpdate              NVARCHAR(40),
                lastActionDate          NVARCHAR(40),
                resolvedIn              NVARCHAR(40),
                closedIn                NVARCHAR(40),
                reopenedIn              NVARCHAR(40),
                actionCount             INT,
                slaAgreement            NVARCHAR(256),
                slaAgreementRule        NVARCHAR(256),
                slaSolutionTime         INT,
                slaResponseTime         INT,
                slaSolutionDate         NVARCHAR(40),
                slaSolutionDateIsPaused BIT,
                slaResponseDate         NVARCHAR(40),
                slaRealResponseDate     NVARCHAR(40),
                resolvedInFirstCall     BIT
            ) j
            OUTER APPLY (
                SELECT JSON_VALUE(p.Payload, '$.owner.id') AS ownerId
            ) o
            OUTER APPLY (
                SELECT TOP 1 id AS primeiroClienteId
                FROM OPENJSON(p.Payload, '$.clients') WITH (id VARCHAR(64))
            ) cli
        ) AS S
        ON T.TicketId = S.TicketId
        WHEN MATCHED THEN
            UPDATE SET 
                T.Protocolo = S.protocol,
                T.Tipo = S.type,
                T.Assunto = S.subject,
                T.Categoria = S.category,
                T.Urgencia = S.urgency,
                T.Status = S.status,
                T.StatusBase = S.baseStatus,
                T.Justificativa = S.justification,
                T.Origem = S.origin,
                T.Equipe = S.ownerTeam,
                T.AgenteId = S.ownerId,
                T.CriadoPorId = ISNULL(S.createdById, T.CriadoPorId),
                T.EmpresaId = S.EmpresaId,
                T.ServicoN1 = S.serviceFirstLevel,
                T.ServicoN2 = S.serviceSecondLevel,
                T.ServicoN3 = S.serviceThirdLevel,
                T.Tags = S.Tags,
                T.DataCriacao = S.DataCriacao,
                T.DataUltimaAtualizacao = S.DataUltimaAtualizacao,
                T.DataUltimaAcao = S.DataUltimaAcao,
                T.DataResolucao = S.DataResolucao,
                T.DataFechamento = S.DataFechamento,
                T.DataReabertura = S.DataReabertura,
                T.QtdAcoes = S.actionCount,
                T.SlaAcordo = S.slaAgreement,
                T.SlaRegra = S.slaAgreementRule,
                T.SlaTempoSolucaoMin = S.SlaTempoSolucaoMin,
                T.SlaTempoRespostaMin = S.SlaTempoRespostaMin,
                T.SlaDataSolucao = S.SlaDataSolucao,
                T.SlaSolucaoPausado = S.slaSolutionDateIsPaused,
                T.SlaDataResposta = S.SlaDataResposta,
                T.SlaDataRespostaReal = S.SlaDataRespostaReal,
                T.ResolvidoPrimeiroContato = S.resolvedInFirstCall,
                T.AtualizadoEm = SYSDATETIME()
        WHEN NOT MATCHED THEN
            INSERT (
                TicketId, Protocolo, Tipo, Assunto, Categoria, Urgencia, Status, StatusBase,
                Justificativa, Origem, Equipe, AgenteId, CriadoPorId, EmpresaId, ServicoN1, ServicoN2, ServicoN3, Tags,
                DataCriacao, DataUltimaAtualizacao, DataUltimaAcao, DataResolucao, DataFechamento,
                DataReabertura, QtdAcoes, SlaAcordo, SlaRegra, SlaTempoSolucaoMin, SlaTempoRespostaMin,
                SlaDataSolucao, SlaSolucaoPausado, SlaDataResposta, SlaDataRespostaReal,
                ResolvidoPrimeiroContato, AtualizadoEm
            )
            VALUES (
                S.TicketId, S.protocol, S.type, S.subject, S.category, S.urgency, S.status, S.baseStatus,
                S.justification, S.origin, S.ownerTeam, S.ownerId, S.createdById, S.EmpresaId, S.serviceFirstLevel, S.serviceSecondLevel, S.serviceThirdLevel, S.Tags,
                S.DataCriacao, S.DataUltimaAtualizacao, S.DataUltimaAcao, S.DataResolucao, S.DataFechamento,
                S.DataReabertura, S.actionCount, S.slaAgreement, S.slaAgreementRule, S.SlaTempoSolucaoMin, S.SlaTempoRespostaMin,
                S.SlaDataSolucao, S.slaSolutionDateIsPaused, S.SlaDataResposta, S.SlaDataRespostaReal,
                S.resolvedInFirstCall, SYSDATETIME()
            );

        -- 5. Atualiza core.Fato_StatusHistorico (BRT + DataFim via LEAD)
        DELETE h
        FROM core.Fato_StatusHistorico h
        INNER JOIN #Pendentes p ON h.TicketId = p.TicketId;

        ;WITH HistoricoBruto AS (
            SELECT 
                p.TicketId,
                sh.status AS Status,
                sh.justification AS Justificativa,
                ISNULL(
                    CAST(TRY_CONVERT(DATETIME2(0), NULLIF(sh.changedDate, '')) AT TIME ZONE 'UTC' AT TIME ZONE 'E. South America Standard Time' AS DATETIME2(0)),
                    SYSDATETIME()
                ) AS DataInicio,
                CAST(ROUND(sh.permanencyTimeFullTime / 60.0, 0) AS INT) AS PermanenciaMinCorridos,
                CAST(ROUND(sh.permanencyTimeWorkingTime / 60.0, 0) AS INT) AS PermanenciaMinUteis
            FROM #Pendentes p
            CROSS APPLY OPENJSON(p.Payload, '$.statusHistories') WITH (
                status                      NVARCHAR(128),
                justification               NVARCHAR(256),
                changedDate                 NVARCHAR(40),
                permanencyTimeFullTime      FLOAT,
                permanencyTimeWorkingTime   FLOAT
            ) sh
            WHERE sh.status IS NOT NULL
        ),
        HistoricoOrdenado AS (
            SELECT
                TicketId,
                ROW_NUMBER() OVER (PARTITION BY TicketId ORDER BY DataInicio) AS Sequencia,
                Status,
                Justificativa,
                DataInicio,
                LEAD(DataInicio) OVER (PARTITION BY TicketId ORDER BY DataInicio) AS DataFim,
                PermanenciaMinCorridos,
                PermanenciaMinUteis
            FROM HistoricoBruto
        )
        INSERT INTO core.Fato_StatusHistorico (
            TicketId, Sequencia, Status, Justificativa, DataInicio, DataFim,
            PermanenciaMinCorridos, PermanenciaMinUteis
        )
        SELECT
            TicketId, Sequencia, Status, Justificativa, DataInicio, DataFim,
            PermanenciaMinCorridos, PermanenciaMinUteis
        FROM HistoricoOrdenado;

        -- 6. Atualiza core.Fato_CampoCustomizado
        DELETE c
        FROM core.Fato_CampoCustomizado c
        INNER JOIN #Pendentes p ON c.TicketId = p.TicketId;

        INSERT INTO core.Fato_CampoCustomizado (TicketId, CampoId, Linha, Valor)
        SELECT 
            p.TicketId,
            cf.customFieldId,
            ISNULL(cf.line, 1),
            cf.value
        FROM #Pendentes p
        CROSS APPLY OPENJSON(p.Payload, '$.customFieldValues') WITH (
            customFieldId INT,
            line          INT,
            value         NVARCHAR(1000)
        ) cf
        WHERE cf.value IS NOT NULL AND LEN(cf.value) > 0;

        UPDATE r
        SET Processado = 1
        FROM raw.Ticket r
        INNER JOIN #Pendentes p ON r.TicketId = p.TicketId;

        -- 7. Atualiza core.Fato_SnapshotBacklog
        DECLARE @Reconstruir BIT = CASE WHEN @QtdProcessados < 50 THEN 1 ELSE 0 END;
        EXEC core.usp_AtualizarSnapshotBacklog @DiasRetroativos = 90, @ReconstruirHistorico = @Reconstruir;

        UPDATE ctl.ExecucaoCarga
        SET Fim = SYSDATETIME(), Status = 'SUCESSO', QtdRegistros = @QtdProcessados,
            Mensagem = CONCAT(@QtdProcessados, ' tickets processados do RAW para CORE (BRT) com sucesso.')
        WHERE ExecucaoId = @ExecucaoId;

    END TRY
    BEGIN CATCH
        DECLARE @ErroMsg NVARCHAR(4000) = ERROR_MESSAGE();
        UPDATE ctl.ExecucaoCarga
        SET Fim = SYSDATETIME(), Status = 'ERRO', Mensagem = @ErroMsg
        WHERE ExecucaoId = @ExecucaoId;
        THROW;
    END CATCH
END;
GO

/* ----------------------------------------------------------------------------
   4. Atualização das 7 Views + Criação da 8ª View (mart.vw_BacklogEvolucao)
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
        ISNULL(t.Equipe, N'Sem Equipe') AS Equipe,
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
        ISNULL(st.EhFinal, CASE WHEN t.StatusBase IN ('Resolved', 'Closed', 'Canceled') THEN 1 ELSE 0 END) AS EhFinal,
        ISNULL(st.EhDependenciaTerceiro, 0) AS EhDependenciaTerceiro,
        p.MinutosSlaIminente
    FROM core.Fato_Ticket t
    LEFT JOIN core.Dim_Status st ON t.Status = st.Nome
    CROSS JOIN Parametros p
)
SELECT 
    b.Equipe,
    COUNT(CASE WHEN b.EhFinal = 0 THEN 1 END) AS BacklogAtual,
    COUNT(CASE WHEN b.EhFinal = 0 AND b.SlaDataSolucao < SYSDATETIME() AND ISNULL(b.SlaSolucaoPausado, 0) = 0 THEN 1 END) AS SlaVencidos,
    COUNT(CASE WHEN b.EhFinal = 0 AND b.SlaDataSolucao >= SYSDATETIME() AND DATEDIFF(MINUTE, SYSDATETIME(), b.SlaDataSolucao) <= b.MinutosSlaIminente AND ISNULL(b.SlaSolucaoPausado, 0) = 0 THEN 1 END) AS SlaIminente4h,
    COUNT(CASE WHEN b.EhFinal = 0 AND b.SlaSolucaoPausado = 1 THEN 1 END) AS SlaPausados,
    COUNT(CASE WHEN b.EhFinal = 0 AND b.EhDependenciaTerceiro = 1 THEN 1 END) AS EmDependenciaDev,
    COUNT(CASE WHEN CAST(b.DataCriacao AS DATE) = CAST(SYSDATETIME() AS DATE) THEN 1 END) AS AbertosHoje,
    COUNT(CASE WHEN CAST(b.DataResolucao AS DATE) = CAST(SYSDATETIME() AS DATE) THEN 1 END) AS ResolvidosHoje,
    CAST(ROUND(100.0 * COUNT(CASE WHEN b.DataResolucao >= DATEADD(DAY, -30, SYSDATETIME()) AND b.ResolvidoPrimeiroContato = 1 THEN 1 END) 
        / NULLIF(COUNT(CASE WHEN b.DataResolucao >= DATEADD(DAY, -30, SYSDATETIME()) THEN 1 END), 0), 1) AS DECIMAL(5,1)) AS FcrUltimos30DiasPct
FROM Base b
GROUP BY b.Equipe;
GO

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
    t.Categoria,
    t.Urgencia,
    t.Status,
    ISNULL(st.GrupoStatus, N'Outros') AS GrupoStatus,
    ISNULL(t.Equipe, N'Sem Equipe') AS Equipe,
    ISNULL(ag.Nome, N'Não Atribuído') AS Analista,
    ISNULL(cli.Nome, N'Não Identificado') AS Cliente,
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
CROSS JOIN Parametros p
WHERE ISNULL(st.EhFinal, CASE WHEN t.StatusBase IN ('Resolved', 'Closed', 'Canceled') THEN 1 ELSE 0 END) = 0;
GO

CREATE OR ALTER VIEW mart.vw_BacklogAging
AS
WITH Parametros AS (
    SELECT
        ISNULL(TRY_CAST((SELECT Valor FROM ctl.Parametro WHERE Chave = 'HORAS_SEM_INTERACAO_ALERTA') AS INT), 48) AS HorasLimiteSemInteracao
)
SELECT 
    t.TicketId,
    t.Assunto,
    ISNULL(t.Equipe, N'Sem Equipe') AS Equipe,
    ISNULL(ag.Nome, N'Não Atribuído') AS Analista,
    ISNULL(cli.Nome, N'Não Identificado') AS Cliente,
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
CROSS JOIN Parametros p
WHERE ISNULL(st.EhFinal, CASE WHEN t.StatusBase IN ('Resolved', 'Closed', 'Canceled') THEN 1 ELSE 0 END) = 0;
GO

CREATE OR ALTER VIEW mart.vw_StatusAging
AS
WITH Passagens AS (
    SELECT
        ISNULL(t.Equipe, N'Sem Equipe') AS Equipe,
        sh.Status,
        ISNULL(st.GrupoStatus, N'Outros') AS GrupoStatus,
        ISNULL(st.EhDependenciaTerceiro, 0) AS EhDependenciaTerceiro,
        ISNULL(
            sh.PermanenciaMinCorridos,
            CASE
                WHEN sh.DataFim IS NULL
                     AND ISNULL(st.EhFinal, CASE WHEN t.StatusBase IN ('Resolved', 'Closed', 'Canceled') THEN 1 ELSE 0 END) = 0
                     AND sh.DataInicio < SYSDATETIME()
                THEN DATEDIFF(MINUTE, sh.DataInicio, SYSDATETIME())
            END
        ) AS MinutosCorridos,
        ISNULL(
            sh.PermanenciaMinUteis,
            CASE
                WHEN sh.DataFim IS NULL
                     AND ISNULL(st.EhFinal, CASE WHEN t.StatusBase IN ('Resolved', 'Closed', 'Canceled') THEN 1 ELSE 0 END) = 0
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
        ISNULL(Equipe, N'Sem Equipe') AS Equipe,
        COUNT(1) AS QtdAbertos
    FROM core.Fato_Ticket
    WHERE DataCriacao IS NOT NULL
    GROUP BY CAST(DataCriacao AS DATE), ISNULL(Equipe, N'Sem Equipe')
),
Resolvidos AS (
    SELECT 
        CAST(DataResolucao AS DATE) AS Data,
        ISNULL(Equipe, N'Sem Equipe') AS Equipe,
        COUNT(1) AS QtdResolvidos
    FROM core.Fato_Ticket
    WHERE DataResolucao IS NOT NULL
    GROUP BY CAST(DataResolucao AS DATE), ISNULL(Equipe, N'Sem Equipe')
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
CROSS JOIN (SELECT Nome FROM core.Dim_Equipe WHERE EhSuporte = 1) eq
LEFT JOIN Abertos a ON d.Data = a.Data AND eq.Nome = a.Equipe
LEFT JOIN Resolvidos r ON d.Data = r.Data AND eq.Nome = r.Equipe;
GO

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
GROUP BY c.ClienteId, c.Nome, c.RazaoSocial, p.DiasSilenciosoCritico;
GO

CREATE OR ALTER VIEW mart.vw_MapaDemanda
AS
SELECT 
    ISNULL(t.Equipe, N'Sem Equipe') AS Equipe,
    t.Categoria,
    t.Urgencia,
    ISNULL(cf.Valor, N'Não Informada') AS VersaoProduto,
    COUNT(1) AS Volumetria,
    COUNT(CASE WHEN ISNULL(st.EhFinal, CASE WHEN t.StatusBase IN ('Resolved', 'Closed', 'Canceled') THEN 1 ELSE 0 END) = 0 THEN 1 END) AS Abertos,
    CAST(ROUND(AVG(DATEDIFF(HOUR, t.DataCriacao, ISNULL(t.DataResolucao, SYSDATETIME()))), 1) AS DECIMAL(10,1)) AS HorasMediasResolucao
FROM core.Fato_Ticket t
LEFT JOIN core.Dim_Status st ON t.Status = st.Nome
LEFT JOIN core.Fato_CampoCustomizado cf ON t.TicketId = cf.TicketId AND cf.CampoId = 133948
GROUP BY ISNULL(t.Equipe, N'Sem Equipe'), t.Categoria, t.Urgencia, ISNULL(cf.Valor, N'Não Informada');
GO

CREATE OR ALTER VIEW mart.vw_BacklogEvolucao
AS
SELECT
    sb.DataSnapshot,
    cal.AnoMes,
    cal.NomeDiaSemana,
    cal.EhDiaUtil,
    sb.Equipe,
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
   5. Reprocessa todos os tickets já existentes em raw.Ticket (sem chamar a API!)
      para aplicar Fuso de Brasília, CriadoPorId, Tags, DataFim e Snapshot 90d
---------------------------------------------------------------------------- */
UPDATE raw.Ticket SET Processado = 0 WHERE Processado = 1;

WHILE EXISTS (SELECT 1 FROM raw.Ticket WHERE Processado = 0)
BEGIN
    EXEC core.usp_ProcessarTickets;
END

EXEC core.usp_AtualizarSnapshotBacklog @DiasRetroativos = 90, @ReconstruirHistorico = 1;
GO
