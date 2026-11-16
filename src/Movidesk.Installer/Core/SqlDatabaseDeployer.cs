using System.Diagnostics;
using System.Reflection;
using System.Runtime.Versioning;
using System.Text;
using System.Text.RegularExpressions;
using Microsoft.Data.SqlClient;
using Microsoft.Win32;

namespace Movidesk.Installer.Core;

/// <summary>
/// Executa o provisionamento nativo do SQL Server (MovideskDM) diretamente em C#
/// (sem depender de sqlcmd, SSMS ou utilitários externos).
/// Conecta via ADO.NET (Microsoft.Data.SqlClient), garante Mixed Mode (LoginMode = 2)
/// e o login SQL dedicado 'superset_bi' para o Apache Superset, cria o banco se não existir
/// e processa todos os scripts SQL embutidos dividindo por lotes 'GO'.
/// </summary>
public sealed class SqlDatabaseDeployer
{
    private const string PrefixSqlResource = "Movidesk.Installer.Sql.";
    private static readonly Assembly AssemblyAtual = typeof(SqlDatabaseDeployer).Assembly;

    public static bool EhHostLocal(string? rawHost)
    {
        if (string.IsNullOrWhiteSpace(rawHost))
        {
            return true;
        }

        string trimmed = rawHost.Trim();
        string hostSemPorta = trimmed.Split(',')[0].Trim();
        return hostSemPorta.Equals("localhost", StringComparison.OrdinalIgnoreCase)
            || hostSemPorta.Equals("127.0.0.1", StringComparison.OrdinalIgnoreCase)
            || hostSemPorta.Equals(".", StringComparison.OrdinalIgnoreCase)
            || hostSemPorta.Equals("(local)", StringComparison.OrdinalIgnoreCase)
            || hostSemPorta.StartsWith("localhost\\", StringComparison.OrdinalIgnoreCase)
            || hostSemPorta.StartsWith(".\\", StringComparison.OrdinalIgnoreCase)
            || hostSemPorta.StartsWith("127.0.0.1\\", StringComparison.OrdinalIgnoreCase)
            || hostSemPorta.StartsWith("(local)\\", StringComparison.OrdinalIgnoreCase);
    }

    public static string ConstruirConnectionString(string host, string banco, string? usuario, string? senha)
    {
        var builder = new SqlConnectionStringBuilder
        {
            DataSource = string.IsNullOrWhiteSpace(host) ? "localhost" : host.Trim(),
            InitialCatalog = string.IsNullOrWhiteSpace(banco) ? "MovideskDM" : banco.Trim(),
            TrustServerCertificate = true,
            MultipleActiveResultSets = true,
            ConnectTimeout = 15
        };

        if (string.IsNullOrWhiteSpace(usuario))
        {
            builder.IntegratedSecurity = true;
        }
        else
        {
            builder.UserID = usuario.Trim();
            builder.Password = senha ?? string.Empty;
        }

        return builder.ConnectionString;
    }

    public async Task<bool> GarantirBancoEExecutarScriptsAsync(
        ConfiguracaoInstalacao config,
        AuditorLog log,
        CancellationToken ct)
    {
        string host = string.IsNullOrWhiteSpace(config.SqlServerHost) ? "localhost" : config.SqlServerHost.Trim();
        string banco = string.IsNullOrWhiteSpace(config.SqlServerBanco) ? "MovideskDM" : config.SqlServerBanco.Trim();
        string bancoEscapado = EscaparIdentificadorSql(banco);
        string user = config.SqlServerUsuario?.Trim() ?? string.Empty;
        string pass = config.SqlServerSenha ?? string.Empty;
        bool ehLocal = EhHostLocal(host);
        bool usarWindowsAuth = string.IsNullOrWhiteSpace(user);
        config.UsouAutenticacaoWindows = usarWindowsAuth;

        log.Aguardando(usarWindowsAuth
            ? $"Conectando nativamente ao SQL Server em '{host}' via Autenticação Windows (Microsoft.Data.SqlClient)..."
            : $"Conectando nativamente ao SQL Server em '{host}' como '{user}' via C# (Microsoft.Data.SqlClient)...");

        // 1. Conecta no banco de sistema 'master' (com fallback automático para Windows Auth em host local)
        SqlConnection? connMaster = null;
        bool servicoReiniciado = false;

        try
        {
            string connStrMaster = ConstruirConnectionString(host, "master", usarWindowsAuth ? string.Empty : user, pass);
            try
            {
                connMaster = new SqlConnection(connStrMaster);
                await connMaster.OpenAsync(ct);
                log.Sucesso(usarWindowsAuth
                    ? $"Conectado com sucesso ao SQL Server '{host}' (Autenticação Integrada do Windows)."
                    : $"Conectado com sucesso ao SQL Server '{host}' (usuário SQL '{user}').");
            }
            catch (SqlException sqlEx) when (!usarWindowsAuth && ehLocal)
            {
                if (connMaster is not null)
                {
                    await connMaster.DisposeAsync();
                    connMaster = null;
                }

                log.Aviso($"Autenticação SQL com usuário '{user}' falhou ({sqlEx.Message}). Tentando fallback automático via Autenticação Integrada do Windows...");
                string connStrWin = ConstruirConnectionString(host, "master", string.Empty, string.Empty);
                connMaster = new SqlConnection(connStrWin);
                await connMaster.OpenAsync(ct);
                usarWindowsAuth = true;
                config.UsouAutenticacaoWindows = true;
                log.Sucesso($"Conectado com sucesso ao SQL Server '{host}' via Autenticação Integrada do Windows!");
            }

            // 1a. Garante existência do banco MovideskDM
            await using (var cmdCheck = new SqlCommand(
                "SELECT COUNT(1) FROM sys.databases WHERE name = @nomeBanco;", connMaster))
            {
                cmdCheck.Parameters.AddWithValue("@nomeBanco", banco);
                int countDb = Convert.ToInt32(await cmdCheck.ExecuteScalarAsync(ct));

                if (countDb > 0)
                {
                    log.Info($"Banco de dados '[{banco}]' já existe no SQL Server.");
                }
                else
                {
                    log.Aguardando($"Criando banco de dados '[{banco}]' no SQL Server (RECOVERY SIMPLE)...");
                    await using var cmdCreate = new SqlCommand(
                        $"CREATE DATABASE [{bancoEscapado}]; ALTER DATABASE [{bancoEscapado}] SET RECOVERY SIMPLE;", connMaster);
                    await cmdCreate.ExecuteNonQueryAsync(ct);
                    log.Sucesso($"Banco de dados '[{banco}]' criado com sucesso!");
                }
            }

            // 1b. Inspeciona modo de autenticação (Windows Auth Only vs Mixed Mode) e nome da instância
            bool apenasWindowsAuth = false;
            string sqlInstanceName = "MSSQLSERVER";
            try
            {
                await using var cmdMode = new SqlCommand(
                    "SELECT CONVERT(INT, ISNULL(SERVERPROPERTY('IsIntegratedSecurityOnly'), 0)), CONVERT(NVARCHAR(128), ISNULL(@@SERVICENAME, N'MSSQLSERVER'));",
                    connMaster);
                await using var reader = await cmdMode.ExecuteReaderAsync(ct);
                if (await reader.ReadAsync(ct))
                {
                    apenasWindowsAuth = !reader.IsDBNull(0) && reader.GetInt32(0) == 1;
                    if (!reader.IsDBNull(1) && !string.IsNullOrWhiteSpace(reader.GetString(1)))
                    {
                        sqlInstanceName = reader.GetString(1).Trim();
                    }
                }
            }
            catch (Exception modeEx)
            {
                log.Aviso($"Aviso ao consultar SERVERPROPERTY('IsIntegratedSecurityOnly'): {modeEx.Message}");
            }

            // 1c. Garante Login SQL dedicado 'superset_bi' com senha fixa forte (obrigatório para pymssql no Docker)
            await GarantirLoginSupersetServidorAsync(connMaster, bancoEscapado, log, ct);

            // 1d. Caso SQL Server esteja em Windows Auth Only (LoginMode = 1), habilita Mixed Mode (LoginMode = 2) e reinicia serviço local
            if (apenasWindowsAuth)
            {
                log.Aviso(
                    $"SQL Server '{host}' está operando apenas em Autenticação Windows (IsIntegratedSecurityOnly = 1). " +
                    "O driver pymssql em contêiner Linux exige Mixed Mode Authentication (LoginMode = 2). Habilitando automaticamente...");

                bool mixedModeAtualizado = false;
                try
                {
                    await using var cmdRegWrite = new SqlCommand(
                        "EXEC sys.xp_instance_regwrite N'HKEY_LOCAL_MACHINE', N'Software\\Microsoft\\MSSQLServer\\MSSQLServer', N'LoginMode', REG_DWORD, 2;",
                        connMaster);
                    await cmdRegWrite.ExecuteNonQueryAsync(ct);
                    mixedModeAtualizado = true;
                    log.Sucesso("Mixed Mode Authentication (LoginMode = 2) gravado via xp_instance_regwrite no SQL Server.");
                }
                catch (Exception xpEx)
                {
                    log.Aviso($"xp_instance_regwrite não pôde alterar LoginMode ({xpEx.Message}); tentando via Registro do Windows...");
                }

                if (ehLocal && OperatingSystem.IsWindows())
                {
                    bool regOk = TentarHabilitarMixedModeRegistro(sqlInstanceName, log);
                    mixedModeAtualizado = mixedModeAtualizado || regOk;
                }

                if (mixedModeAtualizado && ehLocal && !sqlInstanceName.StartsWith("LOCALDB#", StringComparison.OrdinalIgnoreCase))
                {
                    await connMaster.DisposeAsync();
                    connMaster = null;
                    SqlConnection.ClearAllPools();

                    string serviceName = sqlInstanceName.Equals("MSSQLSERVER", StringComparison.OrdinalIgnoreCase)
                        ? "MSSQLSERVER"
                        : $"MSSQL${sqlInstanceName}";

                    servicoReiniciado = await ReiniciarServicoSqlLocalAsync(serviceName, log, ct);
                }
                else if (mixedModeAtualizado)
                {
                    log.Aviso(
                        $"Mixed Mode gravado para instância remota/local '{host}'. Caso o login SQL 'superset_bi' ainda seja recusado na Etapa 4, reinicie o serviço do SQL Server.");
                }
            }
        }
        catch (Exception ex)
        {
            log.Aviso(
                $"Não foi possível conectar ao SQL Server em '{host}' para provisionar o banco '{banco}': {ex.Message}\n" +
                $"Os scripts SQL foram salvos em '{Path.Combine(config.DiretorioInstalacao, "database")}'. " +
                "Você poderá executar os scripts ou usar o 'Painel Movidesk BI' após ajustar o SQL Server.");
            return false;
        }
        finally
        {
            if (connMaster is not null)
            {
                await connMaster.DisposeAsync();
            }
        }

        // 2. Conecta no banco alvo (MovideskDM) para aplicar tabelas, visões, procedimentos e garantir db_owner para superset_bi
        string connStrBanco = ConstruirConnectionString(host, banco, usarWindowsAuth ? string.Empty : user, pass);
        try
        {
            await using SqlConnection connBanco = await AbrirConexaoComRetentativaAsync(
                connStrBanco,
                servicoReiniciado ? 6 : 2,
                log,
                ct);

            // Carrega todos os scripts SQL embutidos no assembly ordenados numericamente (01_*, 02_*, etc.)
            var recursosSql = AssemblyAtual.GetManifestResourceNames()
                .Where(r => r.StartsWith(PrefixSqlResource, StringComparison.OrdinalIgnoreCase) && r.EndsWith(".sql", StringComparison.OrdinalIgnoreCase))
                .OrderBy(r => r, StringComparer.OrdinalIgnoreCase)
                .ToList();

            // 00_banco.sql não precisa ser executado dentro do próprio MovideskDM (já garantido no master)
            recursosSql.RemoveAll(r => r.EndsWith("00_banco.sql", StringComparison.OrdinalIgnoreCase));

            log.Aguardando($"Aplicando {recursosSql.Count} scripts SQL oficiais no banco '[{banco}]' via C#...");

            foreach (string recurso in recursosSql)
            {
                string nomeArquivo = recurso[PrefixSqlResource.Length..];
                await ExecutarScriptRecursoAsync(connBanco, recurso, nomeArquivo, log, ct);
            }

            await GarantirPermissaoSupersetNoBancoAsync(connBanco, banco, log, ct);

            log.Sucesso($"Estrutura completa do Data Mart '[{banco}]' (schemas, tabelas, 3 covering indexes e 9 views mart.*) implantada com sucesso!");
        }
        catch (Exception ex)
        {
            log.Aviso($"Aviso durante a aplicação dos scripts SQL no banco '{banco}': {ex.Message}");
            return false;
        }

        // 3. Valida conexão direta com o login SQL dedicado 'superset_bi' para confirmar Mixed Mode operacional antes do Docker
        await ValidarLoginDedicadoSupersetAsync(host, banco, log, ct);
        return true;
    }

    private static async Task GarantirLoginSupersetServidorAsync(
        SqlConnection connMaster,
        string bancoEscapado,
        AuditorLog log,
        CancellationToken ct)
    {
        const string loginNome = ConfiguracaoInstalacao.SupersetSqlLoginPadrao;
        const string loginSenha = ConfiguracaoInstalacao.SupersetSqlSenhaPadrao;

        string loginIdent = EscaparIdentificadorSql(loginNome);
        string loginLiteral = EscaparLiteralSql(loginNome);
        string senhaLiteral = EscaparLiteralSql(loginSenha);

        try
        {
            string sqlLogin = $"""
                IF SUSER_ID(N'{loginLiteral}') IS NULL
                BEGIN
                    CREATE LOGIN [{loginIdent}]
                        WITH PASSWORD = N'{senhaLiteral}',
                        CHECK_POLICY = OFF,
                        CHECK_EXPIRATION = OFF,
                        DEFAULT_DATABASE = [{bancoEscapado}];
                END
                ELSE
                BEGIN
                    ALTER LOGIN [{loginIdent}]
                        WITH PASSWORD = N'{senhaLiteral}',
                        CHECK_POLICY = OFF,
                        CHECK_EXPIRATION = OFF,
                        DEFAULT_DATABASE = [{bancoEscapado}];
                    ALTER LOGIN [{loginIdent}] ENABLE;
                END
                """;

            await using var cmdLogin = new SqlCommand(sqlLogin, connMaster) { CommandTimeout = 30 };
            await cmdLogin.ExecuteNonQueryAsync(ct);
            log.Sucesso($"Login SQL dedicado '[{loginNome}]' garantido/atualizado (ENABLE, CHECK_POLICY = OFF).");
        }
        catch (Exception ex)
        {
            log.Aviso($"Aviso ao criar/atualizar login SQL '[{loginNome}]': {ex.Message}");
            return;
        }

        try
        {
            string sqlSysAdmin = $"""
                IF ISNULL(IS_SRVROLEMEMBER(N'sysadmin', N'{loginLiteral}'), 0) = 0
                BEGIN
                    ALTER SERVER ROLE [sysadmin] ADD MEMBER [{loginIdent}];
                END
                """;

            await using var cmdRole = new SqlCommand(sqlSysAdmin, connMaster) { CommandTimeout = 30 };
            await cmdRole.ExecuteNonQueryAsync(ct);
            log.Info($"Permissão de servidor [sysadmin] confirmada para o login '[{loginNome}]'.");
        }
        catch (Exception roleEx)
        {
            log.Info($"Aviso: não foi possível adicionar '[{loginNome}]' à role [sysadmin] ({roleEx.Message}); será atribuída permissão db_owner em '[{bancoEscapado}]'.");
        }
    }

    private static async Task GarantirPermissaoSupersetNoBancoAsync(
        SqlConnection connBanco,
        string banco,
        AuditorLog log,
        CancellationToken ct)
    {
        const string loginNome = ConfiguracaoInstalacao.SupersetSqlLoginPadrao;
        string loginIdent = EscaparIdentificadorSql(loginNome);
        string loginLiteral = EscaparLiteralSql(loginNome);

        try
        {
            string sqlUser = $"""
                IF USER_ID(N'{loginLiteral}') IS NULL AND SUSER_ID(N'{loginLiteral}') IS NOT NULL
                BEGIN
                    CREATE USER [{loginIdent}] FOR LOGIN [{loginIdent}] WITH DEFAULT_SCHEMA = [dbo];
                END
                IF USER_ID(N'{loginLiteral}') IS NOT NULL AND ISNULL(IS_ROLEMEMBER(N'db_owner', N'{loginLiteral}'), 0) = 0
                BEGIN
                    ALTER ROLE [db_owner] ADD MEMBER [{loginIdent}];
                END
                """;

            await using var cmdUser = new SqlCommand(sqlUser, connBanco) { CommandTimeout = 30 };
            await cmdUser.ExecuteNonQueryAsync(ct);
            log.Sucesso($"Permissão [db_owner] no banco '[{banco}]' confirmada para '[{loginNome}]'.");
        }
        catch (Exception ex)
        {
            log.Aviso($"Aviso ao conceder [db_owner] no banco '[{banco}]' para '[{loginNome}]': {ex.Message}");
        }
    }

    private static async Task ValidarLoginDedicadoSupersetAsync(
        string host,
        string banco,
        AuditorLog log,
        CancellationToken ct)
    {
        try
        {
            string connStrSuperset = ConstruirConnectionString(
                host,
                banco,
                ConfiguracaoInstalacao.SupersetSqlLoginPadrao,
                ConfiguracaoInstalacao.SupersetSqlSenhaPadrao);

            await using var connTest = new SqlConnection(connStrSuperset);
            await connTest.OpenAsync(ct);
            await using var cmd = new SqlCommand("SELECT 1;", connTest);
            await cmd.ExecuteScalarAsync(ct);
            log.Sucesso($"Autenticação SQL do login '{ConfiguracaoInstalacao.SupersetSqlLoginPadrao}' no banco '[{banco}]' validada com sucesso!");
        }
        catch (Exception ex)
        {
            log.Aviso(
                $"Teste direto de autenticação SQL para '{ConfiguracaoInstalacao.SupersetSqlLoginPadrao}' retornou: {ex.Message}. " +
                "Caso a conexão pelo Superset falhe na Etapa 4, valide o Mixed Mode Authentication e TCP/IP no SQL Server Configuration Manager.");
        }
    }

    [SupportedOSPlatform("windows")]
    private static bool TentarHabilitarMixedModeRegistro(string sqlInstanceName, AuditorLog log)
    {
        try
        {
            foreach (RegistryView view in new[] { RegistryView.Registry64, RegistryView.Registry32 })
            {
                using RegistryKey hklm = RegistryKey.OpenBaseKey(RegistryHive.LocalMachine, view);
                using RegistryKey? instanceNamesKey = hklm.OpenSubKey(@"SOFTWARE\Microsoft\Microsoft SQL Server\Instance Names\SQL");
                string? instanceId = instanceNamesKey?.GetValue(sqlInstanceName) as string;
                if (string.IsNullOrWhiteSpace(instanceId))
                {
                    continue;
                }

                string mssqlServerPath = $@"SOFTWARE\Microsoft\Microsoft SQL Server\{instanceId}\MSSQLServer";
                using RegistryKey? mssqlServerKey = hklm.OpenSubKey(mssqlServerPath, writable: true);
                if (mssqlServerKey is null)
                {
                    continue;
                }

                mssqlServerKey.SetValue("LoginMode", 2, RegistryValueKind.DWord);
                log.Sucesso($@"Registro do Windows atualizado: HKLM\{mssqlServerPath}\LoginMode = 2 (Mixed Mode).");
                return true;
            }
        }
        catch (Exception ex)
        {
            log.Aviso($"Aviso ao atualizar Registro do Windows para Mixed Mode: {ex.Message}");
        }

        return false;
    }

    private static async Task<bool> ReiniciarServicoSqlLocalAsync(
        string serviceName,
        AuditorLog log,
        CancellationToken ct)
    {
        log.Aguardando($"Reiniciando serviço local do SQL Server ('{serviceName}') para ativar Mixed Mode Authentication...");

        try
        {
            string escapedService = serviceName.Replace("'", "''");
            var psi = new ProcessStartInfo
            {
                FileName = "powershell.exe",
                UseShellExecute = false,
                CreateNoWindow = true,
                RedirectStandardOutput = true,
                RedirectStandardError = true
            };
            psi.ArgumentList.Add("-NoProfile");
            psi.ArgumentList.Add("-NonInteractive");
            psi.ArgumentList.Add("-ExecutionPolicy");
            psi.ArgumentList.Add("Bypass");
            psi.ArgumentList.Add("-Command");
            psi.ArgumentList.Add($"Restart-Service -Name '{escapedService}' -Force -ErrorAction Stop");

            using var proc = new Process { StartInfo = psi };
            proc.Start();
            string stdout = await proc.StandardOutput.ReadToEndAsync(ct);
            string stderr = await proc.StandardError.ReadToEndAsync(ct);

            using var timeoutCts = CancellationTokenSource.CreateLinkedTokenSource(ct);
            timeoutCts.CancelAfter(TimeSpan.FromSeconds(60));
            await proc.WaitForExitAsync(timeoutCts.Token);

            if (proc.ExitCode == 0)
            {
                log.Sucesso($"Serviço SQL Server ('{serviceName}') reiniciado com sucesso. Mixed Mode Authentication ativo!");
                await Task.Delay(TimeSpan.FromSeconds(2), ct);
                return true;
            }

            string errDetail = string.IsNullOrWhiteSpace(stderr) ? stdout : stderr;
            log.Aviso($"Não foi possível reiniciar '{serviceName}' automaticamente (código {proc.ExitCode}): {errDetail.Trim()}");
        }
        catch (Exception ex)
        {
            log.Aviso($"Aviso ao reiniciar serviço SQL Server '{serviceName}': {ex.Message}");
        }

        return false;
    }

    private static async Task<SqlConnection> AbrirConexaoComRetentativaAsync(
        string connectionString,
        int maxTentativas,
        AuditorLog log,
        CancellationToken ct)
    {
        Exception? ultimoErro = null;
        for (int tentativa = 1; tentativa <= Math.Max(1, maxTentativas); tentativa++)
        {
            ct.ThrowIfCancellationRequested();
            var conn = new SqlConnection(connectionString);
            try
            {
                await conn.OpenAsync(ct);
                return conn;
            }
            catch (Exception ex)
            {
                await conn.DisposeAsync();
                ultimoErro = ex;
                if (tentativa < maxTentativas)
                {
                    log.Info($"Aguardando SQL Server finalizar inicialização ({tentativa}/{maxTentativas})...");
                    await Task.Delay(TimeSpan.FromSeconds(2), ct);
                }
            }
        }

        throw ultimoErro ?? new InvalidOperationException("Não foi possível reabrir a conexão com o banco MovideskDM.");
    }

    private static string EscaparIdentificadorSql(string identificador) => identificador.Replace("]", "]]");

    private static string EscaparLiteralSql(string valor) => valor.Replace("'", "''");

    private static async Task ExecutarScriptRecursoAsync(
        SqlConnection conn,
        string nomeRecurso,
        string nomeArquivoAmigavel,
        AuditorLog log,
        CancellationToken ct)
    {
        await using Stream? stream = AssemblyAtual.GetManifestResourceStream(nomeRecurso);
        if (stream is null) return;

        using var reader = new StreamReader(stream, Encoding.UTF8);
        string conteudoSql = await reader.ReadToEndAsync(ct);

        string[] lotes = Regex.Split(conteudoSql, @"^\s*GO\s*$", RegexOptions.Multiline | RegexOptions.IgnoreCase);

        int executados = 0;
        foreach (string rawBatch in lotes)
        {
            string batch = rawBatch.Trim();
            if (string.IsNullOrWhiteSpace(batch)) continue;

            // Ignora instruções USE pois a conexão já está no banco correto
            if (batch.StartsWith("USE ", StringComparison.OrdinalIgnoreCase)) continue;

            await using var cmd = new SqlCommand(batch, conn)
            {
                CommandTimeout = 180
            };

            try
            {
                await cmd.ExecuteNonQueryAsync(ct);
                executados++;
            }
            catch (SqlException sqlEx)
            {
                // Ignora erros não críticos se o objeto ou índice já existir (re-execução idempotente)
                if (sqlEx.Number is 2714 or 1913 or 1779) // object/index/primary key already exists
                {
                    continue;
                }
                log.Aviso($"Aviso em {nomeArquivoAmigavel} (linha {sqlEx.LineNumber}): {sqlEx.Message}");
            }
        }

        log.Info($"✔ Script '{nomeArquivoAmigavel}' processado ({executados} lotes executados).");
    }
}
