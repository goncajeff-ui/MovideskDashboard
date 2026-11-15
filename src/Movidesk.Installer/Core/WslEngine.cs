using System.Diagnostics;
using System.Net.Http;
using System.Net.NetworkInformation;
using System.Runtime.Versioning;
using System.Text;
using System.Text.RegularExpressions;

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

    private static readonly Regex AnsiEscapeRegex = new(@"\x1B\[[0-9;?]*[ -/]*[@-~]", RegexOptions.Compiled);

    /// <summary>
    /// Isola PATH Linux e DOCKER_CONFIG para impedir conflito com shims/credenciais do Docker Desktop no Windows.
    /// </summary>
    public const string ScriptIsolamentoDockerBash = """
        export PATH="/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
        unset DOCKER_HOST DOCKER_CONTEXT DOCKER_TLS_VERIFY DOCKER_CERT_PATH || true
        export DOCKER_CONFIG="/root/.docker-advice"
        mkdir -p "$DOCKER_CONFIG"
        if [ ! -f "$DOCKER_CONFIG/config.json" ]; then
            printf '{"auths":{}}\n' > "$DOCKER_CONFIG/config.json"
        fi
        """;

    public const string HelperComposeBash = """
        compose_cmd() {
            if docker compose version >/dev/null 2>&1; then
                docker compose "$@"
            elif command -v docker-compose >/dev/null 2>&1; then
                docker-compose "$@"
            else
                echo "[ERRO] Nem 'docker compose' (v2) nem 'docker-compose' foi encontrado no WSL." >&2
                return 1
            fi
        }
        """;

    public const string HelperIniciarDaemonDockerBash = """
        garantir_daemon_docker() {
            if docker info >/dev/null 2>&1; then
                return 0
            fi

            echo "[INF] Iniciando daemon Docker Engine..."
            if [ "$(ps -p 1 -o comm= 2>/dev/null || true)" = "systemd" ] && command -v systemctl >/dev/null 2>&1; then
                systemctl unmask docker docker.socket containerd >/dev/null 2>&1 || true
                systemctl enable --now docker >/dev/null 2>&1 || service docker start >/dev/null 2>&1 || true
            else
                service docker start >/dev/null 2>&1 || true
                sleep 2
                if ! docker info >/dev/null 2>&1; then
                    echo "[INF] Subindo dockerd em background desacoplado..."
                    setsid dockerd >/var/log/advice-dockerd.log 2>&1 < /dev/null &
                fi
            fi

            for i in $(seq 1 25); do
                if docker info >/dev/null 2>&1; then
                    return 0
                fi
                sleep 1.5
            done

            echo "[ERRO] O daemon Docker não respondeu após tentativa de inicialização." >&2
            if [ "$(ps -p 1 -o comm= 2>/dev/null || true)" = "systemd" ] && command -v journalctl >/dev/null 2>&1; then
                journalctl -u docker --no-pager -n 15 >&2 || true
            fi
            if [ -f /var/log/advice-dockerd.log ]; then
                tail -n 15 /var/log/advice-dockerd.log >&2 || true
            fi
            return 1
        }
        """;

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
        byte[]? dadosStdin = null,
        CancellationToken ct = default)
    {
        var startInfo = new ProcessStartInfo
        {
            FileName = executavel,
            UseShellExecute = false,
            CreateNoWindow = true,
            RedirectStandardOutput = true,
            RedirectStandardError = true,
            RedirectStandardInput = dadosStdin is not null,
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

        if (dadosStdin is not null)
        {
            try
            {
                await process.StandardInput.BaseStream.WriteAsync(dadosStdin, ct);
                await process.StandardInput.BaseStream.FlushAsync(ct);
            }
            finally
            {
                process.StandardInput.Close();
            }
        }

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
            dadosStdin: null,
            ct: ct);
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
        byte[] scriptBytes = Encoding.UTF8.GetBytes(normalized);

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
        args.Add("-l");
        args.Add("-s");

        return ExecutarProcessoAsync(
            ResolverCaminhoWsl(),
            args,
            Encoding.UTF8,
            log,
            registrarLinhasNoLog,
            timeout ?? TimeSpan.FromMinutes(15),
            dadosStdin: scriptBytes,
            ct: ct);
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
        byte[] bytes = Encoding.UTF8.GetBytes(lfText);

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
        args.Add("-c");
        args.Add("mkdir -p \"$(dirname \"$1\")\" && cat > \"$1\" && chmod 644 \"$1\"");
        args.Add("bash");
        args.Add(caminhoDestinoWsl);

        ResultadoComando res = await ExecutarProcessoAsync(
            ResolverCaminhoWsl(),
            args,
            Encoding.UTF8,
            log,
            registrarLinhasNoLog: false,
            timeout: TimeSpan.FromMinutes(2),
            dadosStdin: bytes,
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
                ResultadoComando recheck = await ExecutarWslNativoAsync(["-l", "-q"], log, registrarLinhasNoLog: false, ct: ct);
                bool registradaAgora = recheck.StdOut
                    .Split(['\r', '\n'], StringSplitOptions.RemoveEmptyEntries)
                    .Any(line => line.Trim().Contains(distro, StringComparison.OrdinalIgnoreCase));

                if (!registradaAgora)
                {
                    throw new InvalidOperationException(
                        $"Falha ao instalar WSL 2 / {distro} (código {installRes.ExitCode}).\n{FormatarResumoErro(installRes)}");
                }
            }
        }
        else
        {
            log.Sucesso($"Distribuição '{distro}' já encontrada no WSL.");
        }

        log.Aguardando($"Validando versão 2 do WSL para '{distro}'...");
        await ExecutarWslNativoAsync(["--set-version", distro, "2"], log, registrarLinhasNoLog: false, ct: ct);

        ResultadoComando probe = await ExecutarBashWslAsync(
            distro,
            """
            NEEDS_RESTART=0
            if [ ! -f /etc/wsl.conf ]; then
                printf "[boot]\nsystemd=true\n" > /etc/wsl.conf
                NEEDS_RESTART=1
            elif ! grep -qiE '^\s*systemd\s*=\s*true\b' /etc/wsl.conf; then
                if grep -qiE '^\s*\[boot\]' /etc/wsl.conf; then
                    sed -i '/^\s*\[boot\]/I a systemd=true' /etc/wsl.conf
                else
                    printf "\n[boot]\nsystemd=true\n" >> /etc/wsl.conf
                fi
                NEEDS_RESTART=1
            fi

            PID1_COMM=$(ps -p 1 -o comm= 2>/dev/null || echo "unknown")
            echo "WSL2_UBUNTU_PRONTO: $(uname -r) | PID1=$PID1_COMM"
            echo "WSL_NEEDS_RESTART=$NEEDS_RESTART"
            """,
            comoRoot: true,
            log: log,
            registrarLinhasNoLog: true,
            timeout: TimeSpan.FromMinutes(3),
            ct: ct);

        if (!probe.Sucesso)
        {
            throw new InvalidOperationException(
                $"Não foi possível iniciar o ambiente Bash no WSL '{distro}'. Caso tenha acabado de habilitar o WSL, reinicie o Windows.\n{FormatarResumoErro(probe)}");
        }

        bool precisaTerminarDistro =
            probe.StdOut.Contains("WSL_NEEDS_RESTART=1", StringComparison.Ordinal) ||
            !probe.StdOut.Contains("PID1=systemd", StringComparison.Ordinal);

        if (precisaTerminarDistro)
        {
            log.Aguardando($"Reiniciando instância WSL '{distro}' para efetivar systemd/kernel...");
            await ExecutarWslNativoAsync(["--terminate", distro], log, registrarLinhasNoLog: false, timeout: TimeSpan.FromSeconds(45), ct: ct);
            await Task.Delay(TimeSpan.FromSeconds(2), ct);

            ResultadoComando reprobe = await ExecutarBashWslAsync(
                distro,
                """
                echo "WSL2_REINICIADO: $(uname -r) | PID1=$(ps -p 1 -o comm= 2>/dev/null || echo unknown)"
                """,
                comoRoot: true,
                log: log,
                registrarLinhasNoLog: true,
                timeout: TimeSpan.FromMinutes(3),
                ct: ct);

            if (!reprobe.Sucesso)
            {
                throw new InvalidOperationException(
                    $"O WSL '{distro}' não respondeu após o reinício para ativação do systemd.\n{FormatarResumoErro(reprobe)}");
            }
        }

        log.Sucesso($"Ambiente WSL 2 '{distro}' operacional e configurado.");
    }

    public async Task InstalarEIniciarDockerAsync(string distro, AuditorLog log, CancellationToken ct)
    {
        string scriptDocker = $$"""
            set -e
            export DEBIAN_FRONTEND=noninteractive

            {{ScriptIsolamentoDockerBash}}
            {{HelperComposeBash}}
            {{HelperIniciarDaemonDockerBash}}

            # Remove symlinks quebrados ou herdados de antiga integração do Docker Desktop no WSL
            for bin_path in /usr/bin/docker /usr/bin/docker-compose /usr/local/bin/docker /usr/local/bin/docker-compose; do
                if [ -L "$bin_path" ]; then
                    target=$(readlink "$bin_path" || true)
                    if [[ "$target" == *docker-desktop* ]] || [ ! -e "$bin_path" ]; then
                        echo "[AVISO] Removendo symlink legado do Docker Desktop: $bin_path -> $target"
                        rm -f "$bin_path" || true
                    fi
                fi
            done

            if ! command -v docker >/dev/null 2>&1 || { ! docker compose version >/dev/null 2>&1 && ! command -v docker-compose >/dev/null 2>&1; }; then
                echo "[INF] Docker Engine ou Docker Compose ausente. Instalando no Ubuntu..."
                apt-get update -qq
                apt-get install -y -qq ca-certificates curl gnupg lsb-release apt-transport-https iptables

                install -m 0755 -d /etc/apt/keyrings
                if curl -fsSL --connect-timeout 12 https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc; then
                    chmod a+r /etc/apt/keyrings/docker.asc
                    . /etc/os-release
                    echo \
                      "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu \
                      ${VERSION_CODENAME:-jammy} stable" | tee /etc/apt/sources.list.d/docker.list > /dev/null

                    apt-get update -qq || true
                    if ! apt-get install -y -qq docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin; then
                        echo "[AVISO] Pacote oficial docker-ce falhou; aplicando fallback nativo Ubuntu (docker.io)..."
                        rm -f /etc/apt/sources.list.d/docker.list || true
                        apt-get update -qq
                        apt-get install -y -qq docker.io docker-compose-v2 || apt-get install -y -qq docker.io docker-compose || apt-get install -y -qq docker.io
                    fi
                else
                    echo "[AVISO] Repositório download.docker.com inacessível; instalando via pacote nativo Ubuntu..."
                    apt-get install -y -qq docker.io docker-compose-v2 || apt-get install -y -qq docker.io docker-compose || apt-get install -y -qq docker.io
                fi
            else
                echo "[OK] Docker e Docker Compose já estão instalados no WSL."
            fi

            # Configuração segura de rotação de logs no daemon.json para evitar estouro do disco virtual ext4.vhdx
            mkdir -p /etc/docker
            if [ ! -f /etc/docker/daemon.json ]; then
                printf '{\n  "log-driver": "json-file",\n  "log-opts": {\n    "max-size": "10m",\n    "max-file": "3"\n  }\n}\n' > /etc/docker/daemon.json
            fi

            # Só alterna para iptables-legacy se o backend atual (nf_tables) realmente falhar na tabela NAT
            if command -v iptables >/dev/null 2>&1; then
                if ! iptables -t nat -L -n >/dev/null 2>&1; then
                    echo "[AVISO] iptables padrão incompatível com o kernel WSL; alternando para iptables-legacy..."
                    if command -v update-alternatives >/dev/null 2>&1 && [ -x /usr/sbin/iptables-legacy ]; then
                        update-alternatives --set iptables /usr/sbin/iptables-legacy >/dev/null 2>&1 || true
                        if [ -x /usr/sbin/ip6tables-legacy ]; then
                            update-alternatives --set ip6tables /usr/sbin/ip6tables-legacy >/dev/null 2>&1 || true
                        fi
                    fi
                fi
            fi

            DEFAULT_USER=$(awk -F: '$3 >= 1000 && $3 < 60000 {print $1; exit}' /etc/passwd)
            if [ -n "$DEFAULT_USER" ]; then
                usermod -aG docker "$DEFAULT_USER" || true
            fi

            garantir_daemon_docker

            if ! docker network inspect bridge >/dev/null 2>&1; then
                echo "[AVISO] Rede bridge Docker não detectada; validando iptables e reiniciando Docker..."
                if command -v update-alternatives >/dev/null 2>&1 && [ -x /usr/sbin/iptables-legacy ]; then
                    update-alternatives --set iptables /usr/sbin/iptables-legacy >/dev/null 2>&1 || true
                    [ -x /usr/sbin/ip6tables-legacy ] && update-alternatives --set ip6tables /usr/sbin/ip6tables-legacy >/dev/null 2>&1 || true
                fi
                systemctl restart docker >/dev/null 2>&1 || service docker restart >/dev/null 2>&1 || true
                sleep 2
                docker network inspect bridge >/dev/null 2>&1
            fi

            COMPOSE_VER=$(compose_cmd version --short 2>/dev/null || compose_cmd version 2>/dev/null | head -n 1 || echo "desconhecido")
            echo "[OK] Docker ativo: $(docker --version) | Compose: $COMPOSE_VER"
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
                $"Falha ao instalar ou inicializar o Docker no WSL '{distro}' (código {res.ExitCode}).\n{FormatarResumoErro(res)}");
        }
    }

    public bool PortaTcpEmUsoNoWindows(int porta)
    {
        try
        {
            return IPGlobalProperties.GetIPGlobalProperties()
                .GetActiveTcpListeners()
                .Any(ep => ep.Port == porta);
        }
        catch
        {
            return false;
        }
    }

    public static string FormatarResumoErro(ResultadoComando res, int maxLinhas = 18, int maxCaracteres = 1400)
    {
        string[] FiltrarLinhas(string texto, bool removerRuidoDocker) =>
            texto
                .Split(['\r', '\n'], StringSplitOptions.RemoveEmptyEntries)
                .Select(l => AnsiEscapeRegex.Replace(l, string.Empty).Trim())
                .Where(l => !string.IsNullOrWhiteSpace(l) && (!removerRuidoDocker || !EhLinhaRuidoProgressoDocker(l)))
                .ToArray();

        string[] linhas = !string.IsNullOrWhiteSpace(res.StdErr)
            ? FiltrarLinhas(res.StdErr, removerRuidoDocker: true)
            : [];

        if (linhas.Length == 0 && !string.IsNullOrWhiteSpace(res.StdOut))
        {
            linhas = FiltrarLinhas(res.StdOut, removerRuidoDocker: true);
        }

        if (linhas.Length == 0)
        {
            string rawFallback = string.IsNullOrWhiteSpace(res.StdErr) ? res.StdOut : res.StdErr;
            if (!string.IsNullOrWhiteSpace(rawFallback))
            {
                linhas = FiltrarLinhas(rawFallback, removerRuidoDocker: false);
            }
        }

        if (linhas.Length == 0)
        {
            return "Sem detalhes adicionais emitidos em stderr/stdout.";
        }

        int omitidas = Math.Max(0, linhas.Length - maxLinhas);
        IEnumerable<string> cauda = omitidas > 0 ? linhas.Skip(omitidas) : linhas;

        var sb = new StringBuilder();
        if (omitidas > 0)
        {
            sb.AppendLine($"[... {omitidas} linha(s) anteriores omitida(s); consulte o arquivo de log completo ...]");
        }

        foreach (string linha in cauda)
        {
            sb.AppendLine(linha);
        }

        string resultado = sb.ToString().Trim();
        if (resultado.Length > maxCaracteres)
        {
            string slice = resultado[^maxCaracteres..];
            int firstNewLine = slice.IndexOf('\n');
            if (firstNewLine >= 0 && firstNewLine < slice.Length - 1)
            {
                slice = slice[(firstNewLine + 1)..];
            }

            resultado = "[... início omitido; consulte o arquivo de log completo ...]\n" + slice.TrimStart();
        }

        return resultado;
    }

    private static bool EhLinhaRuidoProgressoDocker(string linha)
    {
        return linha.Contains("Downloading [", StringComparison.OrdinalIgnoreCase) ||
               linha.Contains("Extracting [", StringComparison.OrdinalIgnoreCase) ||
               linha.Contains(": Downloading", StringComparison.OrdinalIgnoreCase) ||
               linha.Contains(": Extracting", StringComparison.OrdinalIgnoreCase) ||
               linha.Contains(": Verifying Checksum", StringComparison.OrdinalIgnoreCase) ||
               linha.Contains(": Pulling fs layer", StringComparison.OrdinalIgnoreCase) ||
               linha.Contains(": Download complete", StringComparison.OrdinalIgnoreCase) ||
               linha.Contains(": Waiting", StringComparison.OrdinalIgnoreCase) ||
               linha.Contains(": Pull complete", StringComparison.OrdinalIgnoreCase);
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
            // Remove regra anterior para garantir que profile=any seja sempre aplicado
            await ExecutarProcessoAsync(
                "netsh",
                [
                    "advfirewall", "firewall", "delete", "rule", $"name={nomeRegra}"
                ],
                Encoding.UTF8,
                log,
                registrarLinhasNoLog: false,
                timeout: TimeSpan.FromSeconds(10),
                ct: ct);

            ResultadoComando addRes = await ExecutarProcessoAsync(
                "netsh",
                [
                    "advfirewall", "firewall", "add", "rule",
                    $"name={nomeRegra}",
                    "dir=in",
                    "action=allow",
                    "protocol=TCP",
                    $"localport={porta}",
                    "profile=any"
                ],
                Encoding.UTF8,
                log,
                registrarLinhasNoLog: false,
                timeout: TimeSpan.FromSeconds(15),
                ct: ct);

            if (addRes.Sucesso)
            {
                log.Sucesso($"Regra de Firewall liberando TCP {porta} (todos os perfis de rede/WSL) aplicada.");
            }
            else
            {
                log.Aviso($"Não foi possível configurar regra de firewall TCP {porta}: {addRes.StdErr}");
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

        string clean = AnsiEscapeRegex.Replace(input, string.Empty);
        return clean.Replace("\0", string.Empty).TrimEnd();
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
