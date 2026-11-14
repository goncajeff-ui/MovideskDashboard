using System.Data;
using System.Globalization;
using System.Reflection;
using System.Text;
using System.Text.Json;
using System.Text.RegularExpressions;
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
/// Possui Retomada Inteligente por Cursor de Data (LastUpdateUtc), sincronização de Empresas (/persons)
/// e atualização automática das Procedures e Views analíticas no SQL Server.
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
    private bool _objetosBancoVerificados;

    public bool IsRunning { get; private set; }
    public IngestionStage CurrentStage { get; private set; } = IngestionStage.Idle;
    public string CurrentStageLabel { get; private set; } = "Aguardando comando";
    public string CurrentJobType { get; private set; } = "-";
    public int ProcessedInCurrentRun { get; private set; }
    public int NewInsertedInCurrentRun { get; private set; }
    public int UpdatedInCurrentRun { get; private set; }
    public string CurrentCursorLabel { get; private set; } = "Automático (Banco MovideskDM)";
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
    /// Aplica automaticamente no banco MovideskDM as Procedures (usp_AtualizarSnapshotBacklog,
    /// usp_ProcessarPessoas, usp_ProcessarTickets), o dicionário Dim_CampoCustomizado e as 8 Views mart.*,
    /// além de reprocessar os chamados existentes em raw.Ticket caso Fato_SnapshotBacklog esteja vazio.
    /// </summary>
    public async Task GarantirObjetosBancoAtualizadosAsync(CancellationToken ct = default)
    {
        if (_objetosBancoVerificados) return;

        try
        {
            await using var conn = new SqlConnection(_connectionString);
            await conn.OpenAsync(ct);

            // 1. Garante dicionário de Campos Customizados
            const string sqlCampos = @"
                MERGE core.Dim_CampoCustomizado AS T
                USING (VALUES
                    (133948, N'Versão do Produto / Release', N'Versão do sistema informada no chamado (ex.: KN1, e-Guardian, Aquilla)'),
                    (133947, N'Campo Customizado #133947',   N'Campo adicional de formulário de atendimento (regra 67477)'),
                    (129731, N'Campo Customizado #129731',   N'Campo adicional de formulário de atendimento (regra 64915)'),
                    (142628, N'Campo Customizado #142628',   N'Campo adicional de formulário de atendimento (regra 72075)'),
                    (184522, N'Campo Customizado #184522',   N'Campo adicional de formulário de atendimento (regra 94167)')
                ) AS S (CampoId, Nome, Descricao)
                ON T.CampoId = S.CampoId
                WHEN MATCHED THEN UPDATE SET T.Nome = S.Nome, T.Descricao = S.Descricao
                WHEN NOT MATCHED THEN INSERT (CampoId, Nome, Descricao) VALUES (S.CampoId, S.Nome, S.Descricao);";

            await using (var cmdCampos = new SqlCommand(sqlCampos, conn) { CommandTimeout = 30 })
            {
                await cmdCampos.ExecuteNonQueryAsync(ct);
            }

            // 2. Aplica 04_procedure_processamento.sql e 03_views_kpis.sql embutidos no executável
            await ExecutarScriptSqlEmbutidoAsync(conn, "Movidesk.ControlPanel.Sql.04_procedure_processamento.sql", ct);
            await ExecutarScriptSqlEmbutidoAsync(conn, "Movidesk.ControlPanel.Sql.03_views_kpis.sql", ct);

            // 3. Verifica se os chamados já existentes precisam ser reprocessados para Fuso BRT + Snapshot 90d
            const string sqlCheckSnapshot = @"
                SELECT
                    (SELECT COUNT(*) FROM raw.Ticket) AS TotalRaw,
                    (SELECT COUNT(DISTINCT DataSnapshot) FROM core.Fato_SnapshotBacklog) AS DiasSnapshot;";

            int totalRaw = 0;
            int diasSnapshot = 0;
            await using (var cmdCheck = new SqlCommand(sqlCheckSnapshot, conn) { CommandTimeout = 30 })
            await using (var reader = await cmdCheck.ExecuteReaderAsync(ct))
            {
                if (await reader.ReadAsync(ct))
                {
                    totalRaw = reader.IsDBNull(0) ? 0 : reader.GetInt32(0);
                    diasSnapshot = reader.IsDBNull(1) ? 0 : reader.GetInt32(1);
                }
            }

            if (totalRaw > 0 && diasSnapshot < 2)
            {
                AppendLog($"[INF] Atualizando {totalRaw:N0} chamados existentes para Horário de Brasília (BRT), DataFim e Snapshot de 90 dias...");

                await using (var cmdReset = new SqlCommand("UPDATE raw.Ticket SET Processado = 0 WHERE Processado = 1;", conn) { CommandTimeout = 120 })
                {
                    await cmdReset.ExecuteNonQueryAsync(ct);
                }

                while (!ct.IsCancellationRequested)
                {
                    int pendentes;
                    await using (var cmdPend = new SqlCommand("SELECT COUNT(*) FROM raw.Ticket WHERE Processado = 0;", conn) { CommandTimeout = 30 })
                    {
                        pendentes = Convert.ToInt32(await cmdPend.ExecuteScalarAsync(ct));
                    }

                    if (pendentes <= 0) break;

                    await using var cmdProc = new SqlCommand("core.usp_ProcessarTickets", conn)
                    {
                        CommandType = CommandType.StoredProcedure,
                        CommandTimeout = 300
                    };
                    await cmdProc.ExecuteNonQueryAsync(ct);
                }

                await using (var cmdSnap = new SqlCommand("EXEC core.usp_AtualizarSnapshotBacklog @DiasRetroativos = 90, @ReconstruirHistorico = 1;", conn) { CommandTimeout = 300 })
                {
                    await cmdSnap.ExecuteNonQueryAsync(ct);
                }

                AppendLog("[OK] Procedures, 8 Views (incluindo mart.vw_BacklogEvolucao), Fuso BRT e Snapshot de 90 dias aplicados com sucesso!");
            }
            else
            {
                AppendLog("[OK] Procedures (usp_ProcessarTickets, usp_ProcessarPessoas, usp_AtualizarSnapshotBacklog) e 8 Views sincronizadas no MovideskDM.");
            }

            _objetosBancoVerificados = true;
        }
        catch (Exception ex)
        {
            AppendLog($"[WRN] Aviso ao verificar atualização automática de procedures/views: {ex.Message}");
        }
    }

    private static async Task ExecutarScriptSqlEmbutidoAsync(SqlConnection conn, string resourceName, CancellationToken ct)
    {
        var asm = Assembly.GetExecutingAssembly();
        await using var stream = asm.GetManifestResourceStream(resourceName);
        if (stream is null) return;

        using var sr = new StreamReader(stream, Encoding.UTF8);
        var script = await sr.ReadToEndAsync(ct);

        var batches = Regex.Split(script, @"^\s*GO\s*$", RegexOptions.Multiline | RegexOptions.IgnoreCase);
        foreach (var rawBatch in batches)
        {
            var batch = rawBatch.Trim();
            if (string.IsNullOrWhiteSpace(batch)) continue;
            if (batch.StartsWith("USE ", StringComparison.OrdinalIgnoreCase)) continue;

            await using var cmd = new SqlCommand(batch, conn) { CommandTimeout = 180 };
            await cmd.ExecuteNonQueryAsync(ct);
        }
    }

    /// <summary>
    /// Sincroniza a API /persons (Empresas + vínculo Pessoa Física -> Empresa dos chamados existentes)
    /// em Task.Run para corrigir retroativamente core.Dim_Cliente e core.Fato_Ticket.EmpresaId sem rebaixar tickets.
    /// </summary>
    public async Task<bool> ExecutarSincronizacaoEmpresasAsync()
    {
        CancellationToken token;
        lock (_stateLock)
        {
            if (IsRunning) return false;

            IsRunning = true;
            CurrentJobType = "Sincronização de Empresas (/persons)";
            ProcessedInCurrentRun = 0;
            NewInsertedInCurrentRun = 0;
            UpdatedInCurrentRun = 0;
            CurrentCursorLabel = "API /persons (Empresas + Vínculos)";
            StartedAt = DateTime.Now;
            _logs.Clear();
            _cts?.Dispose();
            _cts = new CancellationTokenSource();
            token = _cts.Token;
        }

        SetStage(IngestionStage.Extracting, "Extraindo...", "Iniciando Sincronização de Empresas e Vínculos de Clientes (/persons)...");

        await Task.Run(async () =>
        {
            int? execucaoId = await RegistrarInicioExecucaoAsync("PESSOAS_PAINEL");
            string statusFinal = "CONCLUIDO";
            string? msgFinal = null;

            try
            {
                await GarantirObjetosBancoAtualizadosAsync(token);
                await SincronizarEmpresasInternoAsync(token);

                token.ThrowIfCancellationRequested();
                AtualizarCursorLabel("Empresas e Contatos Sincronizados");
                SetStage(
                    IngestionStage.Completed,
                    "Concluído",
                    $"Sincronização de Empresas concluída! +{NewInsertedInCurrentRun:N0} novos cadastros, {UpdatedInCurrentRun:N0} atualizados em core.Dim_Cliente.");
            }
            catch (OperationCanceledException)
            {
                statusFinal = "CANCELADO";
                msgFinal = "Interrompida pelo usuário.";
                SetStage(IngestionStage.Cancelled, "Cancelado", "Sincronização de Empresas pausada pelo operador.");
            }
            catch (Exception ex)
            {
                statusFinal = "ERRO";
                msgFinal = ex.Message;
                SetStage(IngestionStage.Error, "Erro na Carga", $"[ERR] Falha na Sincronização de Empresas: {ex.Message}");
            }
            finally
            {
                await RegistrarFimExecucaoAsync(execucaoId, statusFinal, ProcessedInCurrentRun, msgFinal);
                FinalizarEstadoExecucao();
            }
        });

        return true;
    }

    private async Task SincronizarEmpresasInternoAsync(CancellationToken token)
    {
        // ---------------------------------------------------------------------
        // Etapa 1: Baixar todas as Empresas cadastradas no Movidesk (personType eq 2)
        // ---------------------------------------------------------------------
        AppendLog("[INF] --- Etapa 1/2: Importando cadastro de Empresas (/persons com personType eq 2) ---");
        int skipEmpresas = 0;
        const int topPessoas = 100;

        while (!token.IsCancellationRequested)
        {
            await RespeitarRateLimitAsync(token);

            AtualizarCursorLabel($"Empresas (/persons skip={skipEmpresas})");
            SetStage(IngestionStage.Extracting, "Extraindo...", $"Buscando Empresas em /persons (personType eq 2, skip={skipEmpresas})...");

            var empresas = await BuscarPessoasAsync(topPessoas, skipEmpresas, "id asc", "personType eq 2", token);
            if (empresas.Count == 0) break;

            SetStage(IngestionStage.SavingToDatabase, "Salvando no Banco...", $"Salvando {empresas.Count} empresas em raw.Pessoa...");
            var (ins, upd) = await SalvarPessoasRawAsync(empresas, "API_EMPRESA", token);

            SetStage(IngestionStage.ProcessingCore, "Processando Core...", "Executando core.usp_ProcessarPessoas...");
            await ExecutarProcessamentoPessoasCoreAsync(token);

            RegistrarEstatisticasLote(empresas.Count, ins, upd);
            AppendLog($"[OK] Empresas (/persons): +{ins} novas, {upd} atualizadas (skip={skipEmpresas}).");

            if (empresas.Count < topPessoas) break;
            skipEmpresas += topPessoas;
        }

        // ---------------------------------------------------------------------
        // Etapa 2: Resolver o vínculo Pessoa Física -> Empresa para os Contatos
        // já presentes nos chamados importados (Dim_Cliente sem EmpresaId)
        // ---------------------------------------------------------------------
        var contatosSemEmpresa = await ObterContatosPendentesVinculoAsync(token);
        if (contatosSemEmpresa.Count > 0)
        {
            AppendLog($"[INF] --- Etapa 2/2: Resolvendo vínculo de Empresa para {contatosSemEmpresa.Count:N0} contatos de chamados já importados ---");

            const int tamanhoLoteIds = 15;
            int totalLotes = (int)Math.Ceiling(contatosSemEmpresa.Count / (double)tamanhoLoteIds);

            for (int indiceLote = 0; indiceLote < totalLotes; indiceLote++)
            {
                token.ThrowIfCancellationRequested();
                await RespeitarRateLimitAsync(token);

                var loteIds = contatosSemEmpresa
                    .Skip(indiceLote * tamanhoLoteIds)
                    .Take(tamanhoLoteIds)
                    .ToList();

                var clausulasOr = loteIds.Select(id => $"id eq '{id.Replace("'", "''", StringComparison.Ordinal)}'");
                string filtroContatos = string.Join(" or ", clausulasOr);

                AtualizarCursorLabel($"Vínculo Contatos ({indiceLote + 1}/{totalLotes})");
                SetStage(
                    IngestionStage.Extracting,
                    "Extraindo...",
                    $"Consultando organização de contatos em /persons (lote {indiceLote + 1}/{totalLotes})...");

                var pessoas = await BuscarPessoasAsync(topPessoas, 0, "id asc", filtroContatos, token);
                if (pessoas.Count > 0)
                {
                    SetStage(IngestionStage.SavingToDatabase, "Salvando no Banco...", $"Salvando {pessoas.Count} contatos em raw.Pessoa...");
                    var (ins, upd) = await SalvarPessoasRawAsync(pessoas, "API_CONTATO", token);

                    SetStage(IngestionStage.ProcessingCore, "Processando Core...", "Vinculando chamados às Empresas (core.usp_ProcessarPessoas)...");
                    await ExecutarProcessamentoPessoasCoreAsync(token);

                    RegistrarEstatisticasLote(pessoas.Count, ins, upd);
                    AppendLog($"[OK] Lote {indiceLote + 1}/{totalLotes}: {pessoas.Count} contatos processados e vinculados às respectivas Empresas.");
                }
            }
        }
        else
        {
            AppendLog("[INF] Todos os contatos dos chamados atuais já estão sincronizados em raw.Pessoa.");
        }
    }

    /// <summary>
    /// Dispara ou retoma a Carga Histórica Completa em background (Task.Run).
    /// Detecta automaticamente os chamados já salvos em raw.Ticket e continua exatamente
    /// da fronteira histórica (LastUpdateUtc) sem repetir chamados já importados.
    /// </summary>
    public async Task<bool> ExecutarCargaHistoricaAsync(int skipInicial = 0)
    {
        CancellationToken token;
        lock (_stateLock)
        {
            if (IsRunning) return false;

            IsRunning = true;
            CurrentJobType = "Carga Histórica (Retomada Inteligente)";
            ProcessedInCurrentRun = 0;
            NewInsertedInCurrentRun = 0;
            UpdatedInCurrentRun = 0;
            CurrentCursorLabel = "Consultando fronteira no banco...";
            StartedAt = DateTime.Now;
            _logs.Clear();
            _cts?.Dispose();
            _cts = new CancellationTokenSource();
            token = _cts.Token;
        }

        SetStage(IngestionStage.Extracting, "Extraindo...", "Iniciando Carga Histórica com Retomada Inteligente pelo banco MovideskDM...");

        // Executa o motor extrator estritamente em Task.Run para jamais bloquear a thread do Blazor
        await Task.Run(async () =>
        {
            int? execucaoId = await RegistrarInicioExecucaoAsync("HISTORICO_PAINEL");
            string statusFinal = "CONCLUIDO";
            string? msgFinal = null;

            try
            {
                await GarantirObjetosBancoAtualizadosAsync(token);

                var estadoBanco = await ObterEstadoRetomadaAsync(token);

                if (estadoBanco.TotalRaw > 0 && estadoBanco.CursorRetomadaUtc.HasValue)
                {
                    AppendLog($"[INF] Banco MovideskDM já possui {estadoBanco.TotalRaw:N0} chamados salvos.");
                    AppendLog($"[INF] Fronteira histórica detectada automaticamente: lastUpdate <= {estadoBanco.CursorRetomadaUtc.Value:dd/MM/yyyy HH:mm:ss} UTC.");

                    // 1) Sincronização rápida do topo (novos chamados abertos/atualizados hoje após MaiorLastUpdateUtc)
                    if (estadoBanco.MaiorLastUpdateUtc.HasValue)
                    {
                        var filtroRecente = estadoBanco.MaiorLastUpdateUtc.Value
                            .AddMinutes(-5)
                            .ToString("yyyy-MM-ddTHH:mm:ssZ", CultureInfo.InvariantCulture);

                        AppendLog($"[INF] --- Fase 1 (Delta Rápido): Verificando chamados recentes (lastUpdate >= {filtroRecente}) ---");
                        int skipDelta = 0;
                        DateTime? maiorDataDelta = estadoBanco.MaiorLastUpdateUtc;

                        while (!token.IsCancellationRequested)
                        {
                            await RespeitarRateLimitAsync(token);

                            SetStage(IngestionStage.Extracting, "Extraindo...", $"Sincronizando topo recente /tickets (skip={skipDelta})...");
                            var recentes = await BuscarTicketsAsync("tickets", _batchSize, skipDelta, "lastUpdate asc", $"lastUpdate ge {filtroRecente}", token);
                            if (recentes.Count == 0) break;

                            SetStage(IngestionStage.SavingToDatabase, "Salvando no Banco...", $"Salvando {recentes.Count} tickets recentes em raw.Ticket...");
                            var (ins, upd) = await SalvarTicketsRawAsync(recentes, "API_HISTORICO", token);

                            if (ins > 0 || upd > 0)
                            {
                                SetStage(IngestionStage.ProcessingCore, "Processando Core...", "Executando core.usp_ProcessarTickets (RAW -> CORE)...");
                                await ExecutarProcessamentoCoreAsync(token);
                            }

                            RegistrarEstatisticasLote(recentes.Count, ins, upd);
                            AppendLog($"[OK] Fase 1 (Delta): +{ins} novos inseridos, {upd} atualizados.");

                            foreach (var t in recentes)
                            {
                                if (t.TryGetProperty("lastUpdate", out var lu) && lu.TryGetDateTime(out var dt))
                                {
                                    if (!maiorDataDelta.HasValue || dt > maiorDataDelta.Value)
                                        maiorDataDelta = dt;
                                }
                            }

                            if (recentes.Count < _batchSize) break;
                            skipDelta += _batchSize;
                        }

                        if (maiorDataDelta.HasValue)
                        {
                            await AtualizarMarcaDaguaAsync("TICKETS", maiorDataDelta.Value, token);
                        }
                    }
                }
                else
                {
                    // Banco totalmente vazio: Fase 1 carrega os chamados ativos/recentes (últimos 90 dias)
                    AppendLog("[INF] Banco vazio. --- Fase 1: Carregando chamados recentes (/tickets) ---");
                    int skip = Math.Max(0, skipInicial);
                    DateTime? maiorDataFase1 = null;

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
                        var (ins, upd) = await SalvarTicketsRawAsync(tickets, "API_HISTORICO", token);

                        if (ins > 0 || upd > 0)
                        {
                            SetStage(IngestionStage.ProcessingCore, "Processando Core...", "Executando core.usp_ProcessarTickets (RAW -> CORE)...");
                            await ExecutarProcessamentoCoreAsync(token);
                        }

                        foreach (var t in tickets)
                        {
                            if (t.TryGetProperty("lastUpdate", out var lu) && lu.TryGetDateTime(out var dt))
                            {
                                if (!maiorDataFase1.HasValue || dt > maiorDataFase1.Value)
                                    maiorDataFase1 = dt;
                            }
                        }

                        skip += _batchSize;
                        RegistrarEstatisticasLote(tickets.Count, ins, upd);
                        AppendLog($"[OK] Fase 1: +{ins} novos inseridos ({upd} já existiam) | Sessão: +{NewInsertedInCurrentRun:N0} novos.");

                        if (tickets.Count < _batchSize)
                        {
                            AppendLog("[INF] Último lote parcial da Fase 1 alcançado.");
                            break;
                        }
                    }

                    if (maiorDataFase1.HasValue)
                    {
                        await AtualizarMarcaDaguaAsync("TICKETS", maiorDataFase1.Value, token);
                    }

                    estadoBanco = await ObterEstadoRetomadaAsync(token);
                }

                token.ThrowIfCancellationRequested();

                // =========================================================================
                // FASE 2: HISTÓRICO COMPLETO (/tickets/past) COM CURSOR DE DATA REGRESSIVO
                // Usa $orderby=lastUpdate desc e $filter=lastUpdate le {cursorUtc} com $skip=0,
                // pulando instantaneamente todos os chamados já carregados no banco!
                // =========================================================================
                DateTime cursorFiltroUtc = estadoBanco.CursorRetomadaUtc.HasValue
                    ? CeilToSecond(estadoBanco.CursorRetomadaUtc.Value)
                    : CeilToSecond(DateTime.UtcNow);

                int skipNoCursor = 0;
                int lotesSemNovosNoMesmoSegundo = 0;

                AppendLog($"[INF] --- Fase 2: Carga Histórica em /tickets/past a partir de {cursorFiltroUtc:dd/MM/yyyy HH:mm:ss} UTC (para trás) ---");

                while (!token.IsCancellationRequested)
                {
                    await RespeitarRateLimitAsync(token);

                    string dataFiltroStr = cursorFiltroUtc.ToString("yyyy-MM-ddTHH:mm:ssZ", CultureInfo.InvariantCulture);
                    string filterPast = $"lastUpdate le {dataFiltroStr}";
                    AtualizarCursorLabel($"lastUpdate <= {cursorFiltroUtc:dd/MM/yyyy HH:mm:ss} UTC");

                    SetStage(
                        IngestionStage.Extracting,
                        "Extraindo...",
                        $"Extraindo /tickets/past (lastUpdate <= {dataFiltroStr}, skip={skipNoCursor}, top={_batchSize})...");

                    var tickets = await BuscarTicketsAsync("tickets/past", _batchSize, skipNoCursor, "lastUpdate desc", filterPast, token);
                    if (tickets.Count == 0)
                    {
                        AppendLog("[INF] Fase 2 finalizada! Todo o histórico de /tickets/past foi importado.");
                        break;
                    }

                    SetStage(IngestionStage.SavingToDatabase, "Salvando no Banco...", $"Salvando {tickets.Count} tickets históricos na tabela raw.Ticket...");
                    var (inseridos, atualizados) = await SalvarTicketsRawAsync(tickets, "API_PAST", token);

                    if (inseridos > 0 || atualizados > 0)
                    {
                        SetStage(IngestionStage.ProcessingCore, "Processando Core...", "Executando core.usp_ProcessarTickets (RAW -> CORE)...");
                        await ExecutarProcessamentoCoreAsync(token);
                    }

                    RegistrarEstatisticasLote(tickets.Count, inseridos, atualizados);

                    DateTime? menorDataLote = null;
                    int? menorIdLote = null;
                    foreach (var t in tickets)
                    {
                        if (t.TryGetProperty("id", out var idProp) && idProp.TryGetInt32(out var tid))
                        {
                            if (!menorIdLote.HasValue || tid < menorIdLote.Value)
                                menorIdLote = tid;
                        }

                        if (t.TryGetProperty("lastUpdate", out var lu) && lu.TryGetDateTime(out var dt))
                        {
                            if (!menorDataLote.HasValue || dt < menorDataLote.Value)
                                menorDataLote = dt;
                        }
                        else if (t.TryGetProperty("createdDate", out var cd) && cd.TryGetDateTime(out var cdt))
                        {
                            if (!menorDataLote.HasValue || cdt < menorDataLote.Value)
                                menorDataLote = cdt;
                        }
                    }

                    AppendLog(
                        $"[OK] Fase 2: +{inseridos} NOVOS inseridos, {atualizados} atualizados " +
                        $"(Menor ID lote: #{menorIdLote?.ToString() ?? "-"} | Data cursor: {menorDataLote:dd/MM/yyyy HH:mm} | Acumulado novos na sessão: +{NewInsertedInCurrentRun:N0}).");

                    if (tickets.Count < _batchSize)
                    {
                        AppendLog("[INF] Último lote histórico alcançado em /tickets/past!");
                        break;
                    }

                    // Avança o cursor de data para o chamado mais antigo do lote atual
                    if (menorDataLote.HasValue)
                    {
                        var novoCursorUtc = CeilToSecond(menorDataLote.Value);
                        if (novoCursorUtc < cursorFiltroUtc)
                        {
                            cursorFiltroUtc = novoCursorUtc;
                            skipNoCursor = 0;
                            lotesSemNovosNoMesmoSegundo = 0;
                        }
                        else
                        {
                            // Todos os 50 chamados do lote caíram no mesmo segundo exato
                            skipNoCursor += _batchSize;
                            if (inseridos == 0)
                            {
                                lotesSemNovosNoMesmoSegundo++;
                                if (lotesSemNovosNoMesmoSegundo >= 2)
                                {
                                    cursorFiltroUtc = cursorFiltroUtc.AddSeconds(-1);
                                    skipNoCursor = 0;
                                    lotesSemNovosNoMesmoSegundo = 0;
                                }
                            }
                        }
                    }
                    else
                    {
                        skipNoCursor += _batchSize;
                    }
                }

                token.ThrowIfCancellationRequested();
                AtualizarCursorLabel("Histórico Completo Sincronizado");
                SetStage(
                    IngestionStage.Completed,
                    "Concluído",
                    $"Carga Histórica concluída! +{NewInsertedInCurrentRun:N0} novos chamados inseridos ({ProcessedInCurrentRun:N0} lidos no total).");
            }
            catch (OperationCanceledException)
            {
                statusFinal = "CANCELADO";
                msgFinal = "Interrompida pelo usuário.";
                SetStage(
                    IngestionStage.Cancelled,
                    "Cancelado",
                    $"Carga Histórica pausada pelo operador. +{NewInsertedInCurrentRun:N0} novos chamados foram salvos no banco e a próxima execução retomará automaticamente deste ponto.");
            }
            catch (Exception ex)
            {
                statusFinal = "ERRO";
                msgFinal = ex.Message;
                SetStage(IngestionStage.Error, "Erro na Carga", $"[ERR] Falha na Carga Histórica: {ex.Message}");
            }
            finally
            {
                await RegistrarFimExecucaoAsync(execucaoId, statusFinal, NewInsertedInCurrentRun, msgFinal);
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
            NewInsertedInCurrentRun = 0;
            UpdatedInCurrentRun = 0;
            CurrentCursorLabel = "Marca d'Água (ctl.MarcaDagua)";
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
                await GarantirObjetosBancoAtualizadosAsync(token);

                var ultimaData = await ObterUltimaMarcaDaguaAsync("TICKETS", token);
                if (!ultimaData.HasValue)
                {
                    var estado = await ObterEstadoRetomadaAsync(token);
                    ultimaData = estado.MaiorLastUpdateUtc;
                }

                string filter = "";
                if (ultimaData.HasValue)
                {
                    var dataFiltro = ultimaData.Value.AddMinutes(-10).ToString("yyyy-MM-ddTHH:mm:ssZ", CultureInfo.InvariantCulture);
                    filter = $"lastUpdate ge {dataFiltro}";
                    AtualizarCursorLabel($"lastUpdate >= {ultimaData.Value.AddMinutes(-10):dd/MM/yyyy HH:mm} UTC");
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
                    var (ins, upd) = await SalvarTicketsRawAsync(tickets, "API_INCREMENTAL", token);

                    totalCiclo += tickets.Count;
                    RegistrarEstatisticasLote(tickets.Count, ins, upd);

                    foreach (var t in tickets)
                    {
                        if (t.TryGetProperty("lastUpdate", out var lu) && lu.TryGetDateTime(out var dt))
                        {
                            if (!maiorDataLote.HasValue || dt > maiorDataLote.Value)
                                maiorDataLote = dt;
                        }
                    }

                    AppendLog($"[OK] Lote incremental salvo (+{ins} novos, {upd} atualizados).");

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
                    SetStage(
                        IngestionStage.Completed,
                        "Concluído",
                        $"Carga Incremental concluída! +{NewInsertedInCurrentRun:N0} novos, {UpdatedInCurrentRun:N0} atualizados.");
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

    private static DateTime CeilToSecond(DateTime dt)
    {
        var truncated = new DateTime(dt.Year, dt.Month, dt.Day, dt.Hour, dt.Minute, dt.Second, DateTimeKind.Utc);
        return dt.Millisecond > 0 || dt.Ticks % TimeSpan.TicksPerSecond != 0
            ? truncated.AddSeconds(1)
            : truncated;
    }

    private async Task<(int TotalRaw, DateTime? MaiorLastUpdateUtc, DateTime? CursorRetomadaUtc)> ObterEstadoRetomadaAsync(CancellationToken ct)
    {
        const string sql = @"
            SELECT
                COUNT(*) AS TotalRaw,
                MAX(LastUpdateUtc) AS MaiorLastUpdateUtc,
                (
                    SELECT TOP 1 LastUpdateUtc
                    FROM (
                        SELECT
                            LastUpdateUtc,
                            LEAD(LastUpdateUtc) OVER (ORDER BY LastUpdateUtc DESC) AS ProximoLastUpdateUtc
                        FROM raw.Ticket
                        WHERE LastUpdateUtc IS NOT NULL
                    ) AS Ordenado
                    WHERE ProximoLastUpdateUtc IS NULL
                       OR DATEDIFF(DAY, ProximoLastUpdateUtc, LastUpdateUtc) > 14
                    ORDER BY LastUpdateUtc DESC
                ) AS CursorRetomadaUtc
            FROM raw.Ticket;";

        await using var conn = new SqlConnection(_connectionString);
        await conn.OpenAsync(ct);
        await using var cmd = new SqlCommand(sql, conn) { CommandTimeout = 30 };
        await using var reader = await cmd.ExecuteReaderAsync(ct);

        if (await reader.ReadAsync(ct))
        {
            int totalRaw = reader.IsDBNull(0) ? 0 : reader.GetInt32(0);
            DateTime? maior = reader.IsDBNull(1) ? null : reader.GetDateTime(1);
            DateTime? cursor = reader.IsDBNull(2) ? null : reader.GetDateTime(2);
            return (totalRaw, maior, cursor);
        }

        return (0, null, null);
    }

    private async Task<List<string>> ObterContatosPendentesVinculoAsync(CancellationToken ct)
    {
        const string sql = @"
            SELECT c.ClienteId
            FROM core.Dim_Cliente c
            WHERE ISNULL(c.TipoPessoa, 1) = 1
              AND c.EmpresaId IS NULL
              AND NOT EXISTS (
                  SELECT 1 FROM raw.Pessoa rp WHERE rp.PessoaId = c.ClienteId
              )
            ORDER BY c.ClienteId;";

        var lista = new List<string>();
        await using var conn = new SqlConnection(_connectionString);
        await conn.OpenAsync(ct);
        await using var cmd = new SqlCommand(sql, conn) { CommandTimeout = 30 };
        await using var reader = await cmd.ExecuteReaderAsync(ct);

        while (await reader.ReadAsync(ct))
        {
            if (!reader.IsDBNull(0))
            {
                var id = reader.GetString(0);
                if (!string.IsNullOrWhiteSpace(id))
                    lista.Add(id);
            }
        }

        return lista;
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

        // Inclui createdBy e clients($expand=organization) para vincular sempre a Empresa (Organização) real
        string expand = "owner,createdBy,clients($expand=organization),statusHistories,customFieldValues";

        var query = $"$select={select}&$expand={expand}&$top={top}&$skip={skip}&$orderby={Uri.EscapeDataString(orderby)}";
        if (!string.IsNullOrEmpty(filter))
        {
            query += $"&$filter={Uri.EscapeDataString(filter)}";
        }

        string url = $"{_baseUrl}/{rota}?token={Uri.EscapeDataString(_apiToken)}&{query}";
        return await ExecutarGetJsonArrayComRetryAsync(url, rota, ct);
    }

    private async Task<List<JsonElement>> BuscarPessoasAsync(
        int top,
        int skip,
        string orderby,
        string filter,
        CancellationToken ct)
    {
        string select = "id,businessName,corporateName,cpfCnpj,personType,profileType,isActive,createdDate";
        string expand = "relationships";

        var query = $"$select={select}&$expand={expand}&$top={top}&$skip={skip}&$orderby={Uri.EscapeDataString(orderby)}";
        if (!string.IsNullOrEmpty(filter))
        {
            query += $"&$filter={Uri.EscapeDataString(filter)}";
        }

        string url = $"{_baseUrl}/persons?token={Uri.EscapeDataString(_apiToken)}&{query}";
        return await ExecutarGetJsonArrayComRetryAsync(url, "persons", ct);
    }

    private async Task<List<JsonElement>> ExecutarGetJsonArrayComRetryAsync(
        string url,
        string nomeRota,
        CancellationToken ct)
    {
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

                    AppendLog($"[WRN] API Movidesk /{nomeRota} retornou HTTP {statusCode} (tentativa {tentativa}/{maxTentativas}). Aguardando {delaySegundos}s...");
                    await Task.Delay(TimeSpan.FromSeconds(delaySegundos), ct);
                    continue;
                }

                throw new HttpRequestException($"Erro ao consultar /{nomeRota} ({resp.StatusCode}): {erro}");
            }
            catch (OperationCanceledException)
            {
                throw;
            }
            catch (Exception ex) when (ex is not HttpRequestException || ex.Message.Contains("503"))
            {
                if (tentativa == maxTentativas) throw;
                AppendLog($"[WRN] Instabilidade de rede em /{nomeRota} ({tentativa}/{maxTentativas}): {ex.Message}. Tentando novamente em 15s...");
                await Task.Delay(TimeSpan.FromSeconds(15), ct);
            }
        }

        throw new HttpRequestException($"Não foi possível obter resposta de /{nomeRota} após {maxTentativas} tentativas.");
    }

    /// <summary>
    /// Faz MERGE na tabela raw.Ticket e retorna quantos registros foram realmente INSERIDOS (novos)
    /// versus quantos foram ATUALIZADOS (já existiam no banco).
    /// </summary>
    private async Task<(int Inseridos, int Atualizados)> SalvarTicketsRawAsync(
        List<JsonElement> tickets,
        string fonte,
        CancellationToken ct)
    {
        int inseridos = 0;
        int atualizados = 0;

        await using var conn = new SqlConnection(_connectionString);
        await conn.OpenAsync(ct);

        await using var cmd = new SqlCommand(@"
            MERGE raw.Ticket AS T
            USING (
                SELECT @TicketId AS TicketId, @LastUpdateUtc AS LastUpdateUtc, @Payload AS Payload, @Fonte AS Fonte
            ) AS S
            ON T.TicketId = S.TicketId
            WHEN MATCHED AND (T.LastUpdateUtc IS NULL OR S.LastUpdateUtc IS NULL OR T.LastUpdateUtc <> S.LastUpdateUtc OR T.Processado = 0) THEN
                UPDATE SET T.LastUpdateUtc = S.LastUpdateUtc, T.Payload = S.Payload, T.Fonte = S.Fonte, T.Processado = 0
            WHEN NOT MATCHED THEN
                INSERT (TicketId, LastUpdateUtc, Payload, Fonte, Processado)
                VALUES (S.TicketId, S.LastUpdateUtc, S.Payload, S.Fonte, 0)
            OUTPUT $action;", conn);

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

            var acao = await cmd.ExecuteScalarAsync(ct) as string;
            if (string.Equals(acao, "INSERT", StringComparison.OrdinalIgnoreCase))
            {
                inseridos++;
            }
            else if (string.Equals(acao, "UPDATE", StringComparison.OrdinalIgnoreCase))
            {
                atualizados++;
            }
        }

        return (inseridos, atualizados);
    }

    private async Task<(int Inseridos, int Atualizados)> SalvarPessoasRawAsync(
        List<JsonElement> pessoas,
        string fonte,
        CancellationToken ct)
    {
        int inseridos = 0;
        int atualizados = 0;

        await using var conn = new SqlConnection(_connectionString);
        await conn.OpenAsync(ct);

        await using var cmd = new SqlCommand(@"
            MERGE raw.Pessoa AS T
            USING (
                SELECT @PessoaId AS PessoaId, @Payload AS Payload, @Fonte AS Fonte
            ) AS S
            ON T.PessoaId = S.PessoaId
            WHEN MATCHED THEN
                UPDATE SET T.Payload = S.Payload, T.Fonte = S.Fonte, T.CarregadoEm = SYSDATETIME(), T.Processado = 0
            WHEN NOT MATCHED THEN
                INSERT (PessoaId, Payload, Fonte, Processado)
                VALUES (S.PessoaId, S.Payload, S.Fonte, 0)
            OUTPUT $action;", conn);

        cmd.Parameters.Add("@PessoaId", SqlDbType.VarChar, 64);
        cmd.Parameters.Add("@Payload", SqlDbType.NVarChar, -1);
        cmd.Parameters.Add("@Fonte", SqlDbType.VarChar, 20);

        foreach (var p in pessoas)
        {
            ct.ThrowIfCancellationRequested();

            if (!p.TryGetProperty("id", out var idProp)) continue;
            string? id = idProp.ValueKind == JsonValueKind.String
                ? idProp.GetString()
                : idProp.GetRawText();

            if (string.IsNullOrWhiteSpace(id)) continue;

            cmd.Parameters["@PessoaId"].Value = id;
            cmd.Parameters["@Payload"].Value = p.GetRawText();
            cmd.Parameters["@Fonte"].Value = fonte;

            var acao = await cmd.ExecuteScalarAsync(ct) as string;
            if (string.Equals(acao, "INSERT", StringComparison.OrdinalIgnoreCase))
            {
                inseridos++;
            }
            else if (string.Equals(acao, "UPDATE", StringComparison.OrdinalIgnoreCase))
            {
                atualizados++;
            }
        }

        return (inseridos, atualizados);
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

    private async Task ExecutarProcessamentoPessoasCoreAsync(CancellationToken ct)
    {
        await using var conn = new SqlConnection(_connectionString);
        await conn.OpenAsync(ct);
        await using var cmd = new SqlCommand("core.usp_ProcessarPessoas", conn)
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

    private void AtualizarCursorLabel(string cursorLabel)
    {
        lock (_stateLock)
        {
            CurrentCursorLabel = cursorLabel;
        }
        NotifyStateChanged();
    }

    private void RegistrarEstatisticasLote(int lidos, int inseridos, int atualizados)
    {
        lock (_stateLock)
        {
            ProcessedInCurrentRun += lidos;
            NewInsertedInCurrentRun += inseridos;
            UpdatedInCurrentRun += atualizados;
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
