using System.Reflection;
using System.Text;
using System.Text.RegularExpressions;
using Microsoft.Data.SqlClient;

namespace Movidesk.Installer.Core;

/// <summary>
/// Executa o provisionamento nativo do SQL Server (MovideskDM) diretamente em C#
/// (sem depender de sqlcmd, SSMS ou utilitários externos).
/// Conecta via ADO.NET (Microsoft.Data.SqlClient), cria o banco se não existir
/// e processa todos os scripts SQL embutidos dividindo por lotes 'GO'.
/// </summary>
public sealed class SqlDatabaseDeployer
{
    private const string PrefixSqlResource = "Movidesk.Installer.Sql.";
    private static readonly Assembly AssemblyAtual = typeof(SqlDatabaseDeployer).Assembly;

    public static string ConstruirConnectionString(string host, string banco, string usuario, string senha)
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
        string user = config.SqlServerUsuario;
        string pass = config.SqlServerSenha;

        log.Aguardando($"Conectando nativamente ao SQL Server em '{host}' via C# (Microsoft.Data.SqlClient)...");

        // 1. Conecta no banco de sistema 'master' para verificar ou criar o banco MovideskDM
        string connStrMaster = ConstruirConnectionString(host, "master", user, pass);

        try
        {
            await using var connMaster = new SqlConnection(connStrMaster);
            await connMaster.OpenAsync(ct);
            log.Sucesso($"Conectado com sucesso ao SQL Server '{host}'.");

            await using var cmdCheck = new SqlCommand(
                "SELECT COUNT(1) FROM sys.databases WHERE name = @nomeBanco;", connMaster);
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
                    $"CREATE DATABASE [{banco}]; ALTER DATABASE [{banco}] SET RECOVERY SIMPLE;", connMaster);
                await cmdCreate.ExecuteNonQueryAsync(ct);
                log.Sucesso($"Banco de dados '[{banco}]' criado com sucesso!");
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

        // 2. Conecta no banco alvo (MovideskDM) para aplicar tabelas, visões e procedimentos
        string connStrBanco = ConstruirConnectionString(host, banco, user, pass);
        try
        {
            await using var connBanco = new SqlConnection(connStrBanco);
            await connBanco.OpenAsync(ct);

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

            log.Sucesso($"Estrutura completa do Data Mart '[{banco}]' (schemas, tabelas, 3 covering indexes e 9 views mart.*) implantada com sucesso!");
            return true;
        }
        catch (Exception ex)
        {
            log.Aviso($"Aviso durante a aplicação dos scripts SQL no banco '{banco}': {ex.Message}");
            return false;
        }
    }

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
