using System.Diagnostics;
using System.Reflection;
using System.Text;
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
/// Orquestra a inicialização silenciosa do Apache Superset dentro do WSL2 (Ubuntu)
/// via System.Diagnostics.Process, monitora o endpoint /health e executa a automação
/// completa de configuração inicial (Database, 8 Datasets mart e Dashboard Sala de Guerra).
/// </summary>
public sealed class SupersetService : IDisposable
{
    // =========================================================================
    // CONFIGURAÇÃO DO CAMINHO DO APACHE SUPERSET NO WSL2 (Ubuntu)
    // Caso seu ambiente virtual ou distro tenham outro nome, ajuste no appsettings.json
    // na seção "Superset" ou diretamente nos valores padrão abaixo:
    // =========================================================================
    private readonly string _wslDistro;
    private readonly string _venvActivatePath;
    private readonly string _secretKey;
    private readonly int _port;
    private readonly string _supersetUrl;

    private readonly HttpClient _httpClient = new() { Timeout = TimeSpan.FromSeconds(2) };
    private readonly object _stateLock = new();
    private readonly List<string> _logs = new();
    private readonly List<string> _setupLogs = new();
    private Process? _wslProcess;
    private CancellationTokenSource? _startupCts;

    public SupersetStatus Status { get; private set; } = SupersetStatus.Offline;
    public string StatusMessage { get; private set; } = "Superset parado";
    public string SupersetUrl => _supersetUrl;
    public string DashboardUrl => $"{_supersetUrl.TrimEnd('/')}/superset/dashboard/sala-de-guerra-movidesk/";
    public int Port => _port;
    public string WslDistro => _wslDistro;
    public string VenvActivatePath => _venvActivatePath;

    public bool IsSetupRunning { get; private set; }
    public bool? SetupSucceeded { get; private set; }
    public string SetupStatusMessage { get; private set; } =
        "Pronto para provisionar a conexão MovideskDM, os 8 Datasets (schema mart) e o Dashboard Sala de Guerra.";

    public event Action? OnStateChanged;

    public SupersetService(IConfiguration configuration)
    {
        // TODO: Ajuste no appsettings.json ("Superset:*") se o caminho da venv no WSL mudar
        _wslDistro = configuration["Superset:WslDistro"] ?? "Ubuntu";
        _venvActivatePath = configuration["Superset:VenvActivatePath"] ?? "~/superset-env/bin/activate";
        _secretKey = configuration["Superset:SecretKey"] ?? "movidesk_superset_super_secret_key_2026";
        _port = int.TryParse(configuration["Superset:Port"], out var parsedPort) ? parsedPort : 8088;
        _supersetUrl = configuration["Superset:Url"] ?? $"http://localhost:{_port}";
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
                "Pronto para provisionar a conexão MovideskDM, os 8 Datasets (schema mart) e o Dashboard Sala de Guerra.";
        }
        NotifyStateChanged();
    }

    /// <summary>
    /// Abre o Apache Superset no navegador padrão do Windows.
    /// </summary>
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

    /// <summary>
    /// Abre diretamente o Dashboard "Sala de Guerra - Movidesk BI" no navegador padrão.
    /// </summary>
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

    /// <summary>
    /// Verifica via HTTP (/health) se o servidor Superset já está respondendo na porta configurada.
    /// </summary>
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

    /// <summary>
    /// Aciona o WSL2 silenciosamente no Windows para subir o Apache Superset em background
    /// e monitora até ficar online em http://localhost:8088.
    /// </summary>
    public async Task StartSupersetAsync()
    {
        lock (_stateLock)
        {
            if (Status == SupersetStatus.Starting)
            {
                return;
            }
        }

        // Evita subir duas instâncias caso já esteja respondendo (ex.: iniciado manualmente)
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

        // Comando Bash executado dentro do WSL2:
        //   wsl.exe -d Ubuntu -e bash -c "source ~/superset-env/bin/activate && export SUPERSET_SECRET_KEY='...' && exec superset run -h 0.0.0.0 -p 8088 --with-threads"
        string comandoSuperset =
            $"source {_venvActivatePath} && export SUPERSET_SECRET_KEY='{_secretKey}' && exec superset run -h 0.0.0.0 -p {_port} --with-threads";

        AppendLog($"Executando WSL ({(string.IsNullOrWhiteSpace(_wslDistro) ? "distro padrão" : _wslDistro)}): {comandoSuperset}");

        try
        {
            var startInfo = new ProcessStartInfo
            {
                FileName = OperatingSystem.IsWindows() ? "wsl.exe" : "bash",
                UseShellExecute = false,
                CreateNoWindow = true, // Execução silenciosa (sem abrir janela preta de console)
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
                    // Flask/Werkzeug escreve logs normais no stderr
                    AppendLog(e.Data);
                }
            };

            process.Exited += (_, _) =>
            {
                int? exitCode = null;
                try { exitCode = process.ExitCode; } catch { /* Processo já descartado */ }

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

            // Monitora o endpoint /health em background sem travar a interface Blazor
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

    /// <summary>
    /// Encerra o Apache Superset dentro do WSL2 e finaliza o processo monitorado.
    /// </summary>
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
                    FileName = "wsl.exe",
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

    /// <summary>
    /// Executa silenciosamente o script Python de setup automático (setup_superset_auto.py) dentro do WSL2,
    /// passando a senha do usuário admin informada na interface gráfica e capturando stdout/stderr em tempo real.
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
            SetupStatusMessage = "Iniciando automação do Apache Superset no WSL2...";
            _setupLogs.Clear();
        }
        NotifyStateChanged();

        try
        {
            string scriptContent = LoadSetupScriptContent()
                .Replace("\r\n", "\n", StringComparison.Ordinal)
                .Replace("\r", "\n", StringComparison.Ordinal);

            string scriptB64 = Convert.ToBase64String(Encoding.UTF8.GetBytes(scriptContent));
            string userB64 = Convert.ToBase64String(Encoding.UTF8.GetBytes(adminUsername.Trim()));
            string passB64 = Convert.ToBase64String(Encoding.UTF8.GetBytes(adminPassword));
            string urlB64 = Convert.ToBase64String(Encoding.UTF8.GetBytes(_supersetUrl));

            string bashCmd =
                $"echo '{scriptB64}' | base64 -d > /tmp/setup_superset_auto.py && " +
                $"USR=$(echo '{userB64}' | base64 -d) && " +
                $"PASS=$(echo '{passB64}' | base64 -d) && " +
                $"URL=$(echo '{urlB64}' | base64 -d) && " +
                $"PY_BIN=\"$HOME/superset-env/bin/python\"; " +
                $"if [ ! -x \"$PY_BIN\" ]; then PY_BIN=python3; fi; " +
                $"\"$PY_BIN\" -u /tmp/setup_superset_auto.py --url \"$URL\" --username \"$USR\" --password \"$PASS\"";

            AppendSetupLog($"[INF] Acionando automação Python no WSL2 ({(string.IsNullOrWhiteSpace(_wslDistro) ? "distro padrão" : _wslDistro)}) para o usuário '{adminUsername.Trim()}'...");

            var startInfo = new ProcessStartInfo
            {
                FileName = OperatingSystem.IsWindows() ? "wsl.exe" : "bash",
                UseShellExecute = false,
                CreateNoWindow = true,
                RedirectStandardOutput = true,
                RedirectStandardError = true,
                StandardOutputEncoding = Encoding.UTF8,
                StandardErrorEncoding = Encoding.UTF8
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
                startInfo.ArgumentList.Add(bashCmd);
            }
            else
            {
                startInfo.ArgumentList.Add("-c");
                startInfo.ArgumentList.Add(bashCmd);
            }

            using var process = new Process
            {
                StartInfo = startInfo,
                EnableRaisingEvents = true
            };

            process.OutputDataReceived += (_, e) =>
            {
                if (!string.IsNullOrWhiteSpace(e.Data))
                {
                    AppendSetupLog(e.Data);
                }
            };

            process.ErrorDataReceived += (_, e) =>
            {
                if (!string.IsNullOrWhiteSpace(e.Data))
                {
                    AppendSetupLog(e.Data);
                }
            };

            if (!process.Start())
            {
                throw new InvalidOperationException("Não foi possível iniciar o processo wsl.exe para o setup do Superset.");
            }

            process.BeginOutputReadLine();
            process.BeginErrorReadLine();

            await process.WaitForExitAsync();
            process.WaitForExit(); // Garante flush completo dos buffers assíncronos de stdout/stderr

            bool ok = process.ExitCode == 0;
            lock (_stateLock)
            {
                IsSetupRunning = false;
                SetupSucceeded = ok;
                SetupStatusMessage = ok
                    ? "Setup concluído com sucesso! Database MovideskDM, 8 Datasets (mart) e Dashboard Sala de Guerra publicados."
                    : $"O setup encerrou com falha (código {process.ExitCode}). Verifique os logs no console abaixo.";
            }
            NotifyStateChanged();

            // Atualiza também o status de saúde do Superset (caso o script tenha subido o servidor)
            await CheckHealthAsync();
        }
        catch (Exception ex)
        {
            lock (_stateLock)
            {
                IsSetupRunning = false;
                SetupSucceeded = false;
                SetupStatusMessage = $"Erro ao executar setup automático: {ex.Message}";
            }
            AppendSetupLog($"[ERRO] {ex.Message}");
            NotifyStateChanged();
        }
    }

    private static string LoadSetupScriptContent()
    {
        const string resourceName = "Movidesk.ControlPanel.Superset.setup_superset_auto.py";
        var assembly = Assembly.GetExecutingAssembly();
        using Stream? stream = assembly.GetManifestResourceStream(resourceName);
        if (stream is not null)
        {
            using var reader = new StreamReader(stream, Encoding.UTF8);
            return reader.ReadToEnd();
        }

        // Fallback em ambiente de desenvolvimento caso o recurso embarcado não seja encontrado
        string candidate = Path.GetFullPath(Path.Combine(AppContext.BaseDirectory, "..", "..", "..", "..", "..", "superset", "setup_superset_auto.py"));
        if (File.Exists(candidate))
        {
            return File.ReadAllText(candidate, Encoding.UTF8);
        }

        throw new FileNotFoundException($"Recurso embarcado '{resourceName}' não encontrado no executável.");
    }

    private async Task WaitForHealthyAsync(Process process, CancellationToken ct)
    {
        const int maxTentativas = 40; // ~60 segundos (40 x 1.5s)
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

            if (IsSetupRunning && (message.StartsWith("[OK]", StringComparison.Ordinal) || message.StartsWith("[INFO]", StringComparison.Ordinal)))
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
