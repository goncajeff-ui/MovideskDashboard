using System.Diagnostics;
using System.Net.Http;
using System.Runtime.Versioning;
using System.Text;

namespace Movidesk.Installer.Core;

public sealed class ReinicioWindowsNecessarioException : Exception
{
    public ReinicioWindowsNecessarioException(string message) : base(message)
    {
    }
}

/// <summary>
/// Motor assíncrono de execução de processos Windows, gerenciamento do WSL 2 (Ubuntu),
/// Docker Engine, contêineres e sondagem HTTP de disponibilidade do Apache Superset.
/// </summary>
[SupportedOSPlatform("windows")]
public sealed class WslEngine
{
    private static readonly HttpClient HttpProbeClient = new()
    {
        Timeout = TimeSpan.FromSeconds(4)
    };

    public static string ResolverCaminhoWsl()
    {
        string sys32 = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.System), "wsl.exe");
        return File.Exists(sys32) ? sys32 : "wsl.exe";
    }

    public async Task<ResultadoComando> ExecutarProcessoAsync(
        string executavel,
        IEnumerable<string> argumentos,
        Encoding outputEncoding,
        AuditorLog log,
        bool registrarLinhasNoLog = true,
        TimeSpan? timeout = null,
        CancellationToken ct = default)
    {
        var startInfo = new ProcessStartInfo
        {
            FileName = executavel,
            UseShellExecute = false,
            CreateNoWindow = true,
            RedirectStandardOutput = true,
            RedirectStandardError = true,
            StandardOutputEncoding = outputEncoding,
            StandardErrorEncoding = outputEncoding
        };

        foreach (string arg in argumentos)
        {
            startInfo.ArgumentList.Add(arg);
        }

        using var process = new Process { StartInfo = startInfo };
        var stdOutSb = new StringBuilder();
        var stdErrSb = new StringBuilder();
        object sbLock = new();

        process.OutputDataReceived += (_, e) =>
        {
            if (e.Data is null) return;
            string clean = LimparCaracteresControle(e.Data);
            if (string.IsNullOrWhiteSpace(clean)) return;

            lock (sbLock)
            {
                stdOutSb.AppendLine(clean);
            }

            if (registrarLinhasNoLog)
            {
                log.Comando(clean);
            }
        };

        process.ErrorDataReceived += (_, e) =>
        {
            if (e.Data is null) return;
            string clean = LimparCaracteresControle(e.Data);
            if (string.IsNullOrWhiteSpace(clean)) return;

            lock (sbLock)
            {
                stdErrSb.AppendLine(clean);
            }

            if (registrarLinhasNoLog)
            {
                log.Comando(clean);
            }
        };

        if (!process.Start())
        {
            throw new InvalidOperationException($"Não foi possível iniciar o processo '{executavel}'.");
        }

        process.BeginOutputReadLine();
        process.BeginErrorReadLine();

        using var timeoutCts = timeout.HasValue
            ? new CancellationTokenSource(timeout.Value)
            : new CancellationTokenSource();
        using var linkedCts = CancellationTokenSource.CreateLinkedTokenSource(ct, timeoutCts.Token);

        try
        {
            await process.WaitForExitAsync(linkedCts.Token);
        }
        catch (OperationCanceledException)
        {
            try
            {
                if (!process.HasExited)
                {
                    process.Kill(entireProcessTree: true);
                }
            }
            catch
            {
                // Melhor esforço ao encerrar processo após cancelamento ou timeout
            }

            if (timeoutCts.IsCancellationRequested && !ct.IsCancellationRequested)
            {
                throw new TimeoutException(
                    $"Tempo limite excedido ({timeout?.TotalMinutes:0.#} min) ao executar '{Path.GetFileName(executavel)}'.");
            }

            throw;
        }

        // Garante drenagem final dos buffers assíncronos de saída
        await Task.Delay(50, CancellationToken.None);

        lock (sbLock)
        {
            return new ResultadoComando(
                process.ExitCode,
                stdOutSb.ToString().Trim(),
                stdErrSb.ToString().Trim());
        }
    }

    public Task<ResultadoComando> ExecutarWslNativoAsync(
        IEnumerable<string> argumentos,
        AuditorLog log,
        bool registrarLinhasNoLog = true,
        TimeSpan? timeout = null,
        CancellationToken ct = default)
    {
        // Comandos nativos do host Windows no wsl.exe emitem UTF-16LE
        return ExecutarProcessoAsync(
            ResolverCaminhoWsl(),
            argumentos,
            Encoding.Unicode,
            log,
            registrarLinhasNoLog,
            timeout ?? TimeSpan.FromMinutes(10),
            ct);
    }

    public Task<ResultadoComando> ExecutarBashWslAsync(
        string distro,
        string scriptBash,
        bool comoRoot,
        AuditorLog log,
        bool registrarLinhasNoLog = true,
        TimeSpan? timeout = null,
        CancellationToken ct = default)
    {
        string normalized = scriptBash.Replace("\r\n", "\n", StringComparison.Ordinal).Replace("\r", "\n", StringComparison.Ordinal);
        string b64 = Convert.ToBase64String(Encoding.UTF8.GetBytes(normalized));
        string bashPipeline = $"echo '{b64}' | base64 -d | bash -e -o pipefail";

        var args = new List<string>();
        if (!string.IsNullOrWhiteSpace(distro))
        {
            args.Add("-d");
            args.Add(distro);
        }

        if (comoRoot)
        {
            args.Add("-u");
            args.Add("root");
        }

        args.Add("-e");
        args.Add("bash");
        args.Add("-lc");
        args.Add(bashPipeline);

        return ExecutarProcessoAsync(
            ResolverCaminhoWsl(),
            args,
            Encoding.UTF8,
            log,
            registrarLinhasNoLog,
            timeout ?? TimeSpan.FromMinutes(15),
            ct);
    }

    public async Task CopiarTextoParaWslAsync(
        string distro,
        string caminhoDestinoWsl,
        string conteudoTexto,
        bool comoRoot,
        AuditorLog log,
        CancellationToken ct = default)
    {
        string lfText = conteudoTexto.Replace("\r\n", "\n", StringComparison.Ordinal).Replace("\r", "\n", StringComparison.Ordinal);
        string b64 = Convert.ToBase64String(Encoding.UTF8.GetBytes(lfText));
        string pastaPai = caminhoDestinoWsl.Contains('/')
            ? caminhoDestinoWsl[..caminhoDestinoWsl.LastIndexOf('/')]
            : ".";

        string script = $"""
            mkdir -p "{pastaPai}"
            printf '%s' '{b64}' | base64 -d > "{caminhoDestinoWsl}"
            chmod 644 "{caminhoDestinoWsl}"
            """;

        ResultadoComando res = await ExecutarBashWslAsync(
            distro,
            script,
            comoRoot,
            log,
            registrarLinhasNoLog: false,
            timeout: TimeSpan.FromSeconds(30),
            ct: ct);

        if (!res.Sucesso)
        {
            throw new InvalidOperationException(
                $"Falha ao gravar arquivo '{caminhoDestinoWsl}' no WSL ({distro}): {res.StdErr}");
        }
    }

    public async Task GarantirWsl2UbuntuAsync(string distro, AuditorLog log, CancellationToken ct)
    {
        string wslExe = ResolverCaminhoWsl();
        if (!File.Exists(wslExe) && !EstaNoPath("wsl.exe"))
        {
            throw new PlatformNotSupportedException(
                "O executável 'wsl.exe' não foi encontrado. Verifique se está utilizando Windows 10 (2004+), Windows 11 ou Windows Server 2022.");
        }

        log.Aguardando("Verificando status atual do Subsistema Windows para Linux (WSL 2)...");
        ResultadoComando statusRes = await ExecutarWslNativoAsync(["--status"], log, registrarLinhasNoLog: false, ct: ct);
        ResultadoComando listRes = await ExecutarWslNativoAsync(["-l", "-q"], log, registrarLinhasNoLog: false, ct: ct);

        bool distroExiste = listRes.StdOut
            .Split(['\r', '\n'], StringSplitOptions.RemoveEmptyEntries)
            .Any(line => line.Trim().Contains(distro, StringComparison.OrdinalIgnoreCase));

        if (!distroExiste || !statusRes.Sucesso)
        {
            log.Aguardando($"Habilitando WSL 2 e instalando distribuição '{distro}' (pode levar alguns minutos)...");
            await ExecutarWslNativoAsync(["--set-default-version", "2"], log, registrarLinhasNoLog: false, ct: ct);

            ResultadoComando installRes = await ExecutarWslNativoAsync(
                ["--install", "-d", distro, "--no-launch"],
                log,
                registrarLinhasNoLog: true,
                timeout: TimeSpan.FromMinutes(20),
                ct: ct);

            string saidaCombinada = $"{installRes.StdOut}\n{installRes.StdErr}";
            bool precisaReinicio =
                installRes.ExitCode == 3010 ||
                saidaCombinada.Contains("reboot", StringComparison.OrdinalIgnoreCase) ||
                saidaCombinada.Contains("restart", StringComparison.OrdinalIgnoreCase) ||
                saidaCombinada.Contains("reinic", StringComparison.OrdinalIgnoreCase);

            if (precisaReinicio)
            {
                throw new ReinicioWindowsNecessarioException(
                    "O Windows habilitou os componentes do WSL 2 e requer uma reinicialização para concluir a ativação do kernel Linux.\n\n" +
                    "Por favor, reinicie o computador/servidor e execute este instalador novamente para continuar a partir do Passo 3.");
            }

            if (!installRes.Sucesso)
            {
                // Recheca se a distro já ficou registrada mesmo com aviso de saída não-zero
                ResultadoComando recheck = await ExecutarWslNativoAsync(["-l", "-q"], log, registrarLinhasNoLog: false, ct: ct);
                bool registradaAgora = recheck.StdOut
                    .Split(['\r', '\n'], StringSplitOptions.RemoveEmptyEntries)
                    .Any(line => line.Trim().Contains(distro, StringComparison.OrdinalIgnoreCase));

                if (!registradaAgora)
                {
                    throw new InvalidOperationException(
                        $"Falha ao instalar WSL 2 / {distro} (código {installRes.ExitCode}).\n{saidaCombinada}");
                }
            }
        }
        else
        {
            log.Sucesso($"Distribuição '{distro}' já encontrada no WSL.");
        }

        // Garante WSL versão 2 explicitamente na distro
        log.Aguardando($"Validando versão 2 do WSL para '{distro}'...");
        await ExecutarWslNativoAsync(["--set-version", distro, "2"], log, registrarLinhasNoLog: false, ct: ct);

        // Testa execução não interativa como root para garantir inicialização limpa
        ResultadoComando probe = await ExecutarBashWslAsync(
            distro,
            """
            if [ ! -f /etc/wsl.conf ] || ! grep -q "systemd=true" /etc/wsl.conf; then
              printf "[boot]\nsystemd=true\n" > /etc/wsl.conf
            fi
            echo "WSL2_UBUNTU_PRONTO: $(uname -r)"
            """,
            comoRoot: true,
            log: log,
            registrarLinhasNoLog: true,
            timeout: TimeSpan.FromMinutes(3),
            ct: ct);

        if (!probe.Sucesso)
        {
            throw new InvalidOperationException(
                $"Não foi possível iniciar o ambiente Bash no WSL '{distro}'. Caso tenha acabado de habilitar o WSL, reinicie o Windows.\n{probe.StdErr}");
        }

        log.Sucesso($"Ambiente WSL 2 '{distro}' operacional e configurado.");
    }

    public async Task InstalarEIniciarDockerAsync(string distro, AuditorLog log, CancellationToken ct)
    {
        const string scriptDocker = """
            set -e
            export DEBIAN_FRONTEND=noninteractive

            if ! command -v docker >/dev/null 2>&1 || ! docker compose version >/dev/null 2>&1; then
                echo "[INF] Docker ou Docker Compose ausente. Iniciando instalação no Ubuntu..."
                apt-get update -qq
                apt-get install -y -qq ca-certificates curl gnupg lsb-release apt-transport-https

                install -m 0755 -d /etc/apt/keyrings
                if [ ! -f /etc/apt/keyrings/docker.asc ]; then
                    curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
                    chmod a+r /etc/apt/keyrings/docker.asc
                fi

                . /etc/os-release
                echo \
                  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu \
                  ${VERSION_CODENAME:-jammy} stable" | tee /etc/apt/sources.list.d/docker.list > /dev/null

                apt-get update -qq
                if ! apt-get install -y -qq docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin; then
                    echo "[AVISO] Repositório oficial Docker indisponível; instalando via pacote nativo Ubuntu (docker.io)..."
                    apt-get install -y -qq docker.io docker-compose-v2 || apt-get install -y -qq docker.io
                fi
            else
                echo "[OK] Docker e Docker Compose já estão instalados."
            fi

            # Evita falha de rede docker0 em kernels WSL que ainda utilizam iptables-legacy
            if command -v update-alternatives >/dev/null 2>&1 && [ -x /usr/sbin/iptables-legacy ]; then
                update-alternatives --set iptables /usr/sbin/iptables-legacy >/dev/null 2>&1 || true
            fi

            DEFAULT_USER=$(awk -F: '$3 >= 1000 && $3 < 60000 {print $1; exit}' /etc/passwd)
            if [ -n "$DEFAULT_USER" ]; then
                usermod -aG docker "$DEFAULT_USER" || true
            fi

            if ! docker info >/dev/null 2>&1; then
                echo "[INF] Iniciando daemon Docker..."
                if [ "$(ps -p 1 -o comm= 2>/dev/null)" = "systemd" ]; then
                    systemctl enable --now docker || service docker start || true
                else
                    service docker start >/dev/null 2>&1 || nohup dockerd >/var/log/advice-dockerd.log 2>&1 &
                fi
            fi

            echo "[INF] Aguardando Docker Engine responder..."
            for i in $(seq 1 25); do
                if docker info >/dev/null 2>&1; then
                    echo "[OK] Docker ativo: $(docker --version) | $(docker compose version)"
                    exit 0
                fi
                sleep 1.5
            done

            echo "[ERRO] O daemon Docker não respondeu a tempo."
            exit 1
            """;

        ResultadoComando res = await ExecutarBashWslAsync(
            distro,
            scriptDocker,
            comoRoot: true,
            log: log,
            registrarLinhasNoLog: true,
            timeout: TimeSpan.FromMinutes(15),
            ct: ct);

        if (!res.Sucesso)
        {
            throw new InvalidOperationException(
                $"Falha ao instalar ou inicializar o Docker no WSL '{distro}' (código {res.ExitCode}).\n{res.StdErr}");
        }
    }

    public async Task GarantirRegrasFirewallAsync(AuditorLog log, CancellationToken ct)
    {
        var regras = new[]
        {
            ("Advice Movidesk BI - SQL Server WSL2 (1433)", "1433"),
            ("Advice Movidesk BI - Apache Superset (8088)", "8088")
        };

        foreach ((string nomeRegra, string porta) in regras)
        {
            ResultadoComando res = await ExecutarProcessoAsync(
                "netsh",
                [
                    "advfirewall", "firewall", "show", "rule", $"name={nomeRegra}"
                ],
                Encoding.UTF8,
                log,
                registrarLinhasNoLog: false,
                timeout: TimeSpan.FromSeconds(15),
                ct: ct);

            if (!res.Sucesso)
            {
                ResultadoComando addRes = await ExecutarProcessoAsync(
                    "netsh",
                    [
                        "advfirewall", "firewall", "add", "rule",
                        $"name={nomeRegra}",
                        "dir=in",
                        "action=allow",
                        "protocol=TCP",
                        $"localport={porta}"
                    ],
                    Encoding.UTF8,
                    log,
                    registrarLinhasNoLog: false,
                    timeout: TimeSpan.FromSeconds(15),
                    ct: ct);

                if (addRes.Sucesso)
                {
                    log.Sucesso($"Regra de Firewall liberando TCP {porta} aplicada.");
                }
                else
                {
                    log.Aviso($"Não foi possível configurar regra de firewall TCP {porta} (verifique se o serviço está ativo).");
                }
            }
        }
    }

    public async Task<bool> AguardarHealthHttpAsync(
        string urlHealth,
        TimeSpan tempoMaximo,
        AuditorLog log,
        CancellationToken ct)
    {
        DateTime limite = DateTime.UtcNow.Add(tempoMaximo);
        while (DateTime.UtcNow < limite)
        {
            ct.ThrowIfCancellationRequested();
            try
            {
                using HttpResponseMessage resp = await HttpProbeClient.GetAsync(urlHealth, ct);
                if (resp.IsSuccessStatusCode)
                {
                    log.Sucesso($"Apache Superset respondendo HTTP 200 em {urlHealth}");
                    return true;
                }
            }
            catch (OperationCanceledException) when (ct.IsCancellationRequested)
            {
                throw;
            }
            catch
            {
                // Continua aguardando subida do gunicorn/flask no contêiner
            }

            await Task.Delay(TimeSpan.FromSeconds(2), ct);
        }

        return false;
    }

    private static string LimparCaracteresControle(string input)
    {
        if (string.IsNullOrEmpty(input))
        {
            return string.Empty;
        }

        return input.Replace("\0", string.Empty).TrimEnd();
    }

    private static bool EstaNoPath(string nomeExecutavel)
    {
        string? pathEnv = Environment.GetEnvironmentVariable("PATH");
        if (string.IsNullOrWhiteSpace(pathEnv))
        {
            return false;
        }

        foreach (string dir in pathEnv.Split(Path.PathSeparator, StringSplitOptions.RemoveEmptyEntries))
        {
            try
            {
                if (File.Exists(Path.Combine(dir.Trim(), nomeExecutavel)))
                {
                    return true;
                }
            }
            catch
            {
                // Ignora entrada inválida de PATH
            }
        }

        return false;
    }
}
