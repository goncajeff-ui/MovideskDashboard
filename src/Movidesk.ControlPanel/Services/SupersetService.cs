using System.Diagnostics;
using System.Net;
using System.Net.Http.Headers;
using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;
using Microsoft.Extensions.Configuration;

namespace Movidesk.ControlPanel.Services;

public enum SupersetStatus
{
    Offline,
    Starting,
    Online,
    Error
}

/// <summary>
/// Orquestra a inicialização do Apache Superset e executa 100% nativamente em C# (via HttpClient)
/// o provisionamento completo da REST API do Superset (Database MovideskDM, 9 Datasets mart e o Dashboard Movidesk),
/// sem depender de chamadas externas ao wsl.exe para o setup.
/// </summary>
public sealed class SupersetService : IDisposable
{
    private readonly string _wslDistro;
    private readonly string _venvActivatePath;
    private readonly string _secretKey;
    private readonly int _port;
    private readonly string _supersetUrl;
    private readonly string _supersetDbUri;
    private readonly bool _hasExplicitDbUri;

    private readonly HttpClient _httpClient = new() { Timeout = TimeSpan.FromSeconds(3) };
    private readonly object _stateLock = new();
    private readonly List<string> _logs = new();
    private readonly List<string> _setupLogs = new();
    private Process? _wslProcess;
    private CancellationTokenSource? _startupCts;

    private static readonly (string ViewName, string? MainDttmCol, string Description)[] MartViews =
    [
        ("vw_VisaoGeralKpis", null, "KPIs Executivos de Topo por Equipe (Backlog, SLA, Vazão Hoje e FCR)"),
        ("vw_SlaRadar", "DataCriacao", "Termômetro Preditivo de Quebra de SLA da Fila Ativa"),
        ("vw_BacklogAging", "DataCriacao", "Envelhecimento da Fila Ativa (Aging) e Sem Interação > 48h"),
        ("vw_StatusAging", null, "Gargalos Operacionais e Tempo Médio Retido por Status"),
        ("vw_BacklogEvolucao", "DataSnapshot", "Curva Histórica Diária do Backlog Total vs SLA Vencido (90 Dias)"),
        ("vw_ThroughputDiario", "Data", "Balanço Diário de Vazão Operacional (Abertos vs Resolvidos)"),
        ("vw_ClienteRaioX", "DataUltimoTicket", "Saúde de Empresas Clientes por Produto/Serviço e Dono Atual (Último Ticket), % SLA e Risco de Churn (> 60d)"),
        ("vw_MapaDemanda", null, "Pareto de Serviços, Categorias, Urgências e Versões de Release (#133948)"),
        ("vw_TicketsPorClientePeriodo", "DataAbertura", "Distribuição de Tickets Abertos por Cliente/Organização e Equipe no Período")
    ];

    public SupersetStatus Status { get; private set; } = SupersetStatus.Offline;
    public string StatusMessage { get; private set; } = "Superset parado";
    public string SupersetUrl => _supersetUrl;
    public string DashboardUrl => $"{_supersetUrl.TrimEnd('/')}/superset/dashboard/dashboard-movidesk/";
    public int Port => _port;
    public string WslDistro => _wslDistro;
    public string VenvActivatePath => _venvActivatePath;

    public bool IsSetupRunning { get; private set; }
    public bool? SetupSucceeded { get; private set; }
    public string SetupStatusMessage { get; private set; } =
        "Pronto para provisionar a conexão MovideskDM, os 9 Datasets (schema mart) e o Dashboard Movidesk.";

    public event Action? OnStateChanged;

    public SupersetService(IConfiguration configuration)
    {
        _wslDistro = configuration["Superset:WslDistro"] ?? "Ubuntu";
        _venvActivatePath = configuration["Superset:VenvActivatePath"] ?? "~/superset-env/bin/activate";
        _secretKey = configuration["Superset:SecretKey"] ?? "movidesk_superset_super_secret_key_2026";
        _port = int.TryParse(configuration["Superset:Port"], out var parsedPort) ? parsedPort : 8088;
        _supersetUrl = (configuration["Superset:Url"] ?? $"http://localhost:{_port}").TrimEnd('/');
        string? configuredDbUri = configuration["Superset:SqlAlchemyUri"];
        _hasExplicitDbUri = !string.IsNullOrWhiteSpace(configuredDbUri);
        _supersetDbUri = string.IsNullOrWhiteSpace(configuredDbUri)
            ? "mssql+pymssql://sa:123456@172.29.112.1:1433/MovideskDM"
            : configuredDbUri.Trim();
    }

    private static string ResolveWslExecutablePath()
    {
        if (!OperatingSystem.IsWindows())
        {
            return "bash";
        }

        string sys32Wsl = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.System), "wsl.exe");
        return File.Exists(sys32Wsl) ? sys32Wsl : "wsl.exe";
    }

    public IReadOnlyList<string> GetLogsSnapshot()
    {
        lock (_stateLock)
        {
            return _logs.ToList();
        }
    }

    public IReadOnlyList<string> GetSetupLogsSnapshot()
    {
        lock (_stateLock)
        {
            return _setupLogs.ToList();
        }
    }

    public void ClearSetupLogs()
    {
        lock (_stateLock)
        {
            if (IsSetupRunning) return;
            _setupLogs.Clear();
            SetupSucceeded = null;
            SetupStatusMessage =
                "Pronto para provisionar a conexão MovideskDM, os 9 Datasets (schema mart) e o Dashboard Movidesk.";
        }
        NotifyStateChanged();
    }

    public void OpenInBrowser()
    {
        try
        {
            Process.Start(new ProcessStartInfo(_supersetUrl) { UseShellExecute = true });
        }
        catch (Exception ex)
        {
            AppendLog($"[AVISO] Não foi possível abrir o navegador automaticamente: {ex.Message}");
        }
    }

    public void OpenDashboardInBrowser()
    {
        try
        {
            Process.Start(new ProcessStartInfo(DashboardUrl) { UseShellExecute = true });
        }
        catch (Exception ex)
        {
            AppendSetupLog($"[AVISO] Não foi possível abrir o navegador automaticamente: {ex.Message}");
        }
    }

    public async Task<bool> CheckHealthAsync(CancellationToken cancellationToken = default)
    {
        bool alive = await ProbeHealthEndpointAsync(cancellationToken);

        lock (_stateLock)
        {
            if (alive)
            {
                Status = SupersetStatus.Online;
                StatusMessage = $"Online em {_supersetUrl}";
            }
            else if (Status == SupersetStatus.Online)
            {
                Status = SupersetStatus.Offline;
                StatusMessage = "Superset desconectado";
            }
        }

        NotifyStateChanged();
        return alive;
    }

    public async Task StartSupersetAsync()
    {
        lock (_stateLock)
        {
            if (Status == SupersetStatus.Starting)
            {
                return;
            }
        }

        if (await ProbeHealthEndpointAsync())
        {
            lock (_stateLock)
            {
                Status = SupersetStatus.Online;
                StatusMessage = $"Superset já está online em {_supersetUrl}";
            }
            AppendLog("Instância existente do Superset detectada e respondendo em /health.");
            NotifyStateChanged();
            return;
        }

        CancellationToken startupToken;
        lock (_stateLock)
        {
            _startupCts?.Cancel();
            _startupCts?.Dispose();
            _startupCts = new CancellationTokenSource();
            startupToken = _startupCts.Token;

            Status = SupersetStatus.Starting;
            StatusMessage = "Subindo WSL2 Ubuntu e inicializando Apache Superset...";
            _logs.Clear();
        }
        NotifyStateChanged();

        string comandoSuperset =
            $"source {_venvActivatePath} && export SUPERSET_SECRET_KEY='{_secretKey}' && exec superset run -h 0.0.0.0 -p {_port} --with-threads";

        AppendLog($"Executando WSL ({(string.IsNullOrWhiteSpace(_wslDistro) ? "distro padrão" : _wslDistro)}): {comandoSuperset}");

        try
        {
            var startInfo = new ProcessStartInfo
            {
                FileName = ResolveWslExecutablePath(),
                UseShellExecute = false,
                CreateNoWindow = true,
                RedirectStandardOutput = true,
                RedirectStandardError = true
            };

            if (OperatingSystem.IsWindows())
            {
                if (!string.IsNullOrWhiteSpace(_wslDistro))
                {
                    startInfo.ArgumentList.Add("-d");
                    startInfo.ArgumentList.Add(_wslDistro);
                }
                startInfo.ArgumentList.Add("-e");
                startInfo.ArgumentList.Add("bash");
                startInfo.ArgumentList.Add("-c");
                startInfo.ArgumentList.Add(comandoSuperset);
            }
            else
            {
                startInfo.ArgumentList.Add("-c");
                startInfo.ArgumentList.Add(comandoSuperset);
            }

            var process = new Process
            {
                StartInfo = startInfo,
                EnableRaisingEvents = true
            };

            process.OutputDataReceived += (_, e) =>
            {
                if (!string.IsNullOrWhiteSpace(e.Data))
                {
                    AppendLog(e.Data);
                }
            };

            process.ErrorDataReceived += (_, e) =>
            {
                if (!string.IsNullOrWhiteSpace(e.Data))
                {
                    AppendLog(e.Data);
                }
            };

            process.Exited += (_, _) =>
            {
                int? exitCode = null;
                try { exitCode = process.ExitCode; } catch { /* Ignora */ }

                lock (_stateLock)
                {
                    if (Status == SupersetStatus.Starting || Status == SupersetStatus.Online)
                    {
                        Status = SupersetStatus.Offline;
                        StatusMessage = exitCode.HasValue
                            ? $"Processo Superset encerrado (código {exitCode.Value})."
                            : "Processo Superset encerrado.";
                    }
                }
                AppendLog(exitCode.HasValue
                    ? $"Processo WSL finalizado com código {exitCode.Value}."
                    : "Processo WSL finalizado.");
                NotifyStateChanged();
            };

            if (!process.Start())
            {
                throw new InvalidOperationException("Não foi possível iniciar o processo wsl.exe.");
            }

            process.BeginOutputReadLine();
            process.BeginErrorReadLine();

            lock (_stateLock)
            {
                _wslProcess = process;
            }

            _ = Task.Run(() => WaitForHealthyAsync(process, startupToken), startupToken);
        }
        catch (Exception ex)
        {
            lock (_stateLock)
            {
                Status = SupersetStatus.Error;
                StatusMessage = $"Erro ao acionar WSL: {ex.Message}";
            }
            AppendLog($"[ERRO] {ex.Message}");
            NotifyStateChanged();
        }
    }

    public async Task StopSupersetAsync()
    {
        try
        {
            lock (_stateLock)
            {
                _startupCts?.Cancel();
                Status = SupersetStatus.Offline;
                StatusMessage = "Superset parado pelo operador.";
            }

            if (OperatingSystem.IsWindows())
            {
                var stopPsi = new ProcessStartInfo
                {
                    FileName = ResolveWslExecutablePath(),
                    UseShellExecute = false,
                    CreateNoWindow = true
                };
                if (!string.IsNullOrWhiteSpace(_wslDistro))
                {
                    stopPsi.ArgumentList.Add("-d");
                    stopPsi.ArgumentList.Add(_wslDistro);
                }
                stopPsi.ArgumentList.Add("-e");
                stopPsi.ArgumentList.Add("bash");
                stopPsi.ArgumentList.Add("-c");
                stopPsi.ArgumentList.Add("pkill -f '[s]uperset run' || true");

                using var stopProc = Process.Start(stopPsi);
                if (stopProc != null)
                {
                    await stopProc.WaitForExitAsync();
                }
            }

            lock (_stateLock)
            {
                if (_wslProcess is { HasExited: false })
                {
                    _wslProcess.Kill(entireProcessTree: true);
                }
                _wslProcess?.Dispose();
                _wslProcess = null;
            }

            AppendLog("Servidor Apache Superset encerrado.");
            NotifyStateChanged();
        }
        catch (Exception ex)
        {
            AppendLog($"[AVISO] Falha ao parar Superset: {ex.Message}");
            NotifyStateChanged();
        }
    }

    // =========================================================================
    // AUTOMAÇÃO 100% NATIVA EM C# (HTTPCLIENT DIRETO EM localhost:8088)
    // Zero dependência de wsl.exe / Python externo — imune a erros Win32!
    // =========================================================================

    private sealed class DatasetMetadata
    {
        public int Id { get; init; }
        public string Uuid { get; init; } = string.Empty;
        public Dictionary<string, (int? Id, string Type)> Columns { get; init; } = new(StringComparer.OrdinalIgnoreCase);
    }

    private sealed class ChartMetadata
    {
        public int Id { get; init; }
        public string Uuid { get; init; } = string.Empty;
        public string Title { get; init; } = string.Empty;
    }

    /// <summary>
    /// Executa o setup completo do Apache Superset 100% nativamente em C# via HttpClient
    /// consumindo diretamente a REST API em http://localhost:8088 (sem invocar wsl.exe).
    /// </summary>
    public async Task RunAutoSetupAsync(string adminPassword, string adminUsername = "admin")
    {
        lock (_stateLock)
        {
            if (IsSetupRunning)
            {
                return;
            }
        }

        if (string.IsNullOrWhiteSpace(adminPassword))
        {
            lock (_stateLock)
            {
                SetupSucceeded = false;
                SetupStatusMessage = "Informe a senha do usuário admin antes de executar o setup.";
            }
            AppendSetupLog("[AVISO] Digite a senha do usuário admin do Apache Superset no campo acima.");
            return;
        }

        lock (_stateLock)
        {
            IsSetupRunning = true;
            SetupSucceeded = null;
            SetupStatusMessage = "Conectando diretamente à REST API do Apache Superset (C# HttpClient)...";
            _setupLogs.Clear();
        }
        NotifyStateChanged();

        try
        {
            AppendSetupLog("[INF] Iniciando automação nativa em C# (comunicação HTTP direta com Apache Superset, sem uso de terminal/WSL)...");

            if (!await ProbeHealthEndpointAsync())
            {
                AppendSetupLog($"[AVISO] Superset não respondeu em {_supersetUrl}/health. Tentando iniciar servidor automaticamente...");
                await StartSupersetAsync();
                for (int i = 0; i < 25; i++)
                {
                    await Task.Delay(1500);
                    if (await ProbeHealthEndpointAsync())
                    {
                        break;
                    }
                }

                if (!await ProbeHealthEndpointAsync())
                {
                    throw new InvalidOperationException(
                        $"O Apache Superset não está respondendo em {_supersetUrl}/health. " +
                        "Certifique-se de que o Superset está online no Card 1 ('Iniciar Superset') antes de executar o setup.");
                }
            }

            AppendSetupLog($"[OK] Servidor Apache Superset online em {_supersetUrl}.");

            var cookieContainer = new CookieContainer();
            using var handler = new HttpClientHandler
            {
                UseCookies = true,
                CookieContainer = cookieContainer
            };
            using var apiClient = new HttpClient(handler)
            {
                BaseAddress = new Uri(_supersetUrl),
                Timeout = TimeSpan.FromMinutes(5)
            };
            apiClient.DefaultRequestHeaders.Accept.Add(new MediaTypeWithQualityHeaderValue("application/json"));
            apiClient.DefaultRequestHeaders.Referrer = new Uri($"{_supersetUrl}/");

            // 1. Autenticação JWT + CSRF Token
            string username = string.IsNullOrWhiteSpace(adminUsername) ? "admin" : adminUsername.Trim();
            string accessToken = await AuthenticateSupersetAsync(apiClient, username, adminPassword);
            apiClient.DefaultRequestHeaders.Authorization = new AuthenticationHeaderValue("Bearer", accessToken);

            string? csrfToken = await FetchCsrfTokenAsync(apiClient);
            if (!string.IsNullOrWhiteSpace(csrfToken))
            {
                apiClient.DefaultRequestHeaders.Remove("X-CSRFToken");
                apiClient.DefaultRequestHeaders.Add("X-CSRFToken", csrfToken);
            }

            AppendSetupLog($"[OK] Autenticado na REST API do Superset ({_supersetUrl}) como '{username}'.");

            // 2. Passo 1/3: Criar ou Atualizar Database MovideskDM
            AppendSetupLog("[INF] Passo 1/3 — Verificando conexão Database 'MovideskDM'...");
            int dbId = await UpsertDatabaseAsync(apiClient, "MovideskDM", _supersetDbUri);

            // 3. Passo 2/3: Criar ou Sincronizar os 9 Datasets do schema mart
            AppendSetupLog($"[INF] Passo 2/3 — Sincronizando {MartViews.Length} Datasets (schema 'mart') e protegendo filtro 'Equipe'...");
            Dictionary<string, DatasetMetadata> datasets = await UpsertDatasetsAsync(apiClient, dbId);

            // 4. Passo 3/3: Criar os 15 Gráficos e Publicar o Dashboard "Dashboard - Movidesk BI"
            AppendSetupLog("[INF] Passo 3/3 — Construindo/atualizando os 15 gráficos e publicando o 'Dashboard - Movidesk BI'...");
            string dashUrl = await BuildMovideskDashboardAsync(apiClient, datasets);

            lock (_stateLock)
            {
                IsSetupRunning = false;
                SetupSucceeded = true;
                SetupStatusMessage = "Setup concluído com sucesso! Database MovideskDM, 9 Datasets (mart) e o Dashboard Movidesk publicados.";
            }
            AppendSetupLog($"[OK] SETUP CONCLUÍDO COM SUCESSO! Acesse: {dashUrl}");
            NotifyStateChanged();

            await CheckHealthAsync();
        }
        catch (Exception ex)
        {
            lock (_stateLock)
            {
                IsSetupRunning = false;
                SetupSucceeded = false;
                SetupStatusMessage = $"Erro no setup automático: {ex.Message}";
            }
            AppendSetupLog($"[ERRO] {ex.Message}");
            NotifyStateChanged();
        }
    }

    private async Task<string> AuthenticateSupersetAsync(HttpClient apiClient, string username, string password)
    {
        var loginPayload = new JsonObject
        {
            ["username"] = username,
            ["password"] = password,
            ["provider"] = "db",
            ["refresh"] = true
        };

        var (status, body) = await SendJsonRawAsync(apiClient, HttpMethod.Post, "/api/v1/security/login", loginPayload, timeoutSeconds: 60);
        if (status == HttpStatusCode.Unauthorized)
        {
            throw new InvalidOperationException(
                $"Senha incorreta para o usuário '{username}' no Apache Superset (HTTP 401 UNAUTHORIZED). " +
                "Verifique a senha digitada (a mesma que você usa para logar em http://localhost:8088).");
        }

        if ((int)status < 200 || (int)status >= 300)
        {
            throw new InvalidOperationException($"Falha no login do Superset (HTTP {(int)status}): {body}");
        }

        var json = JsonNode.Parse(body)?.AsObject();
        string? token = json?["access_token"]?.GetValue<string>();
        if (string.IsNullOrWhiteSpace(token))
        {
            throw new InvalidOperationException($"O Superset não retornou access_token no login: {body}");
        }

        return token;
    }

    private async Task<string?> FetchCsrfTokenAsync(HttpClient apiClient)
    {
        var (status, body) = await SendJsonRawAsync(apiClient, HttpMethod.Get, "/api/v1/security/csrf_token/", null, timeoutSeconds: 45);
        if ((int)status >= 200 && (int)status < 300 && !string.IsNullOrWhiteSpace(body))
        {
            var json = JsonNode.Parse(body)?.AsObject();
            return json?["result"]?.GetValue<string>();
        }
        return null;
    }

    private async Task<int> UpsertDatabaseAsync(HttpClient apiClient, string dbName, string dbUri)
    {
        var listJson = await SendJsonCheckedAsync(apiClient, HttpMethod.Get, "/api/v1/database/?q=(page_size:100)", null, timeoutSeconds: 60);
        int? existingId = null;
        if (listJson["result"] is JsonArray arr)
        {
            foreach (JsonNode? item in arr)
            {
                if (string.Equals(item?["database_name"]?.GetValue<string>(), dbName, StringComparison.OrdinalIgnoreCase))
                {
                    existingId = item?["id"]?.GetValue<int>();
                    break;
                }
            }
        }

        var payload = new JsonObject
        {
            ["database_name"] = dbName,
            ["expose_in_sqllab"] = true,
            ["allow_ctas"] = false,
            ["allow_cvas"] = false,
            ["allow_dml"] = false,
            ["allow_run_async"] = false
        };

        if (existingId.HasValue)
        {
            bool preserveExistingUri = false;
            if (!_hasExplicitDbUri)
            {
                try
                {
                    var (dbDetailStatus, dbDetailBody) = await SendJsonRawAsync(
                        apiClient, HttpMethod.Get, $"/api/v1/database/{existingId.Value}", null, timeoutSeconds: 60);
                    if ((int)dbDetailStatus >= 200 && (int)dbDetailStatus < 300 && !string.IsNullOrWhiteSpace(dbDetailBody))
                    {
                        string? existingUri = JsonNode.Parse(dbDetailBody)?["result"]?["sqlalchemy_uri"]?.GetValue<string>();
                        if (!string.IsNullOrWhiteSpace(existingUri) &&
                            existingUri.Contains("MovideskDM", StringComparison.OrdinalIgnoreCase))
                        {
                            preserveExistingUri = true;
                        }
                    }
                }
                catch
                {
                    // Se não foi possível ler detalhes, segue fluxo padrão abaixo
                }
            }

            if (!preserveExistingUri)
            {
                payload["sqlalchemy_uri"] = dbUri;
            }

            try
            {
                await SendJsonCheckedAsync(
                    apiClient, HttpMethod.Put, $"/api/v1/database/{existingId.Value}", payload, timeoutSeconds: 90, maxRetries: 1);
                AppendSetupLog(preserveExistingUri
                    ? $"[OK] Passo 1/3 — Database '{dbName}' (ID={existingId.Value}) validada preservando URI existente."
                    : $"[OK] Passo 1/3 — Database '{dbName}' (ID={existingId.Value}) atualizada com sucesso.");
            }
            catch (Exception dbPutEx)
            {
                AppendSetupLog(
                    $"[AVISO] Passo 1/3 — Timeout/aviso ao atualizar metadados da Database '{dbName}' (ID={existingId.Value}): {dbPutEx.Message}. Prosseguindo com a conexão existente.");
            }
            return existingId.Value;
        }

        payload["sqlalchemy_uri"] = dbUri;
        var created = await SendJsonCheckedAsync(apiClient, HttpMethod.Post, "/api/v1/database/", payload, timeoutSeconds: 120, maxRetries: 1);
        int newId = created["id"]?.GetValue<int>()
            ?? throw new InvalidOperationException("Superset não retornou o ID da Database criada.");
        AppendSetupLog($"[OK] Passo 1/3 — Database '{dbName}' (ID={newId}) criada com sucesso.");
        return newId;
    }

    private static readonly string[] EditableDatasetColumnKeys =
    [
        "id", "column_name", "type", "is_dttm", "groupby", "filterable",
        "is_active", "description", "verbose_name", "expression", "extra",
        "python_date_format", "datetime_format", "advanced_data_type",
        "certified_by", "certification_details", "is_certified", "uuid",
        "warning_markdown"
    ];

    private async Task<Dictionary<string, DatasetMetadata>> UpsertDatasetsAsync(HttpClient apiClient, int dbId)
    {
        var listJson = await SendJsonCheckedAsync(apiClient, HttpMethod.Get, "/api/v1/dataset/?q=(page_size:200)", null, timeoutSeconds: 60);
        var existingMap = new Dictionary<string, int>(StringComparer.OrdinalIgnoreCase);

        if (listJson["result"] is JsonArray arr)
        {
            foreach (JsonNode? row in arr)
            {
                string? tableName = row?["table_name"]?.GetValue<string>();
                string? schema = row?["schema"]?.GetValue<string>();
                int? id = row?["id"]?.GetValue<int>();
                if (!string.IsNullOrWhiteSpace(tableName) && id.HasValue &&
                    (string.Equals(schema, "mart", StringComparison.OrdinalIgnoreCase) || string.IsNullOrWhiteSpace(schema)))
                {
                    existingMap[tableName] = id.Value;
                }
            }
        }

        var result = new Dictionary<string, DatasetMetadata>(StringComparer.OrdinalIgnoreCase);
        int idx = 0;

        foreach (var (viewName, mainDttmCol, description) in MartViews)
        {
            idx++;
            AppendSetupLog($"[INF] Passo 2/3 — Sincronizando 'mart.{viewName}' ({idx}/{MartViews.Length})...");

            int dsId;
            if (existingMap.TryGetValue(viewName, out int foundId))
            {
                dsId = foundId;
                try
                {
                    var (refreshStatus, refreshBody) = await SendJsonRawAsync(
                        apiClient, HttpMethod.Put, $"/api/v1/dataset/{dsId}/refresh", null, timeoutSeconds: 90, maxRetries: 1);
                    if ((int)refreshStatus < 200 || (int)refreshStatus >= 300)
                    {
                        AppendSetupLog($"[AVISO] Refresh de colunas em 'mart.{viewName}' retornou HTTP {(int)refreshStatus}: {refreshBody}");
                    }
                }
                catch (Exception refreshEx)
                {
                    AppendSetupLog($"[AVISO] Refresh de colunas em 'mart.{viewName}' ignorado ({refreshEx.Message}); mantendo metadados existentes.");
                }
            }
            else
            {
                var createPayload = new JsonObject
                {
                    ["database"] = dbId,
                    ["schema"] = "mart",
                    ["table_name"] = viewName
                };
                var created = await SendJsonCheckedAsync(apiClient, HttpMethod.Post, "/api/v1/dataset/", createPayload, timeoutSeconds: 90, maxRetries: 1);
                dsId = created["id"]?.GetValue<int>()
                    ?? throw new InvalidOperationException($"Não foi possível obter o ID do dataset {viewName}.");
            }

            var detailJson = await SendJsonCheckedAsync(apiClient, HttpMethod.Get, $"/api/v1/dataset/{dsId}", null);
            var detailResult = detailJson["result"]?.AsObject();

            try
            {
                var updatePayload = new JsonObject
                {
                    ["description"] = description,
                    ["filter_select_enabled"] = true
                };

                if (!string.IsNullOrWhiteSpace(mainDttmCol))
                {
                    updatePayload["main_dttm_col"] = mainDttmCol;
                }

                if (detailResult?["columns"] is JsonArray rawCols && rawCols.Count > 0)
                {
                    bool needsColumnUpdate = false;
                    var updatedCols = new JsonArray();

                    foreach (JsonNode? rawColNode in rawCols)
                    {
                        if (rawColNode is not JsonObject rawCol) continue;

                        string? cName = rawCol["column_name"]?.GetValue<string>();
                        if (string.IsNullOrWhiteSpace(cName)) continue;

                        bool isMainDttm = !string.IsNullOrWhiteSpace(mainDttmCol) &&
                            string.Equals(cName, mainDttmCol, StringComparison.OrdinalIgnoreCase);
                        bool isDimChave = string.Equals(cName, "Equipe", StringComparison.OrdinalIgnoreCase) ||
                            string.Equals(cName, "Servico", StringComparison.OrdinalIgnoreCase);

                        bool currIsDttm = rawCol["is_dttm"]?.GetValue<bool>() ?? false;
                        bool currGroupby = rawCol["groupby"]?.GetValue<bool>() ?? true;
                        bool currFilterable = rawCol["filterable"]?.GetValue<bool>() ?? true;

                        bool targetIsDttm = currIsDttm || isMainDttm;
                        bool targetGroupby = isDimChave ? true : currGroupby;
                        bool targetFilterable = isDimChave ? true : currFilterable;

                        if (targetIsDttm != currIsDttm ||
                            targetGroupby != currGroupby ||
                            targetFilterable != currFilterable)
                        {
                            needsColumnUpdate = true;
                        }

                        var colCopy = new JsonObject();
                        foreach (string key in EditableDatasetColumnKeys)
                        {
                            if (rawCol.TryGetPropertyValue(key, out JsonNode? propVal) && propVal is not null)
                            {
                                colCopy[key] = propVal.DeepClone();
                            }
                        }

                        colCopy["column_name"] = cName;
                        if (colCopy["type"] is null) colCopy["type"] = "STRING";
                        colCopy["is_dttm"] = targetIsDttm;
                        colCopy["groupby"] = targetGroupby;
                        colCopy["filterable"] = targetFilterable;

                        updatedCols.Add(colCopy);
                    }

                    if (needsColumnUpdate && updatedCols.Count > 0)
                    {
                        updatePayload["columns"] = updatedCols;
                    }
                }

                var (putStatus, _) = await SendJsonRawAsync(apiClient, HttpMethod.Put, $"/api/v1/dataset/{dsId}", updatePayload);
                if ((int)putStatus < 200 || (int)putStatus >= 300)
                {
                    // Fallback seguro sem o array columns caso o Superset recuse alteração em colunas
                    var fallbackPayload = new JsonObject
                    {
                        ["description"] = description,
                        ["filter_select_enabled"] = true
                    };
                    if (!string.IsNullOrWhiteSpace(mainDttmCol))
                    {
                        fallbackPayload["main_dttm_col"] = mainDttmCol;
                    }
                    await SendJsonRawAsync(apiClient, HttpMethod.Put, $"/api/v1/dataset/{dsId}", fallbackPayload);
                }

                detailJson = await SendJsonCheckedAsync(apiClient, HttpMethod.Get, $"/api/v1/dataset/{dsId}", null);
                detailResult = detailJson["result"]?.AsObject();
            }
            catch
            {
                // Mantém os metadados recuperados no GET inicial
            }

            string uuid = detailResult?["uuid"]?.GetValue<string>() ?? string.Empty;

            var cols = new Dictionary<string, (int? Id, string Type)>(StringComparer.OrdinalIgnoreCase);
            if (detailResult?["columns"] is JsonArray colsArr)
            {
                foreach (JsonNode? colNode in colsArr)
                {
                    string? colName = colNode?["column_name"]?.GetValue<string>();
                    if (!string.IsNullOrWhiteSpace(colName))
                    {
                        int? colId = colNode?["id"]?.GetValue<int>();
                        string colType = colNode?["type"]?.GetValue<string>() ?? "NUMERIC";
                        cols[colName] = (colId, colType);
                    }
                }
            }

            result[viewName] = new DatasetMetadata
            {
                Id = dsId,
                Uuid = uuid,
                Columns = cols
            };

            AppendSetupLog($"[OK] Passo 2/3 — Dataset 'mart.{viewName}' (ID={dsId}, {cols.Count} colunas) sincronizado.");
        }

        return result;
    }

    private static string ResolveColName(DatasetMetadata ds, string targetCol)
    {
        foreach (string key in ds.Columns.Keys)
        {
            if (string.Equals(key, targetCol, StringComparison.OrdinalIgnoreCase))
            {
                return key;
            }
        }
        return targetCol;
    }

    private static JsonArray FilterExistingCols(DatasetMetadata ds, params string[] desiredCols)
    {
        var arr = new JsonArray();
        if (ds.Columns.Count == 0)
        {
            foreach (string c in desiredCols) arr.Add(c);
            return arr;
        }

        foreach (string c in desiredCols)
        {
            string actual = ResolveColName(ds, c);
            if (ds.Columns.ContainsKey(actual))
            {
                arr.Add(actual);
            }
        }

        if (arr.Count == 0)
        {
            foreach (string c in desiredCols) arr.Add(c);
        }

        return arr;
    }

    private static JsonObject MakeSimpleMetric(
        DatasetMetadata ds,
        string colName,
        string aggregate,
        string label,
        string? customOptionName = null)
    {
        string actualCol = ResolveColName(ds, colName);
        var colObj = new JsonObject
        {
            ["column_name"] = actualCol,
            ["type"] = ds.Columns.TryGetValue(actualCol, out var meta) ? meta.Type : "NUMERIC"
        };
        if (ds.Columns.TryGetValue(actualCol, out var metaWithId) && metaWithId.Id.HasValue)
        {
            colObj["id"] = metaWithId.Id.Value;
        }

        string optionName = string.IsNullOrWhiteSpace(customOptionName)
            ? $"metric_{actualCol.ToLowerInvariant()}_{aggregate.ToLowerInvariant()}"
            : customOptionName;

        return new JsonObject
        {
            ["expressionType"] = "SIMPLE",
            ["column"] = colObj,
            ["aggregate"] = aggregate,
            ["label"] = label,
            ["optionName"] = optionName
        };
    }

    private async Task<JsonArray> GetMergedChartDashboardsAsync(
        HttpClient apiClient,
        int chartId,
        int requiredDashboardId)
    {
        var ids = new HashSet<int> { requiredDashboardId };
        try
        {
            var (status, body) = await SendJsonRawAsync(apiClient, HttpMethod.Get, $"/api/v1/chart/{chartId}", null, timeoutSeconds: 60);
            if ((int)status >= 200 && (int)status < 300 && !string.IsNullOrWhiteSpace(body))
            {
                var detail = JsonNode.Parse(body)?.AsObject();
                if (detail?["result"]?["dashboards"] is JsonArray dashArr)
                {
                    foreach (JsonNode? item in dashArr)
                    {
                        if (item is JsonObject obj && obj["id"]?.GetValue<int>() is int objId)
                        {
                            ids.Add(objId);
                        }
                        else if (item is JsonValue val && val.TryGetValue<int>(out int rawId))
                        {
                            ids.Add(rawId);
                        }
                    }
                }
            }
        }
        catch
        {
            // Mantém ao menos requiredDashboardId
        }

        var result = new JsonArray();
        foreach (int id in ids)
        {
            result.Add(id);
        }
        return result;
    }

    private async Task<ChartMetadata> UpsertChartAsync(
        HttpClient apiClient,
        Dictionary<string, int> existingCharts,
        string sliceName,
        string vizType,
        int dsId,
        int dashboardId,
        JsonObject paramsObj,
        string description)
    {
        paramsObj["datasource"] = $"{dsId}__table";
        paramsObj["viz_type"] = vizType;

        JsonArray mergedDashboards = existingCharts.TryGetValue(sliceName, out int foundId)
            ? await GetMergedChartDashboardsAsync(apiClient, foundId, dashboardId)
            : new JsonArray(dashboardId);

        var payload = new JsonObject
        {
            ["slice_name"] = sliceName,
            ["viz_type"] = vizType,
            ["datasource_id"] = dsId,
            ["datasource_type"] = "table",
            ["dashboards"] = mergedDashboards,
            ["description"] = description,
            ["params"] = paramsObj.ToJsonString()
        };

        int chartId;
        if (existingCharts.TryGetValue(sliceName, out foundId))
        {
            chartId = foundId;
            await SendJsonCheckedAsync(apiClient, HttpMethod.Put, $"/api/v1/chart/{chartId}", payload, timeoutSeconds: 90);
        }
        else
        {
            var created = await SendJsonCheckedAsync(apiClient, HttpMethod.Post, "/api/v1/chart/", payload, timeoutSeconds: 90);
            chartId = created["id"]?.GetValue<int>()
                ?? throw new InvalidOperationException($"Não foi possível obter o ID do gráfico '{sliceName}'.");
        }

        var detail = await SendJsonCheckedAsync(apiClient, HttpMethod.Get, $"/api/v1/chart/{chartId}", null, timeoutSeconds: 60);
        string uuid = detail["result"]?["uuid"]?.GetValue<string>() ?? string.Empty;

        AppendSetupLog($"[OK] Gráfico '{sliceName}' (ID={chartId}) vinculado ao Dashboard Movidesk.");
        return new ChartMetadata
        {
            Id = chartId,
            Uuid = uuid,
            Title = sliceName
        };
    }

    private async Task<string> BuildMovideskDashboardAsync(
        HttpClient apiClient,
        Dictionary<string, DatasetMetadata> datasets)
    {
        const string dashTitle = "Dashboard - Movidesk BI";
        const string dashSlug = "dashboard-movidesk";

        var dashList = await SendJsonCheckedAsync(apiClient, HttpMethod.Get, "/api/v1/dashboard/?q=(page_size:100)", null, timeoutSeconds: 60);
        int? dashboardId = null;
        int? legacyDashboardId = null;
        if (dashList["result"] is JsonArray dashArr)
        {
            foreach (JsonNode? row in dashArr)
            {
                string? slug = row?["slug"]?.GetValue<string>();
                string? title = row?["dashboard_title"]?.GetValue<string>();
                int? rowId = row?["id"]?.GetValue<int>();
                if (!rowId.HasValue) continue;

                if (string.Equals(slug, dashSlug, StringComparison.OrdinalIgnoreCase) ||
                    string.Equals(title, dashTitle, StringComparison.OrdinalIgnoreCase))
                {
                    dashboardId = rowId.Value;
                    break;
                }

                if (!legacyDashboardId.HasValue &&
                    (string.Equals(slug, "sala-de-guerra-movidesk", StringComparison.OrdinalIgnoreCase) ||
                     string.Equals(title, "Sala de Guerra - Movidesk BI", StringComparison.OrdinalIgnoreCase)))
                {
                    legacyDashboardId = rowId.Value;
                }
            }
        }

        if (!dashboardId.HasValue && legacyDashboardId.HasValue)
        {
            dashboardId = legacyDashboardId.Value;
            AppendSetupLog($"[INF] Dashboard anterior 'Sala de Guerra - Movidesk BI' detectado (ID={dashboardId.Value}). Migrando para '{dashTitle}' ({dashSlug})...");
        }

        if (!dashboardId.HasValue)
        {
            var createDash = await SendJsonCheckedAsync(
                apiClient,
                HttpMethod.Post,
                "/api/v1/dashboard/",
                new JsonObject
                {
                    ["dashboard_title"] = dashTitle,
                    ["slug"] = dashSlug,
                    ["published"] = true
                },
                timeoutSeconds: 90);
            dashboardId = createDash["id"]?.GetValue<int>()
                ?? throw new InvalidOperationException("Não foi possível obter o ID do Dashboard criado.");
        }

        var chartsList = await SendJsonCheckedAsync(apiClient, HttpMethod.Get, "/api/v1/chart/?q=(page_size:200)", null, timeoutSeconds: 60);
        var existingCharts = new Dictionary<string, int>(StringComparer.OrdinalIgnoreCase);
        if (chartsList["result"] is JsonArray chartArr)
        {
            foreach (JsonNode? row in chartArr)
            {
                string? name = row?["slice_name"]?.GetValue<string>();
                int? id = row?["id"]?.GetValue<int>();
                if (!string.IsNullOrWhiteSpace(name) && id.HasValue)
                {
                    existingCharts[name] = id.Value;
                }
            }
        }

        var dsKpis = datasets["vw_VisaoGeralKpis"];
        var dsRadar = datasets["vw_SlaRadar"];
        var dsEvol = datasets["vw_BacklogEvolucao"];
        var dsThrough = datasets["vw_ThroughputDiario"];
        var dsAging = datasets["vw_BacklogAging"];
        var dsStatus = datasets["vw_StatusAging"];
        var dsDemanda = datasets["vw_MapaDemanda"];
        var dsClientes = datasets["vw_ClienteRaioX"];
        var dsClientesPeriodo = datasets["vw_TicketsPorClientePeriodo"];

        var chartSpecs = new (string Key, string Title, string VizType, int DsId, JsonObject Params, string Desc)[]
        {
            ("KPI_BACKLOG", "KPI - Backlog Atual", "big_number_total", dsKpis.Id, new JsonObject
            {
                ["metric"] = MakeSimpleMetric(dsKpis, "BacklogAtual", "SUM", "Backlog Atual"),
                ["subheader"] = "Chamados Ativos na Fila",
                ["y_axis_format"] = ",d",
                ["header_font_size"] = 0.4,
                ["subheader_font_size"] = 0.15,
                ["adhoc_filters"] = new JsonArray()
            }, "Volume exato de chamados em aberto no momento atual."),

            ("KPI_VENCIDOS", "KPI - SLA Vencidos", "big_number_total", dsKpis.Id, new JsonObject
            {
                ["metric"] = MakeSimpleMetric(dsKpis, "SlaVencidos", "SUM", "SLA Vencidos"),
                ["subheader"] = "Abertos Fora do Prazo",
                ["y_axis_format"] = ",d",
                ["header_font_size"] = 0.4,
                ["subheader_font_size"] = 0.15,
                ["adhoc_filters"] = new JsonArray()
            }, "Chamados em aberto cujo SlaDataSolucao já expirou."),

            ("KPI_IMINENTE", "KPI - SLA Iminente (< 4h)", "big_number_total", dsKpis.Id, new JsonObject
            {
                ["metric"] = MakeSimpleMetric(dsKpis, "SlaIminente4h", "SUM", "SLA < 4h"),
                ["subheader"] = "Expirando nas Próximas 4h",
                ["y_axis_format"] = ",d",
                ["header_font_size"] = 0.4,
                ["subheader_font_size"] = 0.15,
                ["adhoc_filters"] = new JsonArray()
            }, "Chamados abertos que vencem nas próximas 4 horas."),

            ("KPI_ABERTOS_HOJE", "KPI - Abertos Hoje", "big_number_total", dsKpis.Id, new JsonObject
            {
                ["metric"] = MakeSimpleMetric(dsKpis, "AbertosHoje", "SUM", "Abertos Hoje"),
                ["subheader"] = "Novos Chamados no Dia",
                ["y_axis_format"] = ",d",
                ["header_font_size"] = 0.4,
                ["subheader_font_size"] = 0.15,
                ["adhoc_filters"] = new JsonArray()
            }, "Total de chamados abertos na data de hoje (BRT)."),

            ("KPI_RESOLVIDOS_HOJE", "KPI - Resolvidos Hoje", "big_number_total", dsKpis.Id, new JsonObject
            {
                ["metric"] = MakeSimpleMetric(dsKpis, "ResolvidosHoje", "SUM", "Resolvidos Hoje"),
                ["subheader"] = "Solucionados no Dia",
                ["y_axis_format"] = ",d",
                ["header_font_size"] = 0.4,
                ["subheader_font_size"] = 0.15,
                ["adhoc_filters"] = new JsonArray()
            }, "Total de chamados resolvidos na data de hoje (BRT)."),

            ("KPI_FCR", "KPI - FCR 30 Dias (%)", "big_number_total", dsKpis.Id, new JsonObject
            {
                ["metric"] = MakeSimpleMetric(dsKpis, "FcrUltimos30DiasPct", "AVG", "FCR 30d (%)"),
                ["subheader"] = "Resolução no 1º Contato",
                ["y_axis_format"] = ".1f",
                ["header_font_size"] = 0.4,
                ["subheader_font_size"] = 0.15,
                ["adhoc_filters"] = new JsonArray()
            }, "Taxa média de First Contact Resolution nos últimos 30 dias."),

            ("TABELA_RADAR_SLA", "Radar Preditivo de SLA (Fila Viva)", "table", dsRadar.Id, new JsonObject
            {
                ["query_mode"] = "raw",
                ["all_columns"] = FilterExistingCols(dsRadar,
                    "OrdemGravidade", "FaixaRiscoSla", "MinutosParaVencer", "TicketId", "Cliente",
                    "Servico", "Assunto", "Equipe", "Analista", "Urgencia", "Status", "HorasSemInteracao"),
                ["order_by_cols"] = new JsonArray("[\"OrdemGravidade\", true]", "[\"MinutosParaVencer\", true]"),
                ["row_limit"] = 500,
                ["page_length"] = 20,
                ["include_search"] = true,
                ["show_cell_bars"] = true,
                ["adhoc_filters"] = new JsonArray()
            }, "Fila ativa ordenada por gravidade de risco de quebra de SLA."),

            ("SERIE_BACKLOG_90D", "Evolução Diária do Backlog e SLA Vencido (90 Dias)", "echarts_area", dsEvol.Id, new JsonObject
            {
                ["x_axis"] = "DataSnapshot",
                ["granularity_sqla"] = "DataSnapshot",
                ["time_grain_sqla"] = "P1D",
                ["x_axis_sort_asc"] = true,
                ["metrics"] = new JsonArray(
                    MakeSimpleMetric(dsEvol, "QtdTickets", "SUM", "Backlog Total"),
                    MakeSimpleMetric(dsEvol, "QtdSlaVencido", "SUM", "SLA Vencido")),
                ["groupby"] = new JsonArray(),
                ["adhoc_filters"] = new JsonArray(
                    new JsonObject
                    {
                        ["clause"] = "WHERE",
                        ["comparator"] = "No filter",
                        ["datasourceWarning"] = false,
                        ["expressionType"] = "SIMPLE",
                        ["filterOptionName"] = "filter_datasnapshot_temporal",
                        ["isExtra"] = false,
                        ["isNew"] = false,
                        ["operator"] = "TEMPORAL_RANGE",
                        ["sqlExpression"] = null,
                        ["subject"] = "DataSnapshot"
                    }),
                ["row_limit"] = 10000,
                ["show_legend"] = true,
                ["rich_tooltip"] = true,
                ["area"] = true,
                ["opacity"] = 0.25
            }, "Fotografia histórica diária da fila aberta vs chamados com SLA vencido."),

            ("SERIE_THROUGHPUT", "Throughput Diário: Abertos vs Resolvidos", "echarts_timeseries_bar", dsThrough.Id, new JsonObject
            {
                ["x_axis"] = "Data",
                ["granularity_sqla"] = "Data",
                ["time_grain_sqla"] = "P1D",
                ["x_axis_sort_asc"] = true,
                ["metrics"] = new JsonArray(
                    MakeSimpleMetric(dsThrough, "Abertos", "SUM", "Abertos"),
                    MakeSimpleMetric(dsThrough, "Resolvidos", "SUM", "Resolvidos")),
                ["groupby"] = new JsonArray(),
                ["adhoc_filters"] = new JsonArray(
                    new JsonObject
                    {
                        ["clause"] = "WHERE",
                        ["comparator"] = "No filter",
                        ["datasourceWarning"] = false,
                        ["expressionType"] = "SIMPLE",
                        ["filterOptionName"] = "filter_data_temporal",
                        ["isExtra"] = false,
                        ["isNew"] = false,
                        ["operator"] = "TEMPORAL_RANGE",
                        ["sqlExpression"] = null,
                        ["subject"] = "Data"
                    }),
                ["row_limit"] = 5000,
                ["show_legend"] = true,
                ["rich_tooltip"] = true
            }, "Vazão diária comparando entrada de chamados vs resoluções."),

            ("TABELA_BACKLOG_AGING", "Auditoria de Envelhecimento (Backlog Aging & +48h Sem Ação)", "table", dsAging.Id, new JsonObject
            {
                ["query_mode"] = "raw",
                ["all_columns"] = FilterExistingCols(dsAging,
                    "TicketId", "Cliente", "Servico", "Assunto", "Equipe",
                    "Analista", "FaixaIdade", "DiasAberto", "HorasDesdeUltimaAcao", "SemInteracaoMais48h"),
                ["order_by_cols"] = new JsonArray("[\"DiasAberto\", false]"),
                ["row_limit"] = 500,
                ["page_length"] = 15,
                ["include_search"] = true,
                ["show_cell_bars"] = true,
                ["adhoc_filters"] = new JsonArray()
            }, "Chamados em aberto classificados por faixa de idade e alerta de inatividade (>48h)."),

            ("TABELA_STATUS_AGING", "Gargalos Operacionais por Status (Horas Úteis e Corridas)", "table", dsStatus.Id, new JsonObject
            {
                ["query_mode"] = "raw",
                ["all_columns"] = FilterExistingCols(dsStatus,
                    "Equipe", "Status", "GrupoStatus", "QtdPassagens",
                    "HorasUteisMedias", "HorasCorridasMedias", "HorasCorridasTotais"),
                ["order_by_cols"] = new JsonArray("[\"HorasCorridasTotais\", false]"),
                ["row_limit"] = 200,
                ["page_length"] = 15,
                ["include_search"] = true,
                ["show_cell_bars"] = true,
                ["adhoc_filters"] = new JsonArray()
            }, "Tempo médio e acumulado retido em cada status do fluxo."),

            ("TABELA_MAPA_DEMANDA", "Mapa de Demanda por Serviço, Categoria e Versão Release", "table", dsDemanda.Id, new JsonObject
            {
                ["query_mode"] = "raw",
                ["all_columns"] = FilterExistingCols(dsDemanda,
                    "Equipe", "Servico", "Categoria", "Urgencia",
                    "VersaoProduto", "Volumetria", "Abertos", "HorasMediasResolucao"),
                ["order_by_cols"] = new JsonArray("[\"Volumetria\", false]"),
                ["row_limit"] = 500,
                ["page_length"] = 15,
                ["include_search"] = true,
                ["show_cell_bars"] = true,
                ["adhoc_filters"] = new JsonArray()
            }, "Pareto de chamados por Serviço (ex: EGUARDIAN), Categoria e Versão (#133948)."),

            ("TABELA_CLIENTE_RAIOX", "Raio-X de Empresas Clientes e Radar de Churn (Silenciosos > 60d)", "table", dsClientes.Id, new JsonObject
            {
                ["query_mode"] = "aggregate",
                ["groupby"] = FilterExistingCols(dsClientes,
                    "Cliente", "Servico", "Equipe", "StatusRelacionamento", "DataUltimoTicket"),
                ["metrics"] = new JsonArray(
                    MakeSimpleMetric(dsClientes, "DiasDesdeUltimoTicket", "MAX", "Dias Sem Ticket"),
                    MakeSimpleMetric(dsClientes, "TotalTicketsHistorico", "SUM", "Total Tickets"),
                    MakeSimpleMetric(dsClientes, "TicketsAtualmenteAbertos", "SUM", "Em Aberto"),
                    MakeSimpleMetric(dsClientes, "SlaCumpridoPct", "AVG", "SLA Cumprido (%)")),
                ["percent_metrics"] = new JsonArray(
                    MakeSimpleMetric(dsClientes, "TotalTicketsHistorico", "SUM", "Total", "metric_pct_totalticketshistorico_sum")),
                ["all_columns"] = new JsonArray(),
                ["timeseries_limit_metric"] = MakeSimpleMetric(dsClientes, "DiasDesdeUltimoTicket", "MAX", "Dias Sem Ticket"),
                ["order_desc"] = true,
                ["percent_metric_calculation"] = "row_limit",
                ["table_timestamp_format"] = "%d/%m/%Y",
                ["adhoc_filters"] = new JsonArray(
                    new JsonObject
                    {
                        ["clause"] = "WHERE",
                        ["comparator"] = "No filter",
                        ["datasourceWarning"] = false,
                        ["expressionType"] = "SIMPLE",
                        ["filterOptionName"] = "filter_dataultimoticket_temporal",
                        ["isExtra"] = false,
                        ["isNew"] = false,
                        ["operator"] = "TEMPORAL_RANGE",
                        ["sqlExpression"] = null,
                        ["subject"] = "DataUltimoTicket"
                    }),
                ["row_limit"] = 2000,
                ["page_length"] = 15,
                ["include_search"] = true,
                ["show_cell_bars"] = true,
                ["color_pn"] = true,
                ["align_pn"] = true,
                ["show_totals"] = true,
                ["column_config"] = new JsonObject
                {
                    ["Dias Sem Ticket"] = new JsonObject { ["d3NumberFormat"] = ",d" },
                    ["Total Tickets"] = new JsonObject { ["d3NumberFormat"] = ",d" },
                    ["Em Aberto"] = new JsonObject { ["d3NumberFormat"] = ",d" },
                    ["SLA Cumprido (%)"] = new JsonObject { ["d3NumberFormat"] = ".1f" },
                    ["%Total"] = new JsonObject { ["d3NumberFormat"] = ".1%" }
                }
            }, "Saúde da carteira de clientes por Produto/Serviço e Equipe Atual (Dono Atual), ordenada do cliente há mais tempo sem abrir chamado ao mais recente."),

            ("PIE_TICKETS_CLIENTE", "Tickets Abertos por Cliente (Organização)", "pie", dsClientesPeriodo.Id, new JsonObject
            {
                ["groupby"] = FilterExistingCols(dsClientesPeriodo, "Cliente"),
                ["metric"] = MakeSimpleMetric(dsClientesPeriodo, "QtdTickets", "SUM", "Tickets"),
                ["adhoc_filters"] = new JsonArray(
                    new JsonObject
                    {
                        ["clause"] = "WHERE",
                        ["comparator"] = "DATETRUNC(DATETIME('today'), month) : now",
                        ["datasourceWarning"] = false,
                        ["expressionType"] = "SIMPLE",
                        ["filterOptionName"] = "filter_dataabertura_este_mes",
                        ["isExtra"] = false,
                        ["isNew"] = false,
                        ["operator"] = "TEMPORAL_RANGE",
                        ["sqlExpression"] = null,
                        ["subject"] = "DataAbertura"
                    }),
                ["row_limit"] = 100,
                ["sort_by_metric"] = true,
                ["color_scheme"] = "supersetColors",
                ["show_legend"] = true,
                ["legendType"] = "scroll",
                ["legendOrientation"] = "left",
                ["label_type"] = "percent",
                ["number_format"] = ",d",
                ["date_format"] = "smart_date",
                ["show_labels"] = true,
                ["labels_outside"] = false,
                ["label_line"] = false,
                ["show_labels_threshold"] = 5,
                ["show_total"] = true,
                ["donut"] = true,
                ["innerRadius"] = 30,
                ["outerRadius"] = 70
            }, "Distribuição em Donut dos tickets abertos por Cliente (Organização) no período selecionado (padrão: Este mês), filtrável por Equipe."),

            ("TABELA_TICKETS_CLIENTE_PERIODO", "Detalhamento de Tickets por Cliente no Período", "table", dsClientesPeriodo.Id, new JsonObject
            {
                ["query_mode"] = "aggregate",
                ["groupby"] = FilterExistingCols(dsClientesPeriodo, "Cliente"),
                ["metrics"] = new JsonArray(
                    MakeSimpleMetric(dsClientesPeriodo, "QtdTickets", "SUM", "Qtd Tickets")),
                ["percent_metrics"] = new JsonArray(
                    MakeSimpleMetric(dsClientesPeriodo, "QtdTickets", "SUM", "Total", "metric_pct_qtdtickets_sum")),
                ["all_columns"] = new JsonArray(),
                ["timeseries_limit_metric"] = MakeSimpleMetric(dsClientesPeriodo, "QtdTickets", "SUM", "Qtd Tickets"),
                ["order_desc"] = true,
                ["percent_metric_calculation"] = "row_limit",
                ["adhoc_filters"] = new JsonArray(
                    new JsonObject
                    {
                        ["clause"] = "WHERE",
                        ["comparator"] = "DATETRUNC(DATETIME('today'), month) : now",
                        ["datasourceWarning"] = false,
                        ["expressionType"] = "SIMPLE",
                        ["filterOptionName"] = "filter_dataabertura_este_mes",
                        ["isExtra"] = false,
                        ["isNew"] = false,
                        ["operator"] = "TEMPORAL_RANGE",
                        ["sqlExpression"] = null,
                        ["subject"] = "DataAbertura"
                    }),
                ["row_limit"] = 500,
                ["page_length"] = 15,
                ["include_search"] = true,
                ["show_cell_bars"] = true,
                ["color_pn"] = true,
                ["align_pn"] = true,
                ["show_totals"] = true,
                ["column_config"] = new JsonObject
                {
                    ["Qtd Tickets"] = new JsonObject { ["d3NumberFormat"] = ",d" },
                    ["%Total"] = new JsonObject { ["d3NumberFormat"] = ".1%" }
                }
            }, "Ranking detalhado de tickets abertos por Cliente no período (Qtd Tickets, % do total e totalizador) para complementar o gráfico Donut.")
        };

        var createdMeta = new Dictionary<string, ChartMetadata>(StringComparer.OrdinalIgnoreCase);
        foreach (var (key, title, vizType, dsId, paramsObj, desc) in chartSpecs)
        {
            createdMeta[key] = await UpsertChartAsync(
                apiClient, existingCharts, title, vizType, dsId, dashboardId.Value, paramsObj, desc);
        }

        var positionJson = new JsonObject
        {
            ["DASHBOARD_VERSION_KEY"] = "v2",
            ["ROOT_ID"] = new JsonObject
            {
                ["type"] = "ROOT",
                ["id"] = "ROOT_ID",
                ["children"] = new JsonArray("GRID_ID")
            },
            ["HEADER_ID"] = new JsonObject
            {
                ["id"] = "HEADER_ID",
                ["type"] = "HEADER",
                ["meta"] = new JsonObject { ["text"] = dashTitle }
            },
            ["GRID_ID"] = new JsonObject
            {
                ["type"] = "GRID",
                ["id"] = "GRID_ID",
                ["children"] = new JsonArray("ROW-KPIS", "ROW-RADAR", "ROW-SERIES", "ROW-AGING", "ROW-DEMANDA-CLIENTES", "ROW-CLIENTES-PERIODO"),
                ["parents"] = new JsonArray("ROOT_ID")
            },
            ["ROW-KPIS"] = new JsonObject
            {
                ["type"] = "ROW",
                ["id"] = "ROW-KPIS",
                ["children"] = new JsonArray(
                    "CHART-KPI_BACKLOG", "CHART-KPI_VENCIDOS", "CHART-KPI_IMINENTE",
                    "CHART-KPI_ABERTOS_HOJE", "CHART-KPI_RESOLVIDOS_HOJE", "CHART-KPI_FCR"),
                ["parents"] = new JsonArray("ROOT_ID", "GRID_ID"),
                ["meta"] = new JsonObject { ["background"] = "BACKGROUND_TRANSPARENT" }
            },
            ["ROW-RADAR"] = new JsonObject
            {
                ["type"] = "ROW",
                ["id"] = "ROW-RADAR",
                ["children"] = new JsonArray("CHART-TABELA_RADAR_SLA"),
                ["parents"] = new JsonArray("ROOT_ID", "GRID_ID"),
                ["meta"] = new JsonObject { ["background"] = "BACKGROUND_TRANSPARENT" }
            },
            ["ROW-SERIES"] = new JsonObject
            {
                ["type"] = "ROW",
                ["id"] = "ROW-SERIES",
                ["children"] = new JsonArray("CHART-SERIE_BACKLOG_90D", "CHART-SERIE_THROUGHPUT"),
                ["parents"] = new JsonArray("ROOT_ID", "GRID_ID"),
                ["meta"] = new JsonObject { ["background"] = "BACKGROUND_TRANSPARENT" }
            },
            ["ROW-AGING"] = new JsonObject
            {
                ["type"] = "ROW",
                ["id"] = "ROW-AGING",
                ["children"] = new JsonArray("CHART-TABELA_BACKLOG_AGING", "CHART-TABELA_STATUS_AGING"),
                ["parents"] = new JsonArray("ROOT_ID", "GRID_ID"),
                ["meta"] = new JsonObject { ["background"] = "BACKGROUND_TRANSPARENT" }
            },
            ["ROW-DEMANDA-CLIENTES"] = new JsonObject
            {
                ["type"] = "ROW",
                ["id"] = "ROW-DEMANDA-CLIENTES",
                ["children"] = new JsonArray("CHART-TABELA_MAPA_DEMANDA", "CHART-TABELA_CLIENTE_RAIOX"),
                ["parents"] = new JsonArray("ROOT_ID", "GRID_ID"),
                ["meta"] = new JsonObject { ["background"] = "BACKGROUND_TRANSPARENT" }
            },
            ["ROW-CLIENTES-PERIODO"] = new JsonObject
            {
                ["type"] = "ROW",
                ["id"] = "ROW-CLIENTES-PERIODO",
                ["children"] = new JsonArray("CHART-PIE_TICKETS_CLIENTE", "CHART-TABELA_TICKETS_CLIENTE_PERIODO"),
                ["parents"] = new JsonArray("ROOT_ID", "GRID_ID"),
                ["meta"] = new JsonObject { ["background"] = "BACKGROUND_TRANSPARENT" }
            }
        };

        var layoutDims = new (string Key, string RowId, int Width, int Height)[]
        {
            ("KPI_BACKLOG", "ROW-KPIS", 2, 18),
            ("KPI_VENCIDOS", "ROW-KPIS", 2, 18),
            ("KPI_IMINENTE", "ROW-KPIS", 2, 18),
            ("KPI_ABERTOS_HOJE", "ROW-KPIS", 2, 18),
            ("KPI_RESOLVIDOS_HOJE", "ROW-KPIS", 2, 18),
            ("KPI_FCR", "ROW-KPIS", 2, 18),
            ("TABELA_RADAR_SLA", "ROW-RADAR", 12, 48),
            ("SERIE_BACKLOG_90D", "ROW-SERIES", 6, 42),
            ("SERIE_THROUGHPUT", "ROW-SERIES", 6, 42),
            ("TABELA_BACKLOG_AGING", "ROW-AGING", 7, 44),
            ("TABELA_STATUS_AGING", "ROW-AGING", 5, 44),
            ("TABELA_MAPA_DEMANDA", "ROW-DEMANDA-CLIENTES", 6, 44),
            ("TABELA_CLIENTE_RAIOX", "ROW-DEMANDA-CLIENTES", 6, 44),
            ("PIE_TICKETS_CLIENTE", "ROW-CLIENTES-PERIODO", 7, 46),
            ("TABELA_TICKETS_CLIENTE_PERIODO", "ROW-CLIENTES-PERIODO", 5, 46)
        };

        foreach (var (key, rowId, width, height) in layoutDims)
        {
            var meta = createdMeta[key];
            string nodeId = $"CHART-{key}";
            positionJson[nodeId] = new JsonObject
            {
                ["type"] = "CHART",
                ["id"] = nodeId,
                ["children"] = new JsonArray(),
                ["parents"] = new JsonArray("ROOT_ID", "GRID_ID", rowId),
                ["meta"] = new JsonObject
                {
                    ["width"] = width,
                    ["height"] = height,
                    ["chartId"] = meta.Id,
                    ["sliceName"] = meta.Title,
                    ["uuid"] = meta.Uuid
                }
            };
        }

        // Preserva json_metadata existente do Dashboard (filtros nativos configurados, paleta de cores, etc.)
        JsonObject? jsonMetadata = null;
        try
        {
            var dashDetail = await SendJsonCheckedAsync(apiClient, HttpMethod.Get, $"/api/v1/dashboard/{dashboardId.Value}", null, timeoutSeconds: 60);
            string? existingMetaRaw = dashDetail["result"]?["json_metadata"]?.GetValue<string>();
            if (!string.IsNullOrWhiteSpace(existingMetaRaw))
            {
                jsonMetadata = JsonNode.Parse(existingMetaRaw) as JsonObject;
            }
        }
        catch
        {
            // Usa objeto padrão se não for possível ler metadados anteriores
        }

        jsonMetadata ??= new JsonObject();
        jsonMetadata["timed_refresh_immune_slices"] ??= new JsonArray();
        jsonMetadata["expanded_slices"] ??= new JsonObject();
        jsonMetadata["refresh_frequency"] ??= 60;
        jsonMetadata["default_filters"] ??= "{}";
        jsonMetadata["color_scheme"] ??= "supersetColors";
        jsonMetadata["cross_filters_enabled"] = true;

        var nativeFilters = jsonMetadata["native_filter_configuration"] as JsonArray ?? new JsonArray();
        bool hasEquipeFilter = false;
        const string periodFilterId = "NATIVE_FILTER-b2c3d4e5-f6a7-4b8c-9d0e-1f2a3b4c5d6e";
        JsonObject? existingPeriodFilter = null;

        foreach (JsonNode? nfNode in nativeFilters)
        {
            if (nfNode is not JsonObject nfObj) continue;

            string? nfId = nfObj["id"]?.GetValue<string>();
            string? nfName = nfObj["name"]?.GetValue<string>();

            if (string.Equals(nfId, periodFilterId, StringComparison.OrdinalIgnoreCase) ||
                string.Equals(nfName, "Período (Tickets por Cliente)", StringComparison.OrdinalIgnoreCase))
            {
                existingPeriodFilter = nfObj;
            }

            if (string.Equals(nfName, "Equipe", StringComparison.OrdinalIgnoreCase))
            {
                hasEquipeFilter = true;
            }
            else if (nfObj["targets"] is JsonArray targetsArr)
            {
                foreach (JsonNode? tNode in targetsArr)
                {
                    string? colName = tNode?["column"]?["name"]?.GetValue<string>();
                    if (string.Equals(colName, "Equipe", StringComparison.OrdinalIgnoreCase))
                    {
                        hasEquipeFilter = true;
                        break;
                    }
                }
            }
        }

        if (!hasEquipeFilter)
        {
            nativeFilters.Add(new JsonObject
            {
                ["id"] = "NATIVE_FILTER-a1b2c3d4-e5f6-4a7b-8c9d-0e1f2a3b4c5d",
                ["name"] = "Equipe",
                ["filterType"] = "filter_select",
                ["targets"] = new JsonArray(
                    new JsonObject
                    {
                        ["datasetId"] = dsKpis.Id,
                        ["column"] = new JsonObject { ["name"] = "Equipe" }
                    }),
                ["defaultDataMask"] = new JsonObject
                {
                    ["extraFormData"] = new JsonObject(),
                    ["filterState"] = new JsonObject(),
                    ["ownState"] = new JsonObject()
                },
                ["controlValues"] = new JsonObject
                {
                    ["enableEmptyFilter"] = false,
                    ["defaultToFirstItem"] = false,
                    ["multiSelect"] = true,
                    ["searchAllOptions"] = false,
                    ["inverseSelection"] = false
                },
                ["cascadeParentIds"] = new JsonArray(),
                ["scope"] = new JsonObject
                {
                    ["rootPath"] = new JsonArray("ROOT_ID"),
                    ["excluded"] = new JsonArray()
                },
                ["type"] = "NATIVE_FILTER",
                ["description"] = "Filtro global de Equipe aplicado em todos os gráficos e views (mart.*)."
            });
        }

        var excludedForPeriod = new JsonArray();
        foreach (var kv in createdMeta)
        {
            if (!string.Equals(kv.Key, "PIE_TICKETS_CLIENTE", StringComparison.OrdinalIgnoreCase) &&
                !string.Equals(kv.Key, "TABELA_TICKETS_CLIENTE_PERIODO", StringComparison.OrdinalIgnoreCase))
            {
                excludedForPeriod.Add(kv.Value.Id);
            }
        }

        if (existingPeriodFilter is not null)
        {
            if (existingPeriodFilter["scope"] is JsonObject scopeObj)
            {
                scopeObj["excluded"] = excludedForPeriod;
            }
            else
            {
                existingPeriodFilter["scope"] = new JsonObject
                {
                    ["rootPath"] = new JsonArray("ROOT_ID"),
                    ["excluded"] = excludedForPeriod
                };
            }
        }
        else
        {
            nativeFilters.Add(new JsonObject
            {
                ["id"] = periodFilterId,
                ["name"] = "Período (Tickets por Cliente)",
                ["filterType"] = "filter_time",
                ["targets"] = new JsonArray(new JsonObject()),
                ["defaultDataMask"] = new JsonObject
                {
                    ["extraFormData"] = new JsonObject(),
                    ["filterState"] = new JsonObject(),
                    ["ownState"] = new JsonObject()
                },
                ["controlValues"] = new JsonObject
                {
                    ["enableEmptyFilter"] = false
                },
                ["cascadeParentIds"] = new JsonArray(),
                ["scope"] = new JsonObject
                {
                    ["rootPath"] = new JsonArray("ROOT_ID"),
                    ["excluded"] = excludedForPeriod
                },
                ["type"] = "NATIVE_FILTER",
                ["description"] = "Filtro de Data de Abertura aplicado ao Donut e ao Grid de Tickets por Cliente (padrão inicial: Este mês)."
            });
        }

        jsonMetadata["native_filter_configuration"] = nativeFilters;

        await SendJsonCheckedAsync(
            apiClient,
            HttpMethod.Put,
            $"/api/v1/dashboard/{dashboardId.Value}",
            new JsonObject
            {
                ["dashboard_title"] = dashTitle,
                ["slug"] = dashSlug,
                ["position_json"] = positionJson.ToJsonString(),
                ["json_metadata"] = jsonMetadata.ToJsonString(),
                ["published"] = true
            },
            timeoutSeconds: 90);

        foreach (var meta in createdMeta.Values)
        {
            try
            {
                var mergedDashIds = await GetMergedChartDashboardsAsync(apiClient, meta.Id, dashboardId.Value);
                await SendJsonRawAsync(
                    apiClient,
                    HttpMethod.Put,
                    $"/api/v1/chart/{meta.Id}",
                    new JsonObject { ["dashboards"] = mergedDashIds },
                    timeoutSeconds: 60);
            }
            catch
            {
                // Ignora caso o vínculo já esteja persistido
            }
        }

        string dashUrl = $"{_supersetUrl}/superset/dashboard/{dashSlug}/";
        AppendSetupLog($"[OK] Passo 3/3 — Dashboard '{dashTitle}' publicado em: {dashUrl}");
        return dashUrl;
    }

    private async Task<(HttpStatusCode Status, string Body)> SendJsonRawAsync(
        HttpClient apiClient,
        HttpMethod method,
        string path,
        JsonNode? payload,
        int timeoutSeconds = 120,
        int maxRetries = 1,
        CancellationToken cancellationToken = default)
    {
        string? payloadJson = payload?.ToJsonString();

        for (int attempt = 0; ; attempt++)
        {
            using var req = new HttpRequestMessage(method, path);
            if (payloadJson is not null)
            {
                req.Content = new StringContent(payloadJson, Encoding.UTF8, "application/json");
            }

            using var timeoutCts = CancellationTokenSource.CreateLinkedTokenSource(cancellationToken);
            timeoutCts.CancelAfter(TimeSpan.FromSeconds(timeoutSeconds));

            try
            {
                using var resp = await apiClient.SendAsync(req, timeoutCts.Token);
                string body = await resp.Content.ReadAsStringAsync(timeoutCts.Token);
                return (resp.StatusCode, body);
            }
            catch (OperationCanceledException) when (!cancellationToken.IsCancellationRequested && attempt < maxRetries)
            {
                AppendSetupLog($"[AVISO] Tempo limite ({timeoutSeconds}s) atingido em {method.Method} {path}. Nova tentativa em 3s...");
                await Task.Delay(3000, cancellationToken);
            }
            catch (OperationCanceledException ex) when (!cancellationToken.IsCancellationRequested)
            {
                throw new TimeoutException(
                    $"Tempo limite ({timeoutSeconds}s) excedido na requisição {method.Method} {path} ao Apache Superset.",
                    ex);
            }
            catch (HttpRequestException ex) when (attempt < maxRetries)
            {
                AppendSetupLog($"[AVISO] Falha de comunicação em {method.Method} {path} ({ex.Message}). Nova tentativa em 3s...");
                await Task.Delay(3000, cancellationToken);
            }
        }
    }

    private async Task<JsonObject> SendJsonCheckedAsync(
        HttpClient apiClient,
        HttpMethod method,
        string path,
        JsonNode? payload,
        int timeoutSeconds = 120,
        int maxRetries = 1)
    {
        var (status, body) = await SendJsonRawAsync(apiClient, method, path, payload, timeoutSeconds, maxRetries);
        if ((int)status < 200 || (int)status >= 300)
        {
            throw new InvalidOperationException($"HTTP {(int)status} em {method.Method} {path}: {body}");
        }

        if (string.IsNullOrWhiteSpace(body))
        {
            return new JsonObject();
        }

        return JsonNode.Parse(body)?.AsObject() ?? new JsonObject();
    }

    private async Task WaitForHealthyAsync(Process process, CancellationToken ct)
    {
        const int maxTentativas = 40;
        for (int i = 0; i < maxTentativas && !ct.IsCancellationRequested; i++)
        {
            if (process.HasExited)
            {
                lock (_stateLock)
                {
                    Status = SupersetStatus.Error;
                    StatusMessage = $"WSL fechou antes de responder (código {process.ExitCode}). Verifique os logs.";
                }
                NotifyStateChanged();
                return;
            }

            if (await ProbeHealthEndpointAsync(ct))
            {
                lock (_stateLock)
                {
                    Status = SupersetStatus.Online;
                    StatusMessage = $"Superset online em {_supersetUrl}";
                }
                AppendLog($"Apache Superset pronto e respondendo em {_supersetUrl}/health.");
                NotifyStateChanged();
                return;
            }

            try
            {
                await Task.Delay(TimeSpan.FromMilliseconds(1500), ct);
            }
            catch (OperationCanceledException)
            {
                return;
            }
        }

        if (!ct.IsCancellationRequested)
        {
            lock (_stateLock)
            {
                if (Status == SupersetStatus.Starting)
                {
                    StatusMessage = "Superset ainda iniciando no WSL... clique em 'Verificar Status' em alguns segundos.";
                }
            }
            NotifyStateChanged();
        }
    }

    private async Task<bool> ProbeHealthEndpointAsync(CancellationToken ct = default)
    {
        try
        {
            using var resp = await _httpClient.GetAsync($"{_supersetUrl.TrimEnd('/')}/health", ct);
            return resp.IsSuccessStatusCode;
        }
        catch
        {
            return false;
        }
    }

    private void AppendLog(string message)
    {
        var line = $"[{DateTime.Now:HH:mm:ss}] {message}";
        lock (_stateLock)
        {
            _logs.Add(line);
            if (_logs.Count > 150)
            {
                _logs.RemoveAt(0);
            }
        }
        NotifyStateChanged();
    }

    private void AppendSetupLog(string message)
    {
        var line = $"[{DateTime.Now:HH:mm:ss}] {message}";
        lock (_stateLock)
        {
            _setupLogs.Add(line);
            if (_setupLogs.Count > 250)
            {
                _setupLogs.RemoveAt(0);
            }

            if (IsSetupRunning && (message.StartsWith("[OK]", StringComparison.Ordinal) || message.StartsWith("[INF]", StringComparison.Ordinal)))
            {
                SetupStatusMessage = message;
            }
        }
        NotifyStateChanged();
    }

    private void NotifyStateChanged() => OnStateChanged?.Invoke();

    public void Dispose()
    {
        _startupCts?.Cancel();
        _startupCts?.Dispose();
        try
        {
            if (_wslProcess is { HasExited: false })
            {
                _wslProcess.Kill(entireProcessTree: true);
            }
        }
        catch
        {
            // Ignora erro ao descartar processo no shutdown
        }
        _wslProcess?.Dispose();
        _httpClient.Dispose();
    }
}
