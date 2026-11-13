using System;
using System.Collections.Generic;
using System.Data;
using System.Globalization;
using System.Net.Http;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Data.SqlClient;
using Microsoft.Extensions.Configuration;
using Serilog;

namespace Movidesk.Ingestion;

public class Program
{
    private static IConfiguration _config = null!;
    private static string _connectionString = null!;
    private static string _apiToken = null!;
    private static string _baseUrl = null!;
    private static int _batchSize = 50;
    private static readonly HttpClient _httpClient = new HttpClient { Timeout = TimeSpan.FromSeconds(120) };

    public static async Task<int> Main(string[] args)
    {
        Log.Logger = new LoggerConfiguration()
            .WriteTo.Console(outputTemplate: "[{Timestamp:HH:mm:ss} {Level:u3}] {Message:lj}{NewLine}{Exception}")
            .CreateLogger();

        try
        {
            var builder = new ConfigurationBuilder()
                .SetBasePath(AppContext.BaseDirectory)
                .AddJsonFile("appsettings.json", optional: false, reloadOnChange: true);

            _config = builder.Build();
            _connectionString = _config.GetConnectionString("DataMart") 
                ?? throw new InvalidOperationException("ConnectionString 'DataMart' não configurada no appsettings.json.");
            _apiToken = _config["Movidesk:Token"] 
                ?? throw new InvalidOperationException("Token do Movidesk não configurado.");
            _baseUrl = _config["Movidesk:BaseUrl"] ?? "https://api.movidesk.com/public/v1";
            _batchSize = int.TryParse(_config["Movidesk:BatchSize"], out var bs) ? bs : 50;

            Log.Information("=== Movidesk Ingestor Data Mart ===");
            Log.Information("Base API: {BaseUrl}", _baseUrl);

            string modo = args.Length > 0 ? args[0].ToLowerInvariant().Replace("--", "") : "teste";

            switch (modo)
            {
                case "historico":
                    int skipInicial = args.Length > 1 && int.TryParse(args[1], out var sk) ? sk : 0;
                    Log.Information("Iniciando modo: CARGA HISTÓRICA COMPLETA (a partir do ticket {Skip})", skipInicial);
                    await ExecutarCargaHistoricaAsync(skipInicial);
                    break;

                case "incremental":
                    Log.Information("Iniciando modo: CARGA INCREMENTAL CONTÍNUA");
                    await ExecutarCargaIncrementalContinuaAsync();
                    break;

                case "pessoas":
                    Log.Information("Iniciando modo: CARGA DE PESSOAS / EMPRESAS");
                    await ExecutarCargaPessoasAsync();
                    break;

                case "processar":
                    Log.Information("Executando procedure de processamento RAW -> CORE...");
                    await ExecutarProcessamentoCoreAsync();
                    break;

                case "teste":
                default:
                    Log.Information("Iniciando modo: TESTE RÁPIDO (Últimos {BatchSize} tickets)", _batchSize);
                    await ExecutarCargaRecenteAsync(_batchSize);
                    await ExecutarProcessamentoCoreAsync();
                    break;
            }

            Log.Information("Execução concluída com sucesso!");
            return 0;
        }
        catch (Exception ex)
        {
            Log.Fatal(ex, "Falha crítica durante a execução do Ingestor.");
            return 1;
        }
        finally
        {
            Log.CloseAndFlush();
        }
    }

    private static async Task ExecutarCargaRecenteAsync(int quantidade)
    {
        Log.Information("Buscando {Qtd} tickets mais recentes...", quantidade);
        var tickets = await BuscarTicketsAsync("tickets", top: quantidade, skip: 0, orderby: "lastUpdate desc");
        Log.Information("Baixados {Qtd} tickets. Salvando na tabela raw.Ticket...", tickets.Count);
        await SalvarTicketsRawAsync(tickets, "API_RECENTE");
    }

    private static async Task ExecutarCargaHistoricaAsync(int skipInicial = 0)
    {
        Log.Information("--- Fase 1: Tickets ativos / recentes (/tickets) ---");
        int skip = skipInicial;
        int totalFase1 = skipInicial;
        while (true)
        {
            await RespeitarRateLimitAsync();
            var tickets = await BuscarTicketsAsync("tickets", top: _batchSize, skip: skip, orderby: "lastUpdate desc");
            if (tickets.Count == 0) break;

            await SalvarTicketsRawAsync(tickets, "API_HISTORICO");
            await ExecutarProcessamentoCoreAsync();
            totalFase1 += tickets.Count;
            skip += _batchSize;
            Log.Information("Fase 1: {Total} tickets recentes processados até agora...", totalFase1);

            if (tickets.Count < _batchSize) break;
        }

        Log.Information("--- Fase 2: Tickets históricos antigos (/tickets/past) ---");
        skip = 0;
        int totalFase2 = 0;
        while (true)
        {
            await RespeitarRateLimitAsync();
            var tickets = await BuscarTicketsAsync("tickets/past", top: _batchSize, skip: skip, orderby: "createdDate desc");
            if (tickets.Count == 0) break;

            await SalvarTicketsRawAsync(tickets, "API_PAST");
            await ExecutarProcessamentoCoreAsync();
            totalFase2 += tickets.Count;
            skip += _batchSize;
            Log.Information("Fase 2: {Total} tickets do histórico processados...", totalFase2);

            if (tickets.Count < _batchSize) break;
        }

        Log.Information("Carga histórica finalizada! Total geral: {Total}", totalFase1 + totalFase2);
    }

    private static async Task ExecutarCargaIncrementalContinuaAsync()
    {
        int intervaloMin = int.TryParse(_config["Movidesk:IntervaloIncrementalMinutos"], out var im) ? im : 5;
        Log.Information("Loop incremental ativo. Intervalo entre ciclos: {Min} minutos.", intervaloMin);

        while (true)
        {
            try
            {
                var ultimaData = await ObterUltimaMarcaDaguaAsync("TICKETS");
                string filter = "";
                if (ultimaData.HasValue)
                {
                    // Busca com margem de segurança de 10 minutos
                    var dataFiltro = ultimaData.Value.AddMinutes(-10).ToString("yyyy-MM-ddTHH:mm:ssZ", CultureInfo.InvariantCulture);
                    filter = $"lastUpdate ge {dataFiltro}";
                    Log.Information("Ciclo incremental: buscando tickets com lastUpdate >= {Data}...", dataFiltro);
                }
                else
                {
                    Log.Information("Primeiro ciclo incremental: buscando tickets recentes...");
                }

                int skip = 0;
                int totalCiclo = 0;
                DateTime? maiorDataLote = null;

                while (true)
                {
                    await RespeitarRateLimitAsync();
                    var tickets = await BuscarTicketsAsync("tickets", top: _batchSize, skip: skip, orderby: "lastUpdate asc", filter: filter);
                    if (tickets.Count == 0) break;

                    await SalvarTicketsRawAsync(tickets, "API_INCREMENTAL");
                    totalCiclo += tickets.Count;

                    foreach (var t in tickets)
                    {
                        if (t.TryGetProperty("lastUpdate", out var lu) && lu.TryGetDateTime(out var dt))
                        {
                            if (!maiorDataLote.HasValue || dt > maiorDataLote.Value)
                                maiorDataLote = dt;
                        }
                    }

                    if (tickets.Count < _batchSize) break;
                    skip += _batchSize;
                }

                if (totalCiclo > 0)
                {
                    Log.Information("Ciclo incremental: {Qtd} tickets atualizados. Processando CORE...", totalCiclo);
                    await ExecutarProcessamentoCoreAsync();
                    if (maiorDataLote.HasValue)
                        await AtualizarMarcaDaguaAsync("TICKETS", maiorDataLote.Value);
                }
                else
                {
                    Log.Information("Nenhum ticket novo ou alterado neste ciclo.");
                }
            }
            catch (Exception ex)
            {
                Log.Error(ex, "Erro no ciclo incremental. Tentará novamente no próximo ciclo.");
            }

            Log.Information("Aguardando {Min} minutos até a próxima verificação...", intervaloMin);
            await Task.Delay(TimeSpan.FromMinutes(intervaloMin));
        }
    }

    private static async Task ExecutarCargaPessoasAsync()
    {
        Log.Information("Sincronizando empresas e clientes via /persons...");
        int skip = 0;
        int total = 0;
        string select = "id,businessName,corporateName,cpfCnpj,personType,profileType,isActive,createdDate";

        while (true)
        {
            await RespeitarRateLimitAsync();
            string url = $"{_baseUrl}/persons?token={Uri.EscapeDataString(_apiToken)}&$select={select}&$filter=personType eq 2&$top={_batchSize}&$skip={skip}";
            var resp = await _httpClient.GetAsync(url);
            if (!resp.IsSuccessStatusCode)
            {
                var erro = await resp.Content.ReadAsStringAsync();
                Log.Error("Erro em /persons: {Status} - {Erro}", resp.StatusCode, erro);
                break;
            }

            var json = await resp.Content.ReadAsStringAsync();
            using var doc = JsonDocument.Parse(json);
            var root = doc.RootElement;
            if (root.ValueKind != JsonValueKind.Array || root.GetArrayLength() == 0) break;

            await SalvarPessoasRawAsync(root, "API");
            total += root.GetArrayLength();
            Log.Information("Sincronizadas {Total} empresas até agora...", total);

            if (root.GetArrayLength() < _batchSize) break;
            skip += _batchSize;
        }

        Log.Information("Carga de empresas finalizada. Total: {Total}", total);
    }

    private static async Task<List<JsonElement>> BuscarTicketsAsync(string rota, int top, int skip, string orderby, string filter = "")
    {
        string select = "id,protocol,type,subject,category,urgency,status,baseStatus,justification," +
                        "origin,createdDate,lastUpdate,lastActionDate,resolvedIn,closedIn,reopenedIn," +
                        "actionCount,ownerTeam,serviceFirstLevel,serviceSecondLevel,serviceThirdLevel,tags," +
                        "slaAgreement,slaAgreementRule,slaSolutionTime,slaResponseTime,slaSolutionDate," +
                        "slaSolutionDateIsPaused,slaResponseDate,slaRealResponseDate,resolvedInFirstCall";

        string expand = "owner,clients,statusHistories,customFieldValues";

        var query = $"$select={select}&$expand={expand}&$top={top}&$skip={skip}&$orderby={Uri.EscapeDataString(orderby)}";
        if (!string.IsNullOrEmpty(filter))
        {
            query += $"&$filter={Uri.EscapeDataString(filter)}";
        }

        string url = $"{_baseUrl}/{rota}?token={Uri.EscapeDataString(_apiToken)}&{query}";

        int maxTentativas = 5;
        for (int tentativa = 1; tentativa <= maxTentativas; tentativa++)
        {
            try
            {
                var resp = await _httpClient.GetAsync(url);
                if (resp.IsSuccessStatusCode)
                {
                    var json = await resp.Content.ReadAsStringAsync();
                    using var doc = JsonDocument.Parse(json);
                    var lista = new List<JsonElement>();

                    if (doc.RootElement.ValueKind == JsonValueKind.Array)
                    {
                        foreach (var item in doc.RootElement.EnumerateArray())
                        {
                            lista.Add(item.Clone());
                        }
                    }
                    return lista;
                }

                int statusCode = (int)resp.StatusCode;
                var erro = await resp.Content.ReadAsStringAsync();

                // Trata 503 (banco temporariamente indisponível), 504 (timeout) ou 429 (rate limit)
                if (statusCode == 503 || statusCode == 504 || statusCode == 429)
                {
                    int delaySegundos = 15 * tentativa;
                    if (resp.Headers.RetryAfter != null && resp.Headers.RetryAfter.Delta.HasValue)
                    {
                        delaySegundos = (int)resp.Headers.RetryAfter.Delta.Value.TotalSeconds + 2;
                    }

                    Log.Warning("API Movidesk retornou {Status} (tentativa {Tentativa}/{Max}). Aguardando {Segundos}s antes de tentar novamente...", 
                        statusCode, tentativa, maxTentativas, delaySegundos);
                    
                    await Task.Delay(TimeSpan.FromSeconds(delaySegundos));
                    continue;
                }

                throw new HttpRequestException($"Erro ao consultar /{rota} ({resp.StatusCode}): {erro}");
            }
            catch (Exception ex) when (ex is not HttpRequestException || ex.Message.Contains("503"))
            {
                if (tentativa == maxTentativas) throw;
                Log.Warning("Instabilidade de rede/servidor na tentativa {Tentativa}/{Max}: {Msg}. Aguardando 15s...", tentativa, maxTentativas, ex.Message);
                await Task.Delay(TimeSpan.FromSeconds(15));
            }
        }

        throw new HttpRequestException($"Não foi possível obter resposta de /{rota} após {maxTentativas} tentativas devido à sobrecarga no servidor do Movidesk.");
    }

    private static async Task SalvarTicketsRawAsync(List<JsonElement> tickets, string fonte)
    {
        using var conn = new SqlConnection(_connectionString);
        await conn.OpenAsync();

        using var cmd = new SqlCommand(@"
            MERGE raw.Ticket AS T
            USING (
                SELECT @TicketId AS TicketId, @LastUpdateUtc AS LastUpdateUtc, @Payload AS Payload, @Fonte AS Fonte
            ) AS S
            ON T.TicketId = S.TicketId
            WHEN MATCHED THEN
                UPDATE SET T.LastUpdateUtc = S.LastUpdateUtc, T.Payload = S.Payload, T.Fonte = S.Fonte, T.Processado = 0
            WHEN NOT MATCHED THEN
                INSERT (TicketId, LastUpdateUtc, Payload, Fonte, Processado)
                VALUES (S.TicketId, S.LastUpdateUtc, S.Payload, S.Fonte, 0);
        ", conn);

        cmd.Parameters.Add("@TicketId", SqlDbType.Int);
        cmd.Parameters.Add("@LastUpdateUtc", SqlDbType.DateTime2);
        cmd.Parameters.Add("@Payload", SqlDbType.NVarChar, -1);
        cmd.Parameters.Add("@Fonte", SqlDbType.VarChar, 20);

        foreach (var t in tickets)
        {
            int id = t.GetProperty("id").GetInt32();
            DateTime? lastUpdate = null;
            if (t.TryGetProperty("lastUpdate", out var lu) && lu.TryGetDateTime(out var dt))
                lastUpdate = dt;

            cmd.Parameters["@TicketId"].Value = id;
            cmd.Parameters["@LastUpdateUtc"].Value = (object?)lastUpdate ?? DBNull.Value;
            cmd.Parameters["@Payload"].Value = t.GetRawText();
            cmd.Parameters["@Fonte"].Value = fonte;

            await cmd.ExecuteNonQueryAsync();
        }
    }

    private static async Task SalvarPessoasRawAsync(JsonElement root, string fonte)
    {
        using var conn = new SqlConnection(_connectionString);
        await conn.OpenAsync();

        using var cmd = new SqlCommand(@"
            MERGE raw.Pessoa AS T
            USING (
                SELECT @PessoaId AS PessoaId, @Payload AS Payload, @Fonte AS Fonte
            ) AS S
            ON T.PessoaId = S.PessoaId
            WHEN MATCHED THEN
                UPDATE SET T.Payload = S.Payload, T.Fonte = S.Fonte, T.Processado = 0
            WHEN NOT MATCHED THEN
                INSERT (PessoaId, Payload, Fonte, Processado)
                VALUES (S.PessoaId, S.Payload, S.Fonte, 0);
        ", conn);

        cmd.Parameters.Add("@PessoaId", SqlDbType.VarChar, 64);
        cmd.Parameters.Add("@Payload", SqlDbType.NVarChar, -1);
        cmd.Parameters.Add("@Fonte", SqlDbType.VarChar, 20);

        foreach (var p in root.EnumerateArray())
        {
            string id = p.GetProperty("id").GetString() ?? "";
            cmd.Parameters["@PessoaId"].Value = id;
            cmd.Parameters["@Payload"].Value = p.GetRawText();
            cmd.Parameters["@Fonte"].Value = fonte;
            await cmd.ExecuteNonQueryAsync();
        }
    }

    public static async Task ExecutarProcessamentoCoreAsync()
    {
        using var conn = new SqlConnection(_connectionString);
        await conn.OpenAsync();
        using var cmd = new SqlCommand("core.usp_ProcessarTickets", conn)
        {
            CommandType = CommandType.StoredProcedure,
            CommandTimeout = 300
        };
        await cmd.ExecuteNonQueryAsync();
    }

    private static async Task<DateTime?> ObterUltimaMarcaDaguaAsync(string entidade)
    {
        using var conn = new SqlConnection(_connectionString);
        await conn.OpenAsync();
        using var cmd = new SqlCommand("SELECT UltimoValorUtc FROM ctl.MarcaDagua WHERE Entidade = @Entidade", conn);
        cmd.Parameters.AddWithValue("@Entidade", entidade);
        var result = await cmd.ExecuteScalarAsync();
        return result != null && result != DBNull.Value ? (DateTime)result : null;
    }

    private static async Task AtualizarMarcaDaguaAsync(string entidade, DateTime valorUtc)
    {
        using var conn = new SqlConnection(_connectionString);
        await conn.OpenAsync();
        using var cmd = new SqlCommand(@"
            MERGE ctl.MarcaDagua AS T
            USING (SELECT @Entidade AS Entidade, @Valor AS Valor) AS S
            ON T.Entidade = S.Entidade
            WHEN MATCHED THEN UPDATE SET T.UltimoValorUtc = S.Valor, T.AtualizadoEm = SYSDATETIME()
            WHEN NOT MATCHED THEN INSERT (Entidade, UltimoValorUtc) VALUES (S.Entidade, S.Valor);
        ", conn);
        cmd.Parameters.AddWithValue("@Entidade", entidade);
        cmd.Parameters.AddWithValue("@Valor", valorUtc);
        await cmd.ExecuteNonQueryAsync();
    }

    private static async Task RespeitarRateLimitAsync()
    {
        var brasiliaNow = TimeZoneInfo.ConvertTimeFromUtc(DateTime.UtcNow, 
            TimeZoneInfo.FindSystemTimeZoneById(OperatingSystem.IsWindows() ? "E. South America Standard Time" : "America/Sao_Paulo"));

        var hora = brasiliaNow.TimeOfDay;
        bool ehHorarioComercial = hora >= new TimeSpan(7, 1, 0) && hora <= new TimeSpan(18, 59, 0);

        if (ehHorarioComercial)
        {
            // Limite Movidesk: 10 requisições por minuto (1 a cada 6 segundos)
            int delay = int.TryParse(_config["Movidesk:DelayEntreRequisicoesMs"], out var d) ? d : 6500;
            await Task.Delay(delay);
        }
        else
        {
            // Fora do horário comercial: acesso irrestrito na API! Delay mínimo de 200ms
            await Task.Delay(200);
        }
    }
}
