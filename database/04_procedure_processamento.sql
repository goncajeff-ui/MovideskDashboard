/* =============================================================================
   04 - Procedures de Processamento (RAW -> CORE) e Snapshot Diário de Backlog
   - Converte timestamps UTC da API para Horário de Brasília (E. South America Standard Time)
   - Auto-mapeia novos status em core.Dim_Status (Mapeado = 0)
   - Grava CriadoPorId e Tags em core.Fato_Ticket
   - Calcula DataFim em core.Fato_StatusHistorico via LEAD()
   - Popula core.Fato_SnapshotBacklog (histórico de 90 dias + foto do dia)
   ============================================================================= */
USE [MovideskDM];
GO

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

    -- Reconstrói os últimos N dias a partir de Fato_Ticket + Fato_StatusHistorico
    -- quando a tabela está vazia ou quando solicitado (@ReconstruirHistorico = 1)
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

    -- Atualiza sempre a foto de HOJE com o estado atual de core.Fato_Ticket
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

CREATE OR ALTER PROCEDURE core.usp_ProcessarPessoas
AS
BEGIN
    SET NOCOUNT ON;
    SET XACT_ABORT ON;

    DROP TABLE IF EXISTS #PessoasPendentes;
    SELECT TOP (5000) PessoaId, Payload
    INTO #PessoasPendentes
    FROM raw.Pessoa
    WHERE Processado = 0;

    IF NOT EXISTS (SELECT 1 FROM #PessoasPendentes)
        RETURN;

    /* --------------------------------------------------------------------
       1. Garante na Dim_Cliente todas as Empresas referenciadas em $.relationships
    -------------------------------------------------------------------- */
    MERGE core.Dim_Cliente AS T
    USING (
        SELECT
            CASE
                WHEN CHARINDEX('/', r.orgId) > 0 THEN LEFT(r.orgId, CHARINDEX('/', r.orgId) - 1)
                ELSE r.orgId
            END AS ClienteId,
            MAX(ISNULL(
                CASE
                    WHEN CHARINDEX('/', r.orgName) > 0 THEN LEFT(r.orgName, CHARINDEX('/', r.orgName) - 1)
                    ELSE r.orgName
                END,
                N'Empresa Sem Nome'
            )) AS Nome
        FROM #PessoasPendentes p
        CROSS APPLY OPENJSON(p.Payload, '$.relationships') WITH (
            orgId   VARCHAR(64)   '$.id',
            orgName NVARCHAR(256) '$.name'
        ) r
        WHERE r.orgId IS NOT NULL AND LEN(r.orgId) > 0
        GROUP BY
            CASE
                WHEN CHARINDEX('/', r.orgId) > 0 THEN LEFT(r.orgId, CHARINDEX('/', r.orgId) - 1)
                ELSE r.orgId
            END
    ) AS S
    ON T.ClienteId = S.ClienteId
    WHEN MATCHED THEN
        UPDATE SET
            T.Nome = ISNULL(T.Nome, S.Nome),
            T.TipoPessoa = ISNULL(T.TipoPessoa, 2)
    WHEN NOT MATCHED THEN
        INSERT (ClienteId, Nome, TipoPessoa, Ativo)
        VALUES (S.ClienteId, S.Nome, 2, 1);

    /* --------------------------------------------------------------------
       2. Atualiza Dim_Cliente com o cadastro completo de Empresas e Pessoas
    -------------------------------------------------------------------- */
    MERGE core.Dim_Cliente AS T
    USING (
        SELECT
            p.PessoaId AS ClienteId,
            MAX(ISNULL(j.businessName, ISNULL(j.corporateName, N'Sem Nome'))) AS Nome,
            MAX(j.corporateName) AS RazaoSocial,
            MAX(j.personType) AS TipoPessoa,
            MAX(rel.EmpresaId) AS EmpresaId,
            MAX(CAST(j.isActive AS INT)) AS Ativo,
            MAX(CAST(TRY_CONVERT(DATETIME2(0), NULLIF(j.createdDate, '')) AT TIME ZONE 'UTC' AT TIME ZONE 'E. South America Standard Time' AS DATETIME2(0))) AS DataCadastro
        FROM #PessoasPendentes p
        CROSS APPLY OPENJSON(p.Payload) WITH (
            businessName  NVARCHAR(256) '$.businessName',
            corporateName NVARCHAR(256) '$.corporateName',
            personType    TINYINT       '$.personType',
            isActive      BIT           '$.isActive',
            createdDate   NVARCHAR(40)  '$.createdDate'
        ) j
        OUTER APPLY (
            SELECT TOP 1
                CASE
                    WHEN CHARINDEX('/', r.orgId) > 0 THEN LEFT(r.orgId, CHARINDEX('/', r.orgId) - 1)
                    ELSE r.orgId
                END AS EmpresaId
            FROM OPENJSON(p.Payload, '$.relationships') WITH (
                orgId VARCHAR(64) '$.id'
            ) r
            WHERE r.orgId IS NOT NULL AND LEN(r.orgId) > 0
        ) rel
        GROUP BY p.PessoaId
    ) AS S
    ON T.ClienteId = S.ClienteId
    WHEN MATCHED THEN
        UPDATE SET
            T.Nome = S.Nome,
            T.RazaoSocial = ISNULL(S.RazaoSocial, T.RazaoSocial),
            T.TipoPessoa = ISNULL(S.TipoPessoa, T.TipoPessoa),
            T.EmpresaId = ISNULL(S.EmpresaId, T.EmpresaId),
            T.Ativo = ISNULL(S.Ativo, T.Ativo),
            T.DataCadastro = ISNULL(S.DataCadastro, T.DataCadastro)
    WHEN NOT MATCHED THEN
        INSERT (ClienteId, Nome, RazaoSocial, TipoPessoa, EmpresaId, Ativo, DataCadastro)
        VALUES (S.ClienteId, S.Nome, S.RazaoSocial, S.TipoPessoa, S.EmpresaId, ISNULL(S.Ativo, 1), S.DataCadastro);

    /* --------------------------------------------------------------------
       3. Retro-atualiza Fato_Ticket e Fato_TicketCliente onde EmpresaId
          estava apontando para a Pessoa Física em vez da Organização!
    -------------------------------------------------------------------- */
    UPDATE t
    SET t.EmpresaId = c.EmpresaId,
        t.AtualizadoEm = SYSDATETIME()
    FROM core.Fato_Ticket t
    INNER JOIN core.Dim_Cliente c ON t.EmpresaId = c.ClienteId
    WHERE c.EmpresaId IS NOT NULL
      AND t.EmpresaId <> c.EmpresaId;

    UPDATE tc
    SET tc.EmpresaId = c.EmpresaId
    FROM core.Fato_TicketCliente tc
    INNER JOIN core.Dim_Cliente c ON tc.ClienteId = c.ClienteId
    WHERE c.EmpresaId IS NOT NULL
      AND (tc.EmpresaId IS NULL OR tc.EmpresaId <> c.EmpresaId);

    UPDATE r
    SET Processado = 1
    FROM raw.Pessoa r
    INNER JOIN #PessoasPendentes p ON r.PessoaId = p.PessoaId;
END;
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
           1b. Auto-cadastra status novos/históricos em Dim_Status (Mapeado = 0)
               para que nenhum chamado fique com EhFinal NULL nas views
        -------------------------------------------------------------------- */
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

        /* --------------------------------------------------------------------
           2. Atualiza Dim_Agente
        -------------------------------------------------------------------- */
        MERGE core.Dim_Agente AS T
        USING (
            SELECT
                j.ownerId AS AgenteId,
                MAX(ISNULL(j.ownerName, N'Não Atribuído')) AS Nome,
                MAX(j.ownerEmail) AS Email
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
            GROUP BY j.ownerId
        ) AS S
        ON T.AgenteId = S.AgenteId
        WHEN MATCHED THEN
            UPDATE SET T.Nome = S.Nome, T.Email = ISNULL(S.Email, T.Email)
        WHEN NOT MATCHED THEN
            INSERT (AgenteId, Nome, Email, Ativo)
            VALUES (S.AgenteId, S.Nome, S.Email, 1);

        /* --------------------------------------------------------------------
           3a. Atualiza Dim_Cliente com as Organizações ($.clients[].organization)
        -------------------------------------------------------------------- */
        MERGE core.Dim_Cliente AS T
        USING (
            SELECT
                c.orgId AS ClienteId,
                MAX(ISNULL(c.orgName, N'Empresa Sem Nome')) AS Nome,
                MAX(c.orgCorporateName) AS RazaoSocial,
                2 AS TipoPessoa,
                1 AS Ativo
            FROM #Pendentes p
            CROSS APPLY OPENJSON(p.Payload, '$.clients') WITH (
                orgId            VARCHAR(64)   '$.organization.id',
                orgName          NVARCHAR(256) '$.organization.businessName',
                orgCorporateName NVARCHAR(256) '$.organization.corporateName'
            ) c
            WHERE c.orgId IS NOT NULL
            GROUP BY c.orgId
        ) AS S
        ON T.ClienteId = S.ClienteId
        WHEN MATCHED THEN
            UPDATE SET
                T.Nome = S.Nome,
                T.RazaoSocial = ISNULL(S.RazaoSocial, T.RazaoSocial),
                T.TipoPessoa = 2
        WHEN NOT MATCHED THEN
            INSERT (ClienteId, Nome, RazaoSocial, TipoPessoa, Ativo)
            VALUES (S.ClienteId, S.Nome, S.RazaoSocial, S.TipoPessoa, S.Ativo);

        /* --------------------------------------------------------------------
           3b. Atualiza Dim_Cliente (extraído de $.clients, vinculando EmpresaId)
        -------------------------------------------------------------------- */
        MERGE core.Dim_Cliente AS T
        USING (
            SELECT
                c.id AS ClienteId,
                MAX(ISNULL(c.businessName, N'Sem Nome')) AS Nome,
                MAX(c.corporateName) AS RazaoSocial,
                MAX(c.personType) AS TipoPessoa,
                MAX(c.orgId) AS EmpresaId,
                1 AS Ativo
            FROM #Pendentes p
            CROSS APPLY OPENJSON(p.Payload, '$.clients') WITH (
                id            VARCHAR(64)   '$.id',
                businessName  NVARCHAR(256) '$.businessName',
                corporateName NVARCHAR(256) '$.corporateName',
                personType    TINYINT       '$.personType',
                orgId         VARCHAR(64)   '$.organization.id'
            ) c
            WHERE c.id IS NOT NULL
            GROUP BY c.id
        ) AS S
        ON T.ClienteId = S.ClienteId
        WHEN MATCHED THEN
            UPDATE SET
                T.Nome = S.Nome,
                T.RazaoSocial = ISNULL(S.RazaoSocial, T.RazaoSocial),
                T.TipoPessoa = ISNULL(S.TipoPessoa, T.TipoPessoa),
                T.EmpresaId = ISNULL(S.EmpresaId, T.EmpresaId)
        WHEN NOT MATCHED THEN
            INSERT (ClienteId, Nome, RazaoSocial, TipoPessoa, EmpresaId, Ativo)
            VALUES (S.ClienteId, S.Nome, S.RazaoSocial, S.TipoPessoa, S.EmpresaId, S.Ativo);

        /* --------------------------------------------------------------------
           3c. Atualiza core.Fato_TicketCliente (Ponte N:N Ticket <-> Cliente/Empresa)
        -------------------------------------------------------------------- */
        DELETE tc
        FROM core.Fato_TicketCliente tc
        INNER JOIN #Pendentes p ON tc.TicketId = p.TicketId;

        INSERT INTO core.Fato_TicketCliente (TicketId, ClienteId, EmpresaId)
        SELECT
            p.TicketId,
            c.id AS ClienteId,
            MAX(ISNULL(c.orgId, CASE WHEN c.personType IN (2, 4) THEN c.id ELSE dc.EmpresaId END)) AS EmpresaId
        FROM #Pendentes p
        CROSS APPLY OPENJSON(p.Payload, '$.clients') WITH (
            id         VARCHAR(64) '$.id',
            personType TINYINT     '$.personType',
            orgId      VARCHAR(64) '$.organization.id'
        ) c
        LEFT JOIN core.Dim_Cliente dc ON c.id = dc.ClienteId
        WHERE c.id IS NOT NULL
        GROUP BY p.TicketId, c.id;

        /* --------------------------------------------------------------------
           4. Atualiza core.Fato_Ticket
              - Datas convertidas de UTC -> Horário de Brasília
              - EmpresaId prioriza a Organização (Empresa) em vez da Pessoa Física
              - Persiste CriadoPorId e Tags
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
                cli.EmpresaPrincipalId AS EmpresaId,
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
                SELECT TOP 1
                    ISNULL(
                        c.orgId,
                        CASE
                            WHEN c.personType IN (2, 4) THEN c.id
                            ELSE ISNULL(dc.EmpresaId, c.id)
                        END
                    ) AS EmpresaPrincipalId
                FROM OPENJSON(p.Payload, '$.clients') WITH (
                    id         VARCHAR(64) '$.id',
                    personType TINYINT     '$.personType',
                    orgId      VARCHAR(64) '$.organization.id'
                ) c
                LEFT JOIN core.Dim_Cliente dc ON c.id = dc.ClienteId
                WHERE c.id IS NOT NULL
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

        /* --------------------------------------------------------------------
           5. Atualiza core.Fato_StatusHistorico
              Converte DataInicio para Horário de Brasília e preenche DataFim via LEAD()
        -------------------------------------------------------------------- */
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

        /* --------------------------------------------------------------------
           7. Atualiza core.Fato_SnapshotBacklog
              Reconstrói os 90 dias se a tabela estiver vazia ou no último lote parcial
        -------------------------------------------------------------------- */
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
