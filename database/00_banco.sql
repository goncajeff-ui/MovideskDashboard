/* =============================================================================
   00 - Criação do banco (executado no contexto do [master])
   ============================================================================= */
IF DB_ID(N'MovideskDM') IS NULL
BEGIN
    CREATE DATABASE [MovideskDM];
END
GO

ALTER DATABASE [MovideskDM] SET RECOVERY SIMPLE;
GO

-- OPENJSON exige nível de compatibilidade >= 130 (SQL Server 2016+)
IF (SELECT compatibility_level FROM sys.databases WHERE name = N'MovideskDM') < 130
    ALTER DATABASE [MovideskDM] SET COMPATIBILITY_LEVEL = 140;
GO
