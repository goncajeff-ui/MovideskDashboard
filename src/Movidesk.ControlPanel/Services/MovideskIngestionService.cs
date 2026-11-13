using System.Data;
using System.Globalization;
using System.Text.Json;
using Microsoft.Data.SqlClient;
using Microsoft.Extensions.Configuration;

namespace Movidesk.ControlPanel.Services;

public enum IngestionStage
{
    Idle,
    Extracting,
    SavingToDatabase,
    ProcessingCore,
    WaitingRateLimit,
    Completed,
    Cancelled,
    Error
}

/// <summary>
/// Orquestrador assíncrono de ingestão da API Movidesk -> SQL Server (MovideskDM).
/// Executa cargas pesadas estritamente em Task.Run no background para nunca travar a UI Blazor.
/// </summary>
public sealed class MovideskIngestionService : IDisposable
{
    // =========================================================================
    // CONFIGURAÇÃO DA STRING DE CONEXÃO DO MSSQL E API DO MOVIDESK
    // Altere em appsettings.json ("ConnectionStrings:MovideskDM" e "Movidesk:*")
    // =========================================================================
    private readonly string _connectionString;
    private readonly string _baseUrl;
    private readonly string _apiToken;
    private readonly int _batchSize;
    private readonly int _delayComercialMs;
    private readonly int _delayLivreMs;

    private readonly HttpClient _httpClient = new() { Timeout = TimeSpan.FromSeconds(120) };
    private readonly object _stateLock = new();
    private readonly List<string> _logs = new();
    private CancellationTokenSource? _cts;

    public bool IsRunning { get; private set; }
    public IngestionStage CurrentStage { get; private set; } = IngestionStage.Idle;
    public string CurrentStageLabel { get; private set; } = "Aguardando comando";
    public string CurrentJobType { get; private set; } = "-";
    public int ProcessedInCurrentRun { get; private set; }
    public DateTime? StartedAt { get; private set; }

    public event Action? OnStateChanged;

    public MovideskIngestionService(IConfiguration configuration)
    {
        // TODO: Ajuste sua ConnectionString do SQL Server em appsettings.json ("ConnectionStrings:MovideskDM")
        _connectionString = configuration.GetConnectionString("MovideskDM")
            ?? "Server=localhost;Database=MovideskDM;User Id=sa;Password=123456;TrustServerCertificate=True;MultipleActiveResultSets=True;";

        _baseUrl = configuration["Movidesk:BaseUrl"] ?? "https://api.movidesk.com/public/v1";
        _apiToken = configuration["Movidesk:Token"] ?? "e7190fc7-d1fd-4f89-b5b7-47e96fe64e73";
        _batchSize = int.TryParse(configuration["Movidesk:BatchSize"], out var bs) ? bs : 50;
        _delayComercialMs = int.TryParse(configuration["Movidesk:DelayHorarioComercialMs"], out var dc) ? dc : 6500;
        _delayLivreMs = int.TryParse(configuration["Movidesk:DelayHorarioLivreMs"], out var dl) ? dl : 200;
    }

    public IReadOnlyList<string> GetLogsSnapshot()
    {
        lock (_stateLock)
        {
            return _logs.ToList();
        }
    }

    public void ClearLogs()
    {
        lock (_stateLock)
        {
            _logs.Clear();
        }
        NotifyStateChanged();
    }

    /// <summary>
    /// Cancela graciosamente qualquer carga em execução.
    /// </summary>
    public void CancelarCarga()
    {
        lock (_stateLock)
        {
            if (!IsRunning) return;
            _cts?.Cancel();
        }
        AppendLog("[WRN] Solicitação de cancelamento enviada. Aguardando encerramento seguro do lote atual...");
    }

    /// <summary>
    /// Dispara a Carga Histórica Completa em background (Task.Run) com suporte a retomada via skipInicial.
    /// </summary>
    public async Task<bool> ExecutarCargaHistoricaAsync(int skipInicial = 0)
    {
        CancellationToken token;
        lock (_stateLock)
        {
            if (IsRunning) return false;

            IsRunning = true;
            CurrentJobType = $"Carga Histórica (skip={skipInicial})";
            ProcessedInCurrentRun = 0;
            StartedAt = DateTime.Now;
            _logs.Clear();
            _cts?.Dispose();
            _cts = new CancellationTokenSource();
            token = _cts.Token;
        }

        SetStage(IngestionStage.Extracting, "Extraindo...", $"Iniciando Carga Histórica Completa (skip inicial = {skipInicial})...");

        // Executa o motor extrator estritamente em Task.Run para jamais bloquear a thread do circuito Blazor
        await Task.Run(async () =>
        {
            int? execucaoId = await RegistrarInicioExecucaoAsync("HISTORICO_PAINEL");
            string statusFinal = "CONCLUIDO";
            string? msgFinal = null;

            try
            {
                AppendLog("[INF] --- Fase 1: Tickets ativos / recentes (/tickets) ---");
                int skip = Math.Max(0, skipInicial);
                int totalFase1 = 0;

                while (!token.IsCancellationRequested)
                {
                    await RespeitarRateLimitAsync(token);

                    SetStage(IngestionStage.Extracting, "Extraindo...", $"Extraindo lote /tickets (skip={skip}, top={_batchSize})...");
                    var tickets = await BuscarTicketsAsync("tickets", _batchSize, skip, "lastUpdate desc", "", token);
                    if (tickets.Count == 0)
                    {
                        AppendLog("[INF] Fase 1 finalizada (sem mais registros em /tickets).");
                        break;
                    }

                    SetStage(IngestionStage.SavingToDatabase, "Salvando no Banco...", $"Salvando {tickets.Count} tickets na tabela raw.Ticket...");
                    await SalvarTicketsRawAsync(tickets, "API_HISTORICO", token);

                    SetStage(IngestionStage.ProcessingCore, "Processando Core...", "Executando core.usp_ProcessarTickets (RAW -> CORE)...");
                    await ExecutarProcessamentoCoreAsync(token);

                    totalFase1 += tickets.Count;
                    skip += _batchSize;
                    AtualizarContagem(totalFase1);
                    AppendLog($"[OK] Fase 1: +{tickets.Count} tickets salvos e processados (total acumulado nesta execução: {totalFase1}).");

                    if (tickets.Count < _batchSize)
                    {
                        AppendLog("[INF] Último lote parcial da Fase 1 alcançado.");
                        break;
                    }
                }

                token.ThrowIfCancellationRequested();

                AppendLog("[INF] --- Fase 2: Tickets históricos antigos (/tickets/past) ---");
                skip = 0;
                int totalFase2 = 0;

                while (!token.IsCancellationRequested)
                {
                    await RespeitarRateLimitAsync(token);

                    SetStage(IngestionStage.Extracting, "Extraindo...", $"Extraindo lote /tickets/past (skip={skip}, top={_batchSize})...");
                    var tickets = await BuscarTicketsAsync("tickets/past", _batchSize, skip, "createdDate desc", "", token);
                    if (tickets.Count == 0)
                    {
                        AppendLog("[INF] Fase 2 finalizada (sem mais registros em /tickets/past).");
                        break;
                    }

                    SetStage(IngestionStage.SavingToDatabase, "Salvando no Banco...", $"Salvando {tickets.Count} tickets históricos na tabela raw.Ticket...");
                    await SalvarTicketsRawAsync(tickets, "API_PAST", token);

                    SetStage(IngestionStage.ProcessingCore, "Processando Core...", "Executando core.usp_ProcessarTickets (RAW -> CORE)...");
                    await ExecutarProcessamentoCoreAsync(token);

                    totalFase2 += tickets.Count;
                    skip += _batchSize;
                    AtualizarContagem(totalFase1 + totalFase2);
                    AppendLog($"[OK] Fase 2: +{tickets.Count} tickets históricos salvos (total geral nesta execução: {totalFase1 + totalFase2}).");

                    if (tickets.Count < _batchSize) break;
                }

                token.ThrowIfCancellationRequested();
                SetStage(IngestionStage.Completed, "Concluído", $"Carga Histórica concluída! Total processado nesta execução: {ProcessedInCurrentRun} tickets.");
            }
            catch (OperationCanceledException)
            {
                statusFinal = "CANCELADO";
                msgFinal = "Interrompida pelo usuário.";
                SetStage(IngestionStage.Cancelled, "Cancelado", $"Carga Histórica cancelada pelo operador. {ProcessedInCurrentRun} tickets salvos até a parada.");
            }
            catch (Exception ex)
            {
                statusFinal = "ERRO";
                msgFinal = ex.Message;
                SetStage(IngestionStage.Error, "Erro na Carga", $"[ERR] Falha na Carga Histórica: {ex.Message}");
            }
            finally
            {
                await RegistrarFimExecucaoAsync(execucaoId, statusFinal, ProcessedInCurrentRun, msgFinal);
                FinalizarEstadoExecucao();
            }
        });

        return true;
    }

    /// <summary>
    /// Dispara um ciclo completo de Carga Incremental usando a marca d'água (ctl.MarcaDagua) em Task.Run.
    /// </summary>
    public async Task<bool> ExecutarCargaIncrementalAsync()
    {
        CancellationToken token;
        lock (_stateLock)
        {
            if (IsRunning) return false;

            IsRunning = true;
            CurrentJobType = "Carga Incremental";
            ProcessedInCurrentRun = 0;
            StartedAt = DateTime.Now;
            _logs.Clear();
            _cts?.Dispose();
            _cts = new CancellationTokenSource();
            token = _cts.Token;
        }

        SetStage(IngestionStage.Extracting, "Extraindo...", "Iniciando Carga Incremental (verificando ctl.MarcaDagua)...");

        await Task.Run(async () =>
        {
            int? execucaoId = await RegistrarInicioExecucaoAsync("INCREMENTAL_PAINEL");
            string statusFinal = "CONCLUIDO";
            string? msgFinal = null;

            try
            {
                var ultimaData = await ObterUltimaMarcaDaguaAsync("TICKETS", token);
                string filter = "";

                if (ultimaData.HasValue)
                {
                    var dataFiltro = ultimaData.Value.AddMinutes(-10).ToString("yyyy-MM-ddTHH:mm:ssZ", CultureInfo.InvariantCulture);
                    filter = $"lastUpdate ge {dataFiltro}";
                    AppendLog($"[INF] Marca d'água encontrada. Buscando tickets com lastUpdate >= {dataFiltro}...");
                }
                else
                {
                    AppendLog("[INF] Nenhuma marca d'água registrada ainda. Buscando últimos tickets atualizados...");
                }

                int skip = 0;
                int totalCiclo = 0;
                DateTime? maiorDataLote = null;

                while (!token.IsCancellationRequested)
                {
                    await RespeitarRateLimitAsync(token);

                    SetStage(IngestionStage.Extracting, "Extraindo...", $"Consultando atualizações no Movidesk (skip={skip})...");
                    var tickets = await BuscarTicketsAsync("tickets", _batchSize, skip, "lastUpdate asc", filter, token);
                    if (tickets.Count == 0) break;

                    SetStage(IngestionStage.SavingToDatabase, "Salvando no Banco...", $"Salvando {tickets.Count} tickets atualizados no banco MovideskDM...");
                    await SalvarTicketsRawAsync(tickets, "API_INCREMENTAL", token);

                    totalCiclo += tickets.Count;
                    AtualizarContagem(totalCiclo);

                    foreach (var t in tickets)
                    {
                        if (t.TryGetProperty("lastUpdate", out var lu) && lu.TryGetDateTime(out var dt))
                        {
                            if (!maiorDataLote.HasValue || dt > maiorDataLote.Value)
                                maiorDataLote = dt;
                        }
                    }

                    AppendLog($"[OK] Lote incremental salvo ({tickets.Count} tickets).");

                    if (tickets.Count < _batchSize) break;
                    skip += _batchSize;
                }

                token.ThrowIfCancellationRequested();

                if (totalCiclo > 0)
                {
                    SetStage(IngestionStage.ProcessingCore, "Processando Core...", "Executando core.usp_ProcessarTickets para atualizar views do Superset...");
                    await ExecutarProcessamentoCoreAsync(token);

                    if (maiorDataLote.HasValue)
                    {
                        await AtualizarMarcaDaguaAsync("TICKETS", maiorDataLote.Value, token);
                        AppendLog($"[INF] Marca d'água atualizada para {maiorDataLote.Value:yyyy-MM-dd HH:mm:ss} UTC.");
                    }

                    token.ThrowIfCancellationRequested();
                    SetStage(IngestionStage.Completed, "Concluído", $"Carga Incremental concluída! {totalCiclo} ticket(s) sincronizado(s).");
                }
                else
                {
                    SetStage(IngestionStage.Completed, "Concluído", "Carga Incremental concluída. Nenhum ticket novo ou alterado desde a última marca d'água.");
                }
            }
            catch (OperationCanceledException)
            {
                statusFinal = "CANCELADO";
                msgFinal = "Interrompida pelo usuário.";
                SetStage(IngestionStage.Cancelled, "Cancelado", "Carga Incremental cancelada pelo operador.");
            }
            catch (Exception ex)
            {
                statusFinal = "ERRO";
                msgFinal = ex.Message;
                SetStage(IngestionStage.Error, "Erro na Carga", $"[ERR] Falha na Carga Incremental: {ex.Message}");
            }
            finally
            {
                await RegistrarFimExecucaoAsync(execucaoId, statusFinal, ProcessedInCurrentRun, msgFinal);
                FinalizarEstadoExecucao();
            }
        });

        return true;
    }

    private async Task<List<JsonElement>> BuscarTicketsAsync(
        string rota,
        int top,
        int skip,
        string orderby,
        string filter,
        CancellationToken ct)
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

        const int maxTentativas = 5;
        for (int tentativa = 1; tentativa <= maxTentativas; tentativa++)
        {
            ct.ThrowIfCancellationRequested();

            try
            {
                using var resp = await _httpClient.GetAsync(url, ct);
                if (resp.IsSuccessStatusCode)
                {
                    var json = await resp.Content.ReadAsStringAsync(ct);
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
                var erro = await resp.Content.ReadAsStringAsync(ct);

                if (statusCode == 503 || statusCode == 504 || statusCode == 429)
                {
                    int delaySegundos = 15 * tentativa;
                    if (resp.Headers.RetryAfter?.Delta is TimeSpan delta)
                    {
                        delaySegundos = (int)delta.TotalSeconds + 2;
                    }

                    AppendLog($"[WRN] API Movidesk retornou HTTP {statusCode} (tentativa {tentativa}/{maxTentativas}). Aguardando {delaySegundos}s...");
                    await Task.Delay(TimeSpan.FromSeconds(delaySegundos), ct);
                    continue;
                }

                throw new HttpRequestException($"Erro ao consultar /{rota} ({resp.StatusCode}): {erro}");
            }
            catch (OperationCanceledException)
            {
                throw;
            }
            catch (Exception ex) when (ex is not HttpRequestException || ex.Message.Contains("503"))
            {
                if (tentativa == maxTentativas) throw;
                AppendLog($"[WRN] Instabilidade de rede ({tentativa}/{maxTentativas}): {ex.Message}. Tentando novamente em 15s...");
                await Task.Delay(TimeSpan.FromSeconds(15), ct);
            }
        }

        throw new HttpRequestException($"Não foi possível obter resposta de /{rota} após {maxTentativas} tentativas.");
    }

    private async Task SalvarTicketsRawAsync(List<JsonElement> tickets, string fonte, CancellationToken ct)
    {
        await using var conn = new SqlConnection(_connectionString);
        await conn.OpenAsync(ct);

        await using var cmd = new SqlCommand(@"
            MERGE raw.Ticket AS T
            USING (
                SELECT @TicketId AS TicketId, @LastUpdateUtc AS LastUpdateUtc, @Payload AS Payload, @Fonte AS Fonte
            ) AS S
            ON T.TicketId = S.TicketId
            WHEN MATCHED THEN
                UPDATE SET T.LastUpdateUtc = S.LastUpdateUtc, T.Payload = S.Payload, T.Fonte = S.Fonte, T.Processado = 0
            WHEN NOT MATCHED THEN
                INSERT (TicketId, LastUpdateUtc, Payload, Fonte, Processado)
                VALUES (S.TicketId, S.LastUpdateUtc, S.Payload, S.Fonte, 0);", conn);

        cmd.Parameters.Add("@TicketId", SqlDbType.Int);
        cmd.Parameters.Add("@LastUpdateUtc", SqlDbType.DateTime2);
        cmd.Parameters.Add("@Payload", SqlDbType.NVarChar, -1);
        cmd.Parameters.Add("@Fonte", SqlDbType.VarChar, 20);

        foreach (var t in tickets)
        {
            ct.ThrowIfCancellationRequested();

            int id = t.GetProperty("id").GetInt32();
            DateTime? lastUpdate = null;
            if (t.TryGetProperty("lastUpdate", out var lu) && lu.TryGetDateTime(out var dt))
                lastUpdate = dt;

            cmd.Parameters["@TicketId"].Value = id;
            cmd.Parameters["@LastUpdateUtc"].Value = (object?)lastUpdate ?? DBNull.Value;
            cmd.Parameters["@Payload"].Value = t.GetRawText();
            cmd.Parameters["@Fonte"].Value = fonte;

            await cmd.ExecuteNonQueryAsync(ct);
        }
    }

    private async Task ExecutarProcessamentoCoreAsync(CancellationToken ct)
    {
        await using var conn = new SqlConnection(_connectionString);
        await conn.OpenAsync(ct);
        await using var cmd = new SqlCommand("core.usp_ProcessarTickets", conn)
        {
            CommandType = CommandType.StoredProcedure,
            CommandTimeout = 300
        };
        await cmd.ExecuteNonQueryAsync(ct);
    }

    private async Task<DateTime?> ObterUltimaMarcaDaguaAsync(string entidade, CancellationToken ct)
    {
        await using var conn = new SqlConnection(_connectionString);
        await conn.OpenAsync(ct);
        await using var cmd = new SqlCommand("SELECT UltimoValorUtc FROM ctl.MarcaDagua WHERE Entidade = @Entidade", conn);
        cmd.Parameters.AddWithValue("@Entidade", entidade);
        var result = await cmd.ExecuteScalarAsync(ct);
        return result != null && result != DBNull.Value ? (DateTime)result : null;
    }

    private async Task AtualizarMarcaDaguaAsync(string entidade, DateTime valorUtc, CancellationToken ct)
    {
        await using var conn = new SqlConnection(_connectionString);
        await conn.OpenAsync(ct);
        await using var cmd = new SqlCommand(@"
            MERGE ctl.MarcaDagua AS T
            USING (SELECT @Entidade AS Entidade, @Valor AS Valor) AS S
            ON T.Entidade = S.Entidade
            WHEN MATCHED THEN UPDATE SET T.UltimoValorUtc = S.Valor, T.AtualizadoEm = SYSDATETIME()
            WHEN NOT MATCHED THEN INSERT (Entidade, UltimoValorUtc) VALUES (S.Entidade, S.Valor);", conn);
        cmd.Parameters.AddWithValue("@Entidade", entidade);
        cmd.Parameters.AddWithValue("@Valor", valorUtc);
        await cmd.ExecuteNonQueryAsync(ct);
    }

    private async Task<int?> RegistrarInicioExecucaoAsync(string tipo)
    {
        try
        {
            await using var conn = new SqlConnection(_connectionString);
            await conn.OpenAsync();
            await using var cmd = new SqlCommand(
                "INSERT INTO ctl.ExecucaoCarga (Tipo, Status) OUTPUT INSERTED.ExecucaoId VALUES (@Tipo, 'EXECUTANDO');", conn);
            cmd.Parameters.AddWithValue("@Tipo", tipo);
            var id = await cmd.ExecuteScalarAsync();
            return id != null && id != DBNull.Value ? Convert.ToInt32(id) : null;
        }
        catch
        {
            return null;
        }
    }

    private async Task RegistrarFimExecucaoAsync(int? execucaoId, string status, int qtd, string? mensagem)
    {
        if (!execucaoId.HasValue) return;
        try
        {
            await using var conn = new SqlConnection(_connectionString);
            await conn.OpenAsync();
            await using var cmd = new SqlCommand(@"
                UPDATE ctl.ExecucaoCarga
                SET Fim = SYSDATETIME(), Status = @Status, QtdRegistros = @Qtd, Mensagem = @Msg
                WHERE ExecucaoId = @Id;", conn);
            cmd.Parameters.AddWithValue("@Id", execucaoId.Value);
            cmd.Parameters.AddWithValue("@Status", status);
            cmd.Parameters.AddWithValue("@Qtd", qtd);
            cmd.Parameters.AddWithValue("@Msg", (object?)mensagem ?? DBNull.Value);
            await cmd.ExecuteNonQueryAsync();
        }
        catch
        {
            // Não interrompe o fluxo caso a tabela de log falhe
        }
    }

    private async Task RespeitarRateLimitAsync(CancellationToken ct)
    {
        var tzId = OperatingSystem.IsWindows() ? "E. South America Standard Time" : "America/Sao_Paulo";
        var brasiliaNow = TimeZoneInfo.ConvertTimeFromUtc(DateTime.UtcNow, TimeZoneInfo.FindSystemTimeZoneById(tzId));
        var hora = brasiliaNow.TimeOfDay;
        bool ehHorarioComercial = hora >= new TimeSpan(7, 1, 0) && hora <= new TimeSpan(18, 59, 0);

        if (ehHorarioComercial)
        {
            SetStage(IngestionStage.WaitingRateLimit, "Aguardando Rate Limit...", $"Horário comercial (10 req/min). Aguardando {_delayComercialMs / 1000.0:0.0}s antes da próxima requisição...", logMessage: false);
            await Task.Delay(_delayComercialMs, ct);
        }
        else
        {
            await Task.Delay(_delayLivreMs, ct);
        }
    }

    private void SetStage(IngestionStage stage, string label, string logLine, bool logMessage = true)
    {
        lock (_stateLock)
        {
            CurrentStage = stage;
            CurrentStageLabel = label;
        }

        if (logMessage)
        {
            AppendLog(logLine);
        }
        else
        {
            NotifyStateChanged();
        }
    }

    private void AtualizarContagem(int total)
    {
        lock (_stateLock)
        {
            ProcessedInCurrentRun = total;
        }
        NotifyStateChanged();
    }

    private void FinalizarEstadoExecucao()
    {
        lock (_stateLock)
        {
            IsRunning = false;
        }
        NotifyStateChanged();
    }

    private void AppendLog(string message)
    {
        var formatted = $"[{DateTime.Now:HH:mm:ss}] {message}";
        lock (_stateLock)
        {
            _logs.Add(formatted);
            if (_logs.Count > 300)
            {
                _logs.RemoveAt(0);
            }
        }
        NotifyStateChanged();
    }

    private void NotifyStateChanged() => OnStateChanged?.Invoke();

    public void Dispose()
    {
        _cts?.Cancel();
        _cts?.Dispose();
        _httpClient.Dispose();
    }
}
