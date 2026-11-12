/* =============================================================================
   01 - Schemas e tabelas do Data Mart
   -----------------------------------------------------------------------------
   raw  : JSON bruto, exatamente como vem da API (ou do gerador fictício)
   core : fatos e dimensões normalizados  (datas em horário de Brasília)
   mart : views consumidas pelo Superset (script 03)
   ctl  : controle de cargas, marca d'água e parâmetros
   sec  : mapeamento usuário -> equipe (Row Level Security no Superset)
   Script idempotente: pode ser executado várias vezes.
   ============================================================================= */

IF SCHEMA_ID(N'raw')  IS NULL EXEC (N'CREATE SCHEMA raw');
IF SCHEMA_ID(N'core') IS NULL EXEC (N'CREATE SCHEMA core');
IF SCHEMA_ID(N'mart') IS NULL EXEC (N'CREATE SCHEMA mart');
IF SCHEMA_ID(N'ctl')  IS NULL EXEC (N'CREATE SCHEMA ctl');
IF SCHEMA_ID(N'sec')  IS NULL EXEC (N'CREATE SCHEMA sec');
GO

/* ----------------------------------------------------------------------------
   RAW
---------------------------------------------------------------------------- */
IF OBJECT_ID(N'raw.Ticket') IS NULL
CREATE TABLE raw.Ticket (
    TicketId        INT             NOT NULL CONSTRAINT PK_raw_Ticket PRIMARY KEY,
    LastUpdateUtc   DATETIME2(3)    NULL,
    Payload         NVARCHAR(MAX)   NOT NULL,
    Fonte           VARCHAR(20)     NOT NULL,      -- 'API' | 'FICTICIO'
    CarregadoEm     DATETIME2(0)    NOT NULL CONSTRAINT DF_raw_Ticket_CarregadoEm DEFAULT SYSDATETIME(),
    Processado      BIT             NOT NULL CONSTRAINT DF_raw_Ticket_Processado DEFAULT 0
);
GO
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'IX_raw_Ticket_Processado')
    CREATE INDEX IX_raw_Ticket_Processado ON raw.Ticket (Processado) INCLUDE (TicketId);
GO

-- Área de pouso para SqlBulkCopy (é truncada a cada lote)
IF OBJECT_ID(N'raw.Ticket_Stage') IS NULL
CREATE TABLE raw.Ticket_Stage (
    TicketId        INT             NOT NULL,
    LastUpdateUtc   DATETIME2(3)    NULL,
    Payload         NVARCHAR(MAX)   NOT NULL,
    Fonte           VARCHAR(20)     NOT NULL
);
GO

IF OBJECT_ID(N'raw.Pessoa') IS NULL
CREATE TABLE raw.Pessoa (
    PessoaId        VARCHAR(64)     NOT NULL CONSTRAINT PK_raw_Pessoa PRIMARY KEY,
    Payload         NVARCHAR(MAX)   NOT NULL,
    Fonte           VARCHAR(20)     NOT NULL,
    CarregadoEm     DATETIME2(0)    NOT NULL CONSTRAINT DF_raw_Pessoa_CarregadoEm DEFAULT SYSDATETIME(),
    Processado      BIT             NOT NULL CONSTRAINT DF_raw_Pessoa_Processado DEFAULT 0
);
GO

IF OBJECT_ID(N'raw.Pessoa_Stage') IS NULL
CREATE TABLE raw.Pessoa_Stage (
    PessoaId        VARCHAR(64)     NOT NULL,
    Payload         NVARCHAR(MAX)   NOT NULL,
    Fonte           VARCHAR(20)     NOT NULL
);
GO

/* ----------------------------------------------------------------------------
   CTL
---------------------------------------------------------------------------- */
IF OBJECT_ID(N'ctl.ExecucaoCarga') IS NULL
CREATE TABLE ctl.ExecucaoCarga (
    ExecucaoId      INT IDENTITY    NOT NULL CONSTRAINT PK_ctl_ExecucaoCarga PRIMARY KEY,
    Tipo            VARCHAR(40)     NOT NULL,
    Inicio          DATETIME2(0)    NOT NULL CONSTRAINT DF_ctl_ExecucaoCarga_Inicio DEFAULT SYSDATETIME(),
    Fim             DATETIME2(0)    NULL,
    Status          VARCHAR(20)     NOT NULL CONSTRAINT DF_ctl_ExecucaoCarga_Status DEFAULT 'EXECUTANDO',
    QtdRegistros    INT             NULL,
    Mensagem        NVARCHAR(4000)  NULL
);
GO

IF OBJECT_ID(N'ctl.MarcaDagua') IS NULL
CREATE TABLE ctl.MarcaDagua (
    Entidade        VARCHAR(40)     NOT NULL CONSTRAINT PK_ctl_MarcaDagua PRIMARY KEY,
    UltimoValorUtc  DATETIME2(3)    NULL,
    AtualizadoEm    DATETIME2(0)    NOT NULL CONSTRAINT DF_ctl_MarcaDagua_AtualizadoEm DEFAULT SYSDATETIME()
);
GO

IF OBJECT_ID(N'ctl.Parametro') IS NULL
CREATE TABLE ctl.Parametro (
    Chave           VARCHAR(60)     NOT NULL CONSTRAINT PK_ctl_Parametro PRIMARY KEY,
    Valor           NVARCHAR(400)   NOT NULL,
    Descricao       NVARCHAR(400)   NULL
);
GO

/* ----------------------------------------------------------------------------
   CORE - Dimensões
---------------------------------------------------------------------------- */
IF OBJECT_ID(N'core.Dim_Calendario') IS NULL
CREATE TABLE core.Dim_Calendario (
    Data            DATE            NOT NULL CONSTRAINT PK_core_Dim_Calendario PRIMARY KEY,
    Ano             SMALLINT        NOT NULL,
    Trimestre       TINYINT         NOT NULL,
    Mes             TINYINT         NOT NULL,
    NomeMes         NVARCHAR(20)    NOT NULL,
    AnoMes          CHAR(7)         NOT NULL,      -- 2026-11
    Semana          TINYINT         NOT NULL,
    DiaSemana       TINYINT         NOT NULL,      -- 1 = domingo ... 7 = sábado
    NomeDiaSemana   NVARCHAR(20)    NOT NULL,
    EhFimDeSemana   BIT             NOT NULL,
    EhFeriado       BIT             NOT NULL,
    NomeFeriado     NVARCHAR(60)    NULL,
    EhDiaUtil       BIT             NOT NULL
);
GO

IF OBJECT_ID(N'core.Dim_Status') IS NULL
CREATE TABLE core.Dim_Status (
    StatusId                INT IDENTITY    NOT NULL CONSTRAINT PK_core_Dim_Status PRIMARY KEY,
    Nome                    NVARCHAR(128)   NOT NULL CONSTRAINT UQ_core_Dim_Status_Nome UNIQUE,
    GrupoStatus             NVARCHAR(60)    NOT NULL,
    OrdemFluxo              TINYINT         NOT NULL,
    PausaSla                BIT             NOT NULL,
    EhDependenciaTerceiro   BIT             NOT NULL,
    EhFinal                 BIT             NOT NULL,
    Cor                     CHAR(7)         NULL,
    Mapeado                 BIT             NOT NULL CONSTRAINT DF_core_Dim_Status_Mapeado DEFAULT 1
);
GO

IF OBJECT_ID(N'core.Dim_Equipe') IS NULL
CREATE TABLE core.Dim_Equipe (
    EquipeId        INT IDENTITY    NOT NULL CONSTRAINT PK_core_Dim_Equipe PRIMARY KEY,
    Nome            NVARCHAR(128)   NOT NULL CONSTRAINT UQ_core_Dim_Equipe_Nome UNIQUE,
    EhSuporte       BIT             NOT NULL CONSTRAINT DF_core_Dim_Equipe_EhSuporte DEFAULT 1
);
GO

IF OBJECT_ID(N'core.Dim_Agente') IS NULL
CREATE TABLE core.Dim_Agente (
    AgenteId        VARCHAR(64)     NOT NULL CONSTRAINT PK_core_Dim_Agente PRIMARY KEY,  -- id da pessoa no Movidesk
    Nome            NVARCHAR(256)   NOT NULL,
    Email           NVARCHAR(256)   NULL,
    Ativo           BIT             NOT NULL CONSTRAINT DF_core_Dim_Agente_Ativo DEFAULT 1
);
GO

IF OBJECT_ID(N'core.Dim_Cliente') IS NULL
CREATE TABLE core.Dim_Cliente (
    ClienteId       VARCHAR(64)     NOT NULL CONSTRAINT PK_core_Dim_Cliente PRIMARY KEY,  -- id da pessoa/empresa no Movidesk
    Nome            NVARCHAR(256)   NOT NULL,
    RazaoSocial     NVARCHAR(256)   NULL,
    TipoPessoa      TINYINT         NULL,          -- 1 Pessoa | 2 Empresa | 4 Departamento
    EmpresaId       VARCHAR(64)     NULL,          -- organização à qual o contato pertence
    Ativo           BIT             NULL,
    DataCadastro    DATETIME2(0)    NULL
);
GO
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'IX_core_Dim_Cliente_Tipo')
    CREATE INDEX IX_core_Dim_Cliente_Tipo ON core.Dim_Cliente (TipoPessoa) INCLUDE (Nome, Ativo);
GO

IF OBJECT_ID(N'core.Dim_CampoCustomizado') IS NULL
CREATE TABLE core.Dim_CampoCustomizado (
    CampoId         INT             NOT NULL CONSTRAINT PK_core_Dim_CampoCustomizado PRIMARY KEY,
    Nome            NVARCHAR(128)   NOT NULL,
    Descricao       NVARCHAR(400)   NULL
);
GO

/* ----------------------------------------------------------------------------
   CORE - Fatos
---------------------------------------------------------------------------- */
IF OBJECT_ID(N'core.Fato_Ticket') IS NULL
CREATE TABLE core.Fato_Ticket (
    TicketId                    INT             NOT NULL CONSTRAINT PK_core_Fato_Ticket PRIMARY KEY,
    Protocolo                   NVARCHAR(64)    NULL,
    Tipo                        TINYINT         NULL,      -- 1 Interno | 2 Público
    Assunto                     NVARCHAR(400)   NULL,
    Categoria                   NVARCHAR(128)   NULL,
    Urgencia                    NVARCHAR(128)   NULL,
    Status                      NVARCHAR(128)   NULL,
    StatusBase                  NVARCHAR(40)    NULL,
    Justificativa               NVARCHAR(256)   NULL,
    Origem                      SMALLINT        NULL,
    Equipe                      NVARCHAR(128)   NULL,
    AgenteId                    VARCHAR(64)     NULL,
    CriadoPorId                 VARCHAR(64)     NULL,
    EmpresaId                   VARCHAR(64)     NULL,      -- empresa principal (1º cliente)
    ServicoN1                   NVARCHAR(256)   NULL,
    ServicoN2                   NVARCHAR(256)   NULL,
    ServicoN3                   NVARCHAR(256)   NULL,
    Tags                        NVARCHAR(1000)  NULL,
    DataCriacao                 DATETIME2(0)    NULL,
    DataUltimaAtualizacao       DATETIME2(0)    NULL,
    DataUltimaAcao              DATETIME2(0)    NULL,
    DataResolucao               DATETIME2(0)    NULL,
    DataFechamento              DATETIME2(0)    NULL,
    DataReabertura              DATETIME2(0)    NULL,
    QtdAcoes                    INT             NULL,
    SlaAcordo                   NVARCHAR(256)   NULL,
    SlaRegra                    NVARCHAR(256)   NULL,
    SlaTempoSolucaoMin          INT             NULL,
    SlaTempoRespostaMin         INT             NULL,
    SlaDataSolucao              DATETIME2(0)    NULL,
    SlaSolucaoPausado           BIT             NULL,
    SlaDataResposta             DATETIME2(0)    NULL,
    SlaDataRespostaReal         DATETIME2(0)    NULL,
    ResolvidoPrimeiroContato    BIT             NULL,
    -- Derivados (calculados em core.usp_ProcessarTickets)
    TicketPaiId                 INT             NULL,
    QtdTicketsFilhos            INT             NULL,
    DataPrimeiraAcaoAgente      DATETIME2(0)    NULL,
    DataUltimaAcaoAgente        DATETIME2(0)    NULL,
    DataUltimaAcaoCliente       DATETIME2(0)    NULL,
    QtdAcoesPublicasAgente      INT             NULL,
    QtdReaberturas              INT             NULL,
    QtdTrocasEquipe             INT             NULL,
    AtualizadoEm                DATETIME2(0)    NOT NULL CONSTRAINT DF_core_Fato_Ticket_AtualizadoEm DEFAULT SYSDATETIME()
);
GO
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'IX_core_Fato_Ticket_StatusBase')
    CREATE INDEX IX_core_Fato_Ticket_StatusBase ON core.Fato_Ticket (StatusBase, Equipe, AgenteId) INCLUDE (SlaDataSolucao, DataCriacao, Urgencia, Status);
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'IX_core_Fato_Ticket_DataCriacao')
    CREATE INDEX IX_core_Fato_Ticket_DataCriacao ON core.Fato_Ticket (DataCriacao) INCLUDE (Equipe, AgenteId, EmpresaId);
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'IX_core_Fato_Ticket_DataResolucao')
    CREATE INDEX IX_core_Fato_Ticket_DataResolucao ON core.Fato_Ticket (DataResolucao) INCLUDE (Equipe, AgenteId);
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'IX_core_Fato_Ticket_Empresa')
    CREATE INDEX IX_core_Fato_Ticket_Empresa ON core.Fato_Ticket (EmpresaId, DataCriacao);
GO

IF OBJECT_ID(N'core.Fato_TicketCliente') IS NULL
CREATE TABLE core.Fato_TicketCliente (
    TicketId        INT             NOT NULL,
    ClienteId       VARCHAR(64)     NOT NULL,
    EmpresaId       VARCHAR(64)     NULL,
    CONSTRAINT PK_core_Fato_TicketCliente PRIMARY KEY (TicketId, ClienteId)
);
GO

IF OBJECT_ID(N'core.Fato_Acao') IS NULL
CREATE TABLE core.Fato_Acao (
    TicketId        INT             NOT NULL,
    AcaoId          INT             NOT NULL,
    Tipo            TINYINT         NULL,      -- 1 Interna | 2 Pública
    Origem          SMALLINT        NULL,
    Status          NVARCHAR(128)   NULL,
    DataCriacao     DATETIME2(0)    NULL,
    CriadoPorId     VARCHAR(64)     NULL,
    CriadoPorPerfil TINYINT         NULL,      -- 1 Agente | 2 Cliente | 3 Agente e Cliente
    EhAgente        BIT             NOT NULL,
    Deletada        BIT             NOT NULL,
    CONSTRAINT PK_core_Fato_Acao PRIMARY KEY (TicketId, AcaoId)
);
GO

IF OBJECT_ID(N'core.Fato_StatusHistorico') IS NULL
CREATE TABLE core.Fato_StatusHistorico (
    TicketId                INT             NOT NULL,
    Sequencia               INT             NOT NULL,
    Status                  NVARCHAR(128)   NOT NULL,
    Justificativa           NVARCHAR(256)   NULL,
    DataInicio              DATETIME2(0)    NOT NULL,
    DataFim                 DATETIME2(0)    NULL,      -- NULL = status atual
    PermanenciaMinCorridos  INT             NULL,
    PermanenciaMinUteis     INT             NULL,
    AlteradoPorId           VARCHAR(64)     NULL,
    CONSTRAINT PK_core_Fato_StatusHistorico PRIMARY KEY (TicketId, Sequencia)
);
GO
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'IX_core_Fato_StatusHistorico_Periodo')
    CREATE INDEX IX_core_Fato_StatusHistorico_Periodo ON core.Fato_StatusHistorico (DataInicio, DataFim) INCLUDE (Status);
GO

IF OBJECT_ID(N'core.Fato_ResponsavelHistorico') IS NULL
CREATE TABLE core.Fato_ResponsavelHistorico (
    TicketId                INT             NOT NULL,
    Sequencia               INT             NOT NULL,
    Equipe                  NVARCHAR(128)   NULL,
    AgenteId                VARCHAR(64)     NULL,
    DataInicio              DATETIME2(0)    NOT NULL,
    DataFim                 DATETIME2(0)    NULL,
    PermanenciaMinCorridos  INT             NULL,
    AlteradoPorId           VARCHAR(64)     NULL,
    CONSTRAINT PK_core_Fato_ResponsavelHistorico PRIMARY KEY (TicketId, Sequencia)
);
GO

IF OBJECT_ID(N'core.Fato_CampoCustomizado') IS NULL
CREATE TABLE core.Fato_CampoCustomizado (
    TicketId        INT             NOT NULL,
    CampoId         INT             NOT NULL,
    Linha           INT             NOT NULL,
    Valor           NVARCHAR(1000)  NULL,
    CONSTRAINT PK_core_Fato_CampoCustomizado PRIMARY KEY (TicketId, CampoId, Linha)
);
GO

IF OBJECT_ID(N'core.Fato_TicketRelacao') IS NULL
CREATE TABLE core.Fato_TicketRelacao (
    TicketPaiId     INT             NOT NULL,
    TicketFilhoId   INT             NOT NULL,
    CONSTRAINT PK_core_Fato_TicketRelacao PRIMARY KEY (TicketPaiId, TicketFilhoId)
);
GO

-- Foto diária do backlog (reconstruída a partir do histórico de status + gravada diariamente)
IF OBJECT_ID(N'core.Fato_SnapshotBacklog') IS NULL
CREATE TABLE core.Fato_SnapshotBacklog (
    DataSnapshot    DATE            NOT NULL,
    Equipe          NVARCHAR(128)   NOT NULL,
    AgenteId        VARCHAR(64)     NOT NULL,
    Status          NVARCHAR(128)   NOT NULL,
    Urgencia        NVARCHAR(128)   NOT NULL,
    QtdTickets      INT             NOT NULL,
    QtdSlaVencido   INT             NOT NULL,
    CONSTRAINT PK_core_Fato_SnapshotBacklog PRIMARY KEY (DataSnapshot, Equipe, AgenteId, Status, Urgencia)
);
GO

/* ----------------------------------------------------------------------------
   SEC - base para Row Level Security no Superset
---------------------------------------------------------------------------- */
IF OBJECT_ID(N'sec.UsuarioEquipe') IS NULL
CREATE TABLE sec.UsuarioEquipe (
    UsuarioSuperset NVARCHAR(128)   NOT NULL,
    Equipe          NVARCHAR(128)   NOT NULL,
    CONSTRAINT PK_sec_UsuarioEquipe PRIMARY KEY (UsuarioSuperset, Equipe)
);
GO
