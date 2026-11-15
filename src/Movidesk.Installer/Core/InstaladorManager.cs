using System.Runtime.Versioning;

namespace Movidesk.Installer.Core;

/// <summary>
/// Orquestrador central das 7 etapas de implantação unificada
/// (Painel de Controle + WSL 2 Ubuntu + Docker + Apache Superset + Driver ODBC 18 + Dashboard Movidesk BI).
/// </summary>
[SupportedOSPlatform("windows")]
public sealed class InstaladorManager
{
    private readonly ExtratorArquivos _extrator;
    private readonly AtalhoManager _atalhoManager;
    private readonly WslEngine _wslEngine;

    public static IReadOnlyList<EtapaDefinicao> Etapas { get; } =
    [
        new(
            1,
            "STEP_1_PAINEL",
            "Extração do Painel de Controle",
            "Instalando a interface de gerenciamento do BI, configurando a chave da API Movidesk e criando atalhos na Área de Trabalho."),
        new(
            2,
            "STEP_2_WSL",
            "Ambiente Linux (WSL 2 Ubuntu)",
            "Este passo prepara o subsistema Linux (WSL 2 Ubuntu) no seu Windows, necessário para rodar o motor de dados."),
        new(
            3,
            "STEP_3_DOCKER",
            "Motor Docker & Docker Compose",
            "Instalando o orquestrador de contêineres Docker para executar o painel de BI de forma isolada e estável."),
        new(
            4,
            "STEP_4_SUPERSET",
            "Download & Inicialização do Superset",
            "Baixando a imagem oficial e inicializando a plataforma Apache Superset em contêiner."),
        new(
            5,
            "STEP_5_CONFIG",
            "Configuração Interna do Superset",
            "Configurando usuários administradores e inicializando o banco de dados interno da plataforma."),
        new(
            6,
            "STEP_6_ODBC",
            "Driver ODBC 18 (SQL Server)",
            "Instalando drivers de comunicação com o SQL Server (msodbcsql18) e conectores para leitura do MovideskDM."),
        new(
            7,
            "STEP_7_DEPLOY",
            "Deploy Final dos Dashboards Oficiais",
            "Carregando as visões, os 9 Datasets da camada mart e os 15 gráficos oficiais do Dashboard - Movidesk BI.")
    ];

    public InstaladorManager()
        : this(new ExtratorArquivos(), new AtalhoManager(), new WslEngine())
    {
    }

    public InstaladorManager(
        ExtratorArquivos extrator,
        AtalhoManager atalhoManager,
        WslEngine wslEngine)
    {
        _extrator = extrator;
        _atalhoManager = atalhoManager;
        _wslEngine = wslEngine;
    }

    public async Task<ResultadoInstalacao> ExecutarInstalacaoCompletaAsync(
        ConfiguracaoInstalacao config,
        AuditorLog log,
        IProgress<ProgressoEtapa>? progresso = null,
        CancellationToken ct = default)
    {
        ArgumentNullException.ThrowIfNull(config);
        ArgumentNullException.ThrowIfNull(log);

        string exePainel = Path.Combine(config.DiretorioInstalacao, "MovideskControlPanel.exe");
        string atalhoDesktop = string.Empty;
        bool deployPendenteBanco = false;

        try
        {
            // STEP 1 — Extração do Painel, API Key no appsettings.json e Atalho Desktop
            (exePainel, atalhoDesktop) = await ExecutarEtapaAsync(1, progresso, log, () =>
                ExecutarStep1ExtracaoPainelAsync(config, log), ct);

            // STEP 2 — Preparação do WSL 2 e Distro Ubuntu
            await ExecutarEtapaAsync(2, progresso, log, () =>
                _wslEngine.GarantirWsl2UbuntuAsync(config.WslDistro, log, ct), ct);

            // STEP 3 — Instalação e subida do Docker Engine + Compose no Ubuntu
            await ExecutarEtapaAsync(3, progresso, log, () =>
                _wslEngine.InstalarEIniciarDockerAsync(config.WslDistro, log, ct), ct);

            // STEP 4 — Exportação do docker-compose.yml / superset_config.py e docker compose up -d
            await ExecutarEtapaAsync(4, progresso, log, () =>
                ExecutarStep4DownloadSupersetAsync(config, log, ct), ct);

            // STEP 5 — Configuração Interna via docker exec (db upgrade, admin, init)
            await ExecutarEtapaAsync(5, progresso, log, () =>
                ExecutarStep5ConfiguracaoInternaAsync(config, log, ct), ct);

            // STEP 6 — Instalação do Driver ODBC msodbcsql18 + pyodbc/pymssql no contêiner
            await ExecutarEtapaAsync(6, progresso, log, () =>
                ExecutarStep6DriverOdbcAsync(config, log, ct), ct);

            // STEP 7 — Deploy Final das Visões e Gráficos Oficiais do Dashboard - Movidesk BI
            deployPendenteBanco = await ExecutarStep7ComToleranciaBancoAsync(config, log, progresso, ct);

            log.CopiarLogParaPastaInstalacao(config.DiretorioInstalacao);

            string resumo = deployPendenteBanco
                ? "Infraestrutura (Painel, WSL 2, Docker, Superset e Driver ODBC 18) implantada com sucesso! Apenas o provisionamento automático do Dashboard aguarda a criação/acesso ao banco MovideskDM no SQL Server."
                : "Implantação completa finalizada com sucesso! O Painel de Controle e o Dashboard - Movidesk BI estão prontos para uso.";

            return new ResultadoInstalacao
            {
                Sucesso = true,
                DeployDashboardPendenteBanco = deployPendenteBanco,
                DiretorioInstalacao = config.DiretorioInstalacao,
                CaminhoExecutavelPainel = exePainel,
                CaminhoAtalhoDesktop = atalhoDesktop,
                CaminhoArquivoLog = log.CaminhoArquivoLog,
                MensagemResumo = resumo
            };
        }
        catch (OperationCanceledException)
        {
            log.Aviso("Instalação cancelada pelo usuário.");
            log.CopiarLogParaPastaInstalacao(config.DiretorioInstalacao);

            return new ResultadoInstalacao
            {
                Sucesso = false,
                Cancelada = true,
                DiretorioInstalacao = config.DiretorioInstalacao,
                CaminhoExecutavelPainel = exePainel,
                CaminhoAtalhoDesktop = atalhoDesktop,
                CaminhoArquivoLog = log.CaminhoArquivoLog,
                MensagemResumo = "Instalação interrompida a pedido do operador."
            };
        }
        catch (ReinicioWindowsNecessarioException ex)
        {
            ReportarEtapa(progresso, 2, StatusEtapa.Aviso);
            log.Aviso(ex.Message);
            log.CopiarLogParaPastaInstalacao(config.DiretorioInstalacao);

            return new ResultadoInstalacao
            {
                Sucesso = false,
                ReinicioWindowsNecessario = true,
                DiretorioInstalacao = config.DiretorioInstalacao,
                CaminhoExecutavelPainel = exePainel,
                CaminhoAtalhoDesktop = atalhoDesktop,
                CaminhoArquivoLog = log.CaminhoArquivoLog,
                MensagemResumo = ex.Message
            };
        }
        catch (Exception ex)
        {
            log.Erro($"Falha crítica durante a implantação: {ex.Message}");
            log.CopiarLogParaPastaInstalacao(config.DiretorioInstalacao);

            return new ResultadoInstalacao
            {
                Sucesso = false,
                DiretorioInstalacao = config.DiretorioInstalacao,
                CaminhoExecutavelPainel = exePainel,
                CaminhoAtalhoDesktop = atalhoDesktop,
                CaminhoArquivoLog = log.CaminhoArquivoLog,
                MensagemResumo = ex.Message
            };
        }
    }

    private Task<(string CaminhoExe, string AtalhoDesktop)> ExecutarStep1ExtracaoPainelAsync(
        ConfiguracaoInstalacao config,
        AuditorLog log)
    {
        string pastaDestino = config.DiretorioInstalacao;
        string caminhoExe = _extrator.ExtrairPainelControle(pastaDestino, log);

        _extrator.ExtrairScriptsSqlAuxiliares(pastaDestino, log);
        _extrator.InjetarConfiguracaoAppSettings(pastaDestino, config, log);
        string caminhoIcone = _extrator.ExtrairIconeAdviceParaDisco(pastaDestino, log);

        string atalho = string.Empty;
        if (config.CriarAtalhoDesktop)
        {
            atalho = _atalhoManager.CriarAtalhoDesktop(
                nomeAtalho: "Painel Movidesk BI",
                caminhoExecutavel: caminhoExe,
                caminhoIcone: string.IsNullOrEmpty(caminhoIcone) ? caminhoExe : caminhoIcone,
                descricao: "Painel de Controle - Dashboard Movidesk BI (Advice Compliance Solutions)",
                workingDirectory: pastaDestino,
                log: log);
        }

        return Task.FromResult((caminhoExe, atalho));
    }

    private async Task ExecutarStep4DownloadSupersetAsync(
        ConfiguracaoInstalacao config,
        AuditorLog log,
        CancellationToken ct)
    {
        string dockerComposeYml = _extrator.ObterRecursoTextoUtf8Lf("docker-compose.yml");
        string supersetConfigPy = _extrator.ObterRecursoTextoUtf8Lf("superset_config.py");

        log.Aguardando($"Enviando arquivos de configuração para '{config.WslPastaSuperset}' no WSL ({config.WslDistro})...");
        await _wslEngine.CopiarTextoParaWslAsync(
            config.WslDistro,
            $"{config.WslPastaSuperset}/docker-compose.yml",
            dockerComposeYml,
            comoRoot: true,
            log,
            ct);

        await _wslEngine.CopiarTextoParaWslAsync(
            config.WslDistro,
            $"{config.WslPastaSuperset}/superset_config.py",
            supersetConfigPy,
            comoRoot: true,
            log,
            ct);

        string scriptCompose = $"""
            set -e
            cd "{config.WslPastaSuperset}"
            echo "[INF] Baixando imagem oficial Apache Superset..."
            docker compose pull
            echo "[INF] Subindo contêiner '{config.NomeConteinerSuperset}'..."
            docker compose up -d
            docker compose ps
            """;

        ResultadoComando res = await _wslEngine.ExecutarBashWslAsync(
            config.WslDistro,
            scriptCompose,
            comoRoot: true,
            log: log,
            registrarLinhasNoLog: true,
            timeout: TimeSpan.FromMinutes(20),
            ct: ct);

        if (!res.Sucesso)
        {
            throw new InvalidOperationException(
                $"Falha ao baixar ou iniciar os contêineres do Apache Superset (código {res.ExitCode}).\n{res.StdErr}");
        }

        log.Sucesso("Contêiner Apache Superset baixado e inicializado na porta 8088.");
    }

    private async Task ExecutarStep5ConfiguracaoInternaAsync(
        ConfiguracaoInstalacao config,
        AuditorLog log,
        CancellationToken ct)
    {
        string c = config.NomeConteinerSuperset;
        string user = EscaparArgBashSimples(config.SupersetUsuarioAdmin);
        string pass = EscaparArgBashSimples(config.SupersetSenhaAdmin);
        string email = EscaparArgBashSimples(config.SupersetEmailAdmin);

        string scriptInit = $"""
            set -e
            echo "[INF] Aguardando contêiner '{c}' estabilizar..."
            sleep 4

            echo "[INF] Atualizando metadados internos (superset db upgrade)..."
            docker exec "{c}" superset db upgrade

            echo "[INF] Criando usuário administrador '{user}' (se não existir)..."
            docker exec "{c}" superset fab create-admin \
                --username '{user}' \
                --firstname 'Admin' \
                --lastname 'Advice' \
                --email '{email}' \
                --password '{pass}' || true

            echo "[INF] Sincronizando permissões e roles padrão (superset init)..."
            docker exec "{c}" superset init
            """;

        ResultadoComando res = await _wslEngine.ExecutarBashWslAsync(
            config.WslDistro,
            scriptInit,
            comoRoot: true,
            log: log,
            registrarLinhasNoLog: true,
            timeout: TimeSpan.FromMinutes(10),
            ct: ct);

        if (!res.Sucesso)
        {
            throw new InvalidOperationException(
                $"Falha na inicialização interna do Superset via docker exec (código {res.ExitCode}).\n{res.StdErr}");
        }

        log.Aguardando("Validando resposta HTTP do servidor web Apache Superset (porta 8088)...");
        bool online = await _wslEngine.AguardarHealthHttpAsync(
            "http://localhost:8088/health",
            TimeSpan.FromSeconds(75),
            log,
            ct);

        if (!online)
        {
            log.Aviso("Endpoint /health demorou a responder no primeiro boot; seguindo com a instalação do driver ODBC.");
        }
    }

    private async Task ExecutarStep6DriverOdbcAsync(
        ConfiguracaoInstalacao config,
        AuditorLog log,
        CancellationToken ct)
    {
        string scriptOdbc = $$"""
            set -e
            CONTAINER="{{config.NomeConteinerSuperset}}"

            echo "[INF] Instalando Microsoft ODBC Driver 18 (msodbcsql18) no contêiner $CONTAINER..."
            docker exec -u 0 "$CONTAINER" bash -lc '
                set -e
                export DEBIAN_FRONTEND=noninteractive
                apt-get update -qq
                apt-get install -y -qq curl gnupg2 apt-transport-https ca-certificates unixodbc unixodbc-dev freetds-dev gcc

                . /etc/os-release
                DIST_ID=$(echo "${ID:-debian}" | tr "[:upper:]" "[:lower:]")
                VER_ID="${VERSION_ID:-12}"

                install -m 0755 -d /usr/share/keyrings
                curl -fsSL https://packages.microsoft.com/keys/microsoft.asc | gpg --dearmor --yes -o /usr/share/keyrings/microsoft-prod.gpg
                chmod a+r /usr/share/keyrings/microsoft-prod.gpg

                REPO_URL="https://packages.microsoft.com/config/${DIST_ID}/${VER_ID}/prod.list"
                if ! curl -fsSL "$REPO_URL" -o /etc/apt/sources.list.d/mssql-release.list; then
                    echo "[AVISO] Fallback de repositório para Debian 12 (bookworm)..."
                    curl -fsSL "https://packages.microsoft.com/config/debian/12/prod.list" -o /etc/apt/sources.list.d/mssql-release.list
                fi

                sed -i "s|signed-by=[^ ]*|signed-by=/usr/share/keyrings/microsoft-prod.gpg|g" /etc/apt/sources.list.d/mssql-release.list || true
                if ! grep -q "signed-by=" /etc/apt/sources.list.d/mssql-release.list; then
                    sed -i "s|^deb |deb [signed-by=/usr/share/keyrings/microsoft-prod.gpg] |" /etc/apt/sources.list.d/mssql-release.list
                fi

                apt-get update -qq
                ACCEPT_EULA=Y apt-get install -y -qq msodbcsql18

                echo "[INF] Instalando conectores Python SQL Server (pyodbc + pymssql + pillow)..."
                if [ -x /app/.venv/bin/python ] && command -v uv >/dev/null 2>&1; then
                    uv pip install --python /app/.venv/bin/python pyodbc pymssql pillow
                elif [ -x /app/.venv/bin/pip ]; then
                    /app/.venv/bin/pip install --no-cache-dir pyodbc pymssql pillow
                elif command -v pip3 >/dev/null 2>&1; then
                    pip3 install --no-cache-dir pyodbc pymssql pillow
                else
                    python3 -m pip install --no-cache-dir pyodbc pymssql pillow
                fi

                python3 -c "import pyodbc; print(\"[OK] Drivers ODBC carregados:\", pyodbc.drivers())" || true
            '

            echo "[INF] Reiniciando contêiner do Superset para efetivar drivers..."
            cd "{{config.WslPastaSuperset}}"
            docker compose restart
            """;

        ResultadoComando res = await _wslEngine.ExecutarBashWslAsync(
            config.WslDistro,
            scriptOdbc,
            comoRoot: true,
            log: log,
            registrarLinhasNoLog: true,
            timeout: TimeSpan.FromMinutes(15),
            ct: ct);

        if (!res.Sucesso)
        {
            throw new InvalidOperationException(
                $"Falha ao instalar o driver msodbcsql18 / conectores SQL Server no contêiner (código {res.ExitCode}).\n{res.StdErr}");
        }

        log.Aguardando("Aguardando Apache Superset retornar online após instalação do driver ODBC 18...");
        bool voltouOnline = await _wslEngine.AguardarHealthHttpAsync(
            "http://localhost:8088/health",
            TimeSpan.FromSeconds(90),
            log,
            ct);

        if (!voltouOnline)
        {
            throw new TimeoutException("O Apache Superset não respondeu em http://localhost:8088/health após reiniciar com o driver ODBC.");
        }
    }

    private async Task<bool> ExecutarStep7ComToleranciaBancoAsync(
        ConfiguracaoInstalacao config,
        AuditorLog log,
        IProgress<ProgressoEtapa>? progresso,
        CancellationToken ct)
    {
        EtapaDefinicao etapa = Etapas[6];
        log.Secao($"Etapa {etapa.Numero}/{Etapas.Count} — {etapa.Titulo}");
        log.Info(etapa.DescricaoUx);
        ReportarEtapa(progresso, 7, StatusEtapa.EmAndamento);

        try
        {
            if (config.ConfigurarFirewall)
            {
                await _wslEngine.GarantirRegrasFirewallAsync(log, ct);
            }

            string setupScriptPy = _extrator.ObterRecursoTextoUtf8Lf("setup_superset_auto.py");
            string scriptPathWsl = $"{config.WslPastaSuperset}/setup_superset_auto.py";
            await _wslEngine.CopiarTextoParaWslAsync(config.WslDistro, scriptPathWsl, setupScriptPy, comoRoot: true, log, ct);

            string userSuperset = EscaparArgBashSimples(config.SupersetUsuarioAdmin);
            string passSuperset = EscaparArgBashSimples(config.SupersetSenhaAdmin);
            string rawHost = string.IsNullOrWhiteSpace(config.SqlServerHost) ? "localhost" : config.SqlServerHost.Trim();
            string sqlHostExplicit = string.Empty;
            string sqlPort = "1433";

            bool ehHostLocal = rawHost.Equals("localhost", StringComparison.OrdinalIgnoreCase)
                || rawHost.Equals("127.0.0.1", StringComparison.OrdinalIgnoreCase)
                || rawHost.Equals(".", StringComparison.OrdinalIgnoreCase)
                || rawHost.Equals("(local)", StringComparison.OrdinalIgnoreCase)
                || rawHost.StartsWith("localhost\\", StringComparison.OrdinalIgnoreCase)
                || rawHost.StartsWith(".\\", StringComparison.OrdinalIgnoreCase);

            if (!ehHostLocal)
            {
                string hostSemInstancia = rawHost.Split('\\')[0];
                int sepIdx = hostSemInstancia.IndexOfAny([',', ':']);
                if (sepIdx > 0)
                {
                    sqlHostExplicit = hostSemInstancia[..sepIdx].Trim();
                    string possiblePort = hostSemInstancia[(sepIdx + 1)..].Trim();
                    if (int.TryParse(possiblePort, out _))
                    {
                        sqlPort = possiblePort;
                    }
                }
                else
                {
                    sqlHostExplicit = hostSemInstancia;
                }
            }

            string sqlUser = Uri.EscapeDataString(config.SqlServerUsuario);
            string sqlPass = Uri.EscapeDataString(config.SqlServerSenha);
            string sqlDb = Uri.EscapeDataString(config.SqlServerBanco);
            string containerName = config.NomeConteinerSuperset;

            // Descobre IP do host Windows alcançável pelo WSL2/Docker quando SQL estiver local
            string scriptDeploy = $$"""
                set -e
                EXPLICIT_HOST="{{EscaparArgBashSimples(sqlHostExplicit)}}"
                SQL_PORT="{{sqlPort}}"

                if [ -n "$EXPLICIT_HOST" ]; then
                    TARGET_HOST="$EXPLICIT_HOST"
                else
                    TARGET_HOST=$(ip route show default 2>/dev/null | awk '/default/ {print $3; exit}')
                    if [ -z "$TARGET_HOST" ]; then
                        TARGET_HOST=$(awk '/^nameserver/ {print $2; exit}' /etc/resolv.conf 2>/dev/null || true)
                    fi
                    if [ -z "$TARGET_HOST" ]; then
                        TARGET_HOST="172.29.112.1"
                    fi
                fi

                echo "[INF] Endereço SQL Server resolvido para o WSL2/Docker: ${TARGET_HOST}:${SQL_PORT}"

                if ! timeout 4 bash -c "cat < /dev/null > /dev/tcp/$TARGET_HOST/$SQL_PORT" 2>/dev/null; then
                    echo "[AVISO] Porta TCP ${SQL_PORT} do SQL Server em $TARGET_HOST não respondeu ao WSL."
                    exit 42
                fi

                DB_URI="mssql+pyodbc://{{sqlUser}}:{{sqlPass}}@${TARGET_HOST}:${SQL_PORT}/{{sqlDb}}?driver=ODBC+Driver+18+for+SQL+Server&TrustServerCertificate=yes"

                if docker exec "{{containerName}}" test -x /app/.venv/bin/python 2>/dev/null; then
                    docker cp "{{scriptPathWsl}}" "{{containerName}}:/tmp/setup_superset_auto.py"
                    docker exec "{{containerName}}" /app/.venv/bin/python /tmp/setup_superset_auto.py \
                        --url "http://127.0.0.1:8088" \
                        --username '{{userSuperset}}' \
                        --password '{{passSuperset}}' \
                        --db-name "MovideskDM" \
                        --db-uri "$DB_URI"
                else
                    python3 "{{scriptPathWsl}}" \
                        --url "http://localhost:8088" \
                        --username '{{userSuperset}}' \
                        --password '{{passSuperset}}' \
                        --db-name "MovideskDM" \
                        --db-uri "$DB_URI"
                fi
                """;

            ResultadoComando res = await _wslEngine.ExecutarBashWslAsync(
                config.WslDistro,
                scriptDeploy,
                comoRoot: true,
                log: log,
                registrarLinhasNoLog: true,
                timeout: TimeSpan.FromMinutes(10),
                ct: ct);

            if (res.ExitCode == 42 || (!res.Sucesso && IndicaBancoAindaNaoCriado(res)))
            {
                log.Aviso(
                    "SQL Server porta 1433 ou banco 'MovideskDM' ainda não acessível a partir do WSL2 neste momento. " +
                    $"Os scripts SQL foram salvos em '{Path.Combine(config.DiretorioInstalacao, "database")}'. " +
                    "Após criar o banco MovideskDM e liberar TCP/IP no SQL Server, abra o 'Painel Movidesk BI' e clique em 'Executar Setup Automático'.");
                ReportarEtapa(progresso, 7, StatusEtapa.Aviso);
                return true;
            }

            if (!res.Sucesso)
            {
                throw new InvalidOperationException(
                    $"Erro ao importar o Dashboard - Movidesk BI no Superset (código {res.ExitCode}).\n{res.StdErr}");
            }

            log.Sucesso("Dashboard - Movidesk BI (9 Datasets, 15 Gráficos e 3 Filtros Nativos) publicado com sucesso!");
            ReportarEtapa(progresso, 7, StatusEtapa.Concluida);
            return false;
        }
        catch (OperationCanceledException)
        {
            ReportarEtapa(progresso, 7, StatusEtapa.Aviso);
            throw;
        }
        catch (Exception ex)
        {
            ReportarEtapa(progresso, 7, StatusEtapa.Erro);
            throw new InvalidOperationException($"Falha na Etapa 7 (Deploy Final do Dashboard): {ex.Message}", ex);
        }
    }

    private async Task<T> ExecutarEtapaAsync<T>(
        int numeroEtapa,
        IProgress<ProgressoEtapa>? progresso,
        AuditorLog log,
        Func<Task<T>> acao,
        CancellationToken ct)
    {
        ct.ThrowIfCancellationRequested();
        EtapaDefinicao def = Etapas[numeroEtapa - 1];
        log.Secao($"Etapa {def.Numero}/{Etapas.Count} — {def.Titulo}");
        log.Info(def.DescricaoUx);
        ReportarEtapa(progresso, numeroEtapa, StatusEtapa.EmAndamento);

        try
        {
            T resultado = await acao();
            ReportarEtapa(progresso, numeroEtapa, StatusEtapa.Concluida);
            return resultado;
        }
        catch (OperationCanceledException)
        {
            ReportarEtapa(progresso, numeroEtapa, StatusEtapa.Aviso);
            throw;
        }
        catch (Exception)
        {
            ReportarEtapa(progresso, numeroEtapa, StatusEtapa.Erro);
            throw;
        }
    }

    private Task ExecutarEtapaAsync(
        int numeroEtapa,
        IProgress<ProgressoEtapa>? progresso,
        AuditorLog log,
        Func<Task> acao,
        CancellationToken ct)
    {
        return ExecutarEtapaAsync(numeroEtapa, progresso, log, async () =>
        {
            await acao();
            return true;
        }, ct);
    }

    private static void ReportarEtapa(IProgress<ProgressoEtapa>? progresso, int numeroEtapa, StatusEtapa status)
    {
        if (progresso is null) return;

        EtapaDefinicao def = Etapas[numeroEtapa - 1];
        int concluidas = status == StatusEtapa.Concluida
            ? numeroEtapa
            : Math.Max(0, numeroEtapa - 1);

        int percentual = (int)Math.Round(100.0 * concluidas / Etapas.Count);
        if (status == StatusEtapa.EmAndamento && percentual < 5)
        {
            percentual = 4;
        }

        progresso.Report(new ProgressoEtapa(
            EtapaAtual: numeroEtapa,
            TotalEtapas: Etapas.Count,
            TituloEtapa: def.Titulo,
            DescricaoUx: def.DescricaoUx,
            Status: status,
            PercentualGeral: Math.Clamp(percentual, 0, 100)));
    }

    private static string EscaparArgBashSimples(string valor) => valor.Replace("'", "'\"'\"'");

    private static bool IndicaBancoAindaNaoCriado(ResultadoComando res)
    {
        string texto = $"{res.StdOut}\n{res.StdErr}";
        return texto.Contains("Cannot open database", StringComparison.OrdinalIgnoreCase) ||
               texto.Contains("MovideskDM", StringComparison.OrdinalIgnoreCase) &&
               (texto.Contains("Login failed", StringComparison.OrdinalIgnoreCase) ||
                texto.Contains("does not exist", StringComparison.OrdinalIgnoreCase) ||
                texto.Contains("Invalid object name", StringComparison.OrdinalIgnoreCase) ||
                texto.Contains("could not connect", StringComparison.OrdinalIgnoreCase));
    }
}
