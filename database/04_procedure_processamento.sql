/* =============================================================================
   04 - Procedure de Processamento (RAW -> CORE)
   Faz o parse do JSON do Movidesk e atualiza fatos e dimensões
   ============================================================================= */
USE [MovideskDM];
GO

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
        -- Tabela temporária para os tickets pendentes de processamento
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

        /* --------------------------------------------------------------------
           1. Atualiza Dim_Equipe
        -------------------------------------------------------------------- */
        INSERT INTO core.Dim_Equipe (Nome)
        SELECT DISTINCT j.ownerTeam
        FROM #Pendentes p
        CROSS APPLY OPENJSON(p.Payload) WITH (ownerTeam NVARCHAR(128)) j
        WHERE j.ownerTeam IS NOT NULL
          AND NOT EXISTS (SELECT 1 FROM core.Dim_Equipe e WHERE e.Nome = j.ownerTeam);

        /* --------------------------------------------------------------------
           2. Atualiza Dim_Agente
        -------------------------------------------------------------------- */
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

        /* --------------------------------------------------------------------
           3. Atualiza Dim_Cliente (extraído de clients)
        -------------------------------------------------------------------- */
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

        /* --------------------------------------------------------------------
           4. Atualiza core.Fato_Ticket
        -------------------------------------------------------------------- */
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
                j.tags,
                TRY_CONVERT(DATETIME2(0), j.createdDate) AS DataCriacao,
                TRY_CONVERT(DATETIME2(0), j.lastUpdate) AS DataUltimaAtualizacao,
                TRY_CONVERT(DATETIME2(0), j.lastActionDate) AS DataUltimaAcao,
                TRY_CONVERT(DATETIME2(0), j.resolvedIn) AS DataResolucao,
                TRY_CONVERT(DATETIME2(0), j.closedIn) AS DataFechamento,
                TRY_CONVERT(DATETIME2(0), j.reopenedIn) AS DataReabertura,
                j.actionCount,
                j.slaAgreement,
                j.slaAgreementRule,
                j.slaSolutionTime,
                j.slaResponseTime,
                TRY_CONVERT(DATETIME2(0), j.slaSolutionDate) AS SlaDataSolucao,
                j.slaSolutionDateIsPaused,
                TRY_CONVERT(DATETIME2(0), j.slaResponseDate) AS SlaDataResposta,
                TRY_CONVERT(DATETIME2(0), j.slaRealResponseDate) AS SlaDataRespostaReal,
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
                T.EmpresaId = S.EmpresaId,
                T.ServicoN1 = S.serviceFirstLevel,
                T.ServicoN2 = S.serviceSecondLevel,
                T.ServicoN3 = S.serviceThirdLevel,
                T.DataCriacao = S.DataCriacao,
                T.DataUltimaAtualizacao = S.DataUltimaAtualizacao,
                T.DataUltimaAcao = S.DataUltimaAcao,
                T.DataResolucao = S.DataResolucao,
                T.DataFechamento = S.DataFechamento,
                T.DataReabertura = S.DataReabertura,
                T.QtdAcoes = S.actionCount,
                T.SlaAcordo = S.slaAgreement,
                T.SlaRegra = S.slaAgreementRule,
                T.SlaTempoSolucaoMin = S.slaSolutionTime,
                T.SlaTempoRespostaMin = S.slaResponseTime,
                T.SlaDataSolucao = S.SlaDataSolucao,
                T.SlaSolucaoPausado = S.slaSolutionDateIsPaused,
                T.SlaDataResposta = S.SlaDataResposta,
                T.SlaDataRespostaReal = S.SlaDataRespostaReal,
                T.ResolvidoPrimeiroContato = S.resolvedInFirstCall,
                T.AtualizadoEm = SYSDATETIME()
        WHEN NOT MATCHED THEN
            INSERT (
                TicketId, Protocolo, Tipo, Assunto, Categoria, Urgencia, Status, StatusBase,
                Justificativa, Origem, Equipe, AgenteId, EmpresaId, ServicoN1, ServicoN2, ServicoN3,
                DataCriacao, DataUltimaAtualizacao, DataUltimaAcao, DataResolucao, DataFechamento,
                DataReabertura, QtdAcoes, SlaAcordo, SlaRegra, SlaTempoSolucaoMin, SlaTempoRespostaMin,
                SlaDataSolucao, SlaSolucaoPausado, SlaDataResposta, SlaDataRespostaReal,
                ResolvidoPrimeiroContato, AtualizadoEm
            )
            VALUES (
                S.TicketId, S.protocol, S.type, S.subject, S.category, S.urgency, S.status, S.baseStatus,
                S.justification, S.origin, S.ownerTeam, S.ownerId, S.EmpresaId, S.serviceFirstLevel, S.serviceSecondLevel, S.serviceThirdLevel,
                S.DataCriacao, S.DataUltimaAtualizacao, S.DataUltimaAcao, S.DataResolucao, S.DataFechamento,
                S.DataReabertura, S.actionCount, S.slaAgreement, S.slaAgreementRule, S.slaTempoSolucaoMin, S.slaTempoRespostaMin,
                S.SlaDataSolucao, S.slaSolutionDateIsPaused, S.SlaDataResposta, S.SlaDataRespostaReal,
                S.resolvedInFirstCall, SYSDATETIME()
            );

        /* --------------------------------------------------------------------
           5. Atualiza core.Fato_StatusHistorico
        -------------------------------------------------------------------- */
        DELETE h
        FROM core.Fato_StatusHistorico h
        INNER JOIN #Pendentes p ON h.TicketId = p.TicketId;

        INSERT INTO core.Fato_StatusHistorico (
            TicketId, Sequencia, Status, Justificativa, DataInicio,
            PermanenciaMinCorridos, PermanenciaMinUteis
        )
        SELECT 
            p.TicketId,
            ROW_NUMBER() OVER (PARTITION BY p.TicketId ORDER BY TRY_CONVERT(DATETIME2(0), sh.changedDate)) AS Sequencia,
            sh.status,
            sh.justification,
            ISNULL(TRY_CONVERT(DATETIME2(0), sh.changedDate), SYSDATETIME()) AS DataInicio,
            CAST(ROUND(sh.permanencyTimeFullTime / 60.0, 0) AS INT) AS PermanenciaMinCorridos,
            CAST(ROUND(sh.permanencyTimeWorkingTime / 60.0, 0) AS INT) AS PermanenciaMinUteis
        FROM #Pendentes p
        CROSS APPLY OPENJSON(p.Payload, '$.statusHistories') WITH (
            status                      NVARCHAR(128),
            justification               NVARCHAR(256),
            changedDate                 NVARCHAR(40),
            permanencyTimeFullTime      FLOAT,
            permanencyTimeWorkingTime   FLOAT
        ) sh;

        /* --------------------------------------------------------------------
           6. Atualiza core.Fato_CampoCustomizado (ex: versão do sistema)
        -------------------------------------------------------------------- */
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

        -- Marca pendentes como processados
        UPDATE r
        SET Processado = 1
        FROM raw.Ticket r
        INNER JOIN #Pendentes p ON r.TicketId = p.TicketId;

        UPDATE ctl.ExecucaoCarga
        SET Fim = SYSDATETIME(), Status = 'SUCESSO', QtdRegistros = @QtdProcessados,
            Mensagem = CONCAT(@QtdProcessados, ' tickets processados do RAW para CORE com sucesso.')
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
