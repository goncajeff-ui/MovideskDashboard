using System.Runtime.Versioning;
using System.Security.Cryptography;

namespace Movidesk.Installer.Core;

/// <summary>
/// Orquestrador central das 4 etapas de implantação unificada
/// (1. Aplicação & Banco de Dados | 2. Infraestrutura Linux & Docker | 3. Plataforma Apache Superset | 4. Deploy Dashboard).
/// </summary>
[SupportedOSPlatform("windows")]
public sealed class InstaladorManager
{
    private readonly ExtratorArquivos _extrator;
    private readonly AtalhoManager _atalhoManager;
    private readonly WslEngine _wslEngine;
    private readonly SqlDatabaseDeployer _sqlDeployer;

    public static IReadOnlyList<EtapaDefinicao> Etapas { get; } =
    [
        new(
            1,
            "STEP_1_APP_BANCO",
            "Aplicação & Banco de Dados (MovideskDM)",
            "Instalando o Painel de Controle (.NET 8), criando atalhos e provisionando o banco MovideskDM com tabelas, índices e views nativamente no SQL Server."),
        new(
            2,
            "STEP_2_INFRA_WSL_DOCKER",
            "Infraestrutura Linux & Docker (WSL 2)",
            "Preparando o subsistema Linux (WSL 2 Ubuntu) e inicializando o motor de contêineres Docker para isolamento dos serviços."),
        new(
            3,
            "STEP_3_SUPERSET",
            "Plataforma Apache Superset & Conectores",
            "Inicializando o contêiner Apache Superset 6.1.0 na porta 8088, metadados internos e drivers ODBC 18 para SQL Server."),
        new(
            4,
            "STEP_4_DASHBOARD",
            "Deploy do Dashboard Movidesk BI",
            "Conectando a base MovideskDM ao Superset, registrando os 9 Datasets oficiais e publicando os 15 gráficos do Dashboard.")
    ];

    public InstaladorManager()
        : this(new ExtratorArquivos(), new AtalhoManager(), new WslEngine(), new SqlDatabaseDeployer())
    {
    }

    public InstaladorManager(
        ExtratorArquivos extrator,
        AtalhoManager atalhoManager,
        WslEngine wslEngine,
        SqlDatabaseDeployer sqlDeployer)
    {
        _extrator = extrator;
        _atalhoManager = atalhoManager;
        _wslEngine = wslEngine;
        _sqlDeployer = sqlDeployer;
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
            // ETAPA 1/4 — Aplicação & Banco de Dados (MovideskDM)
            (exePainel, atalhoDesktop) = await ExecutarEtapaAsync(1, progresso, log, async () =>
            {
                var r = await ExecutarStep1ExtracaoPainelAsync(config, log);
                await _sqlDeployer.GarantirBancoEExecutarScriptsAsync(config, log, ct);
                return r;
            }, ct);

            // ETAPA 2/4 — Infraestrutura Linux & Docker (WSL 2)
            await ExecutarEtapaAsync(2, progresso, log, async () =>
            {
                await _wslEngine.GarantirWsl2UbuntuAsync(config.WslDistro, log, ct);
                await _wslEngine.InstalarEIniciarDockerAsync(config.WslDistro, log, ct);
            }, ct);

            // ETAPA 3/4 — Plataforma Apache Superset & Conectores
            await ExecutarEtapaAsync(3, progresso, log, async () =>
            {
                await ExecutarStepDownloadSupersetAsync(config, log, ct);
                await ExecutarStepConfiguracaoInternaAsync(config, log, ct);
                await ExecutarStepDriverOdbcAsync(config, log, ct);
            }, ct);

            // ETAPA 4/4 — Deploy Final do Dashboard Movidesk BI
            deployPendenteBanco = await ExecutarStepDeployDashboardAsync(config, log, progresso, ct);

            log.CopiarLogParaPastaInstalacao(config.DiretorioInstalacao);

            string resumo = deployPendenteBanco
                ? "Infraestrutura (Painel, WSL 2, Docker, Superset e Driver ODBC 18) implantada com sucesso! O provisionamento dos dashboards no Superset aguarda a conexão com o banco MovideskDM no SQL Server."
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

    private async Task ExecutarStepDownloadSupersetAsync(
        ConfiguracaoInstalacao config,
        AuditorLog log,
        CancellationToken ct)
    {
        string dockerComposeYml = _extrator.ObterRecursoTextoUtf8Lf("docker-compose.yml");
        string supersetConfigPy = _extrator.ObterRecursoTextoUtf8Lf("superset_config.py");
        string secretGerada = Convert.ToHexString(RandomNumberGenerator.GetBytes(24)).ToLowerInvariant();

        log.Aguardando($"Enviando arquivos de configuração seguros para '{config.WslPastaSuperset}' no WSL ({config.WslDistro})...");
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

        string pastaSuperset = EscaparArgBashSimples(config.WslPastaSuperset);
        string containerName = EscaparArgBashSimples(config.NomeConteinerSuperset);

        string scriptPrePull = $$"""
            set -e
            export DEBIAN_FRONTEND=noninteractive

            {{WslEngine.ScriptIsolamentoDockerBash}}
            {{WslEngine.HelperComposeBash}}
            {{WslEngine.HelperIniciarDaemonDockerBash}}

            mkdir -p '{{pastaSuperset}}'
            chmod 755 '{{pastaSuperset}}'
            if [ ! -s '{{pastaSuperset}}/.env' ] || ! grep -q '^SUPERSET_SECRET_KEY=' '{{pastaSuperset}}/.env'; then
                printf 'SUPERSET_SECRET_KEY={{secretGerada}}\nTZ=America/Sao_Paulo\n' > '{{pastaSuperset}}/.env'
                chmod 600 '{{pastaSuperset}}/.env'
                echo "[OK] Arquivo .env criado com chave criptográfica exclusiva (chmod 600)."
            else
                chmod 600 '{{pastaSuperset}}/.env'
                echo "[OK] Mantendo SUPERSET_SECRET_KEY existente no .env."
            fi

            garantir_daemon_docker

            # Limpa execução anterior para instalação idempotente e libera porta 8088 de instância legada
            docker rm -f '{{containerName}}' >/dev/null 2>&1 || true
            pkill -f '[s]uperset run' >/dev/null 2>&1 || true

            if docker image inspect apache/superset:6.1.0 >/dev/null 2>&1; then
                echo "[OK] Imagem apache/superset:6.1.0 já disponível no cache local do Docker."
            else
                TARGET_FS="/var/lib/docker"
                [ -d "$TARGET_FS" ] || TARGET_FS="/"
                FREE_MB=$(df -Pm "$TARGET_FS" 2>/dev/null | awk 'NR==2 {print $4}')
                echo "[INF] Espaço livre em disco no WSL2 ($TARGET_FS): ${FREE_MB:-desconhecido} MB"
                if [ -n "$FREE_MB" ] && [ "$FREE_MB" -lt 2000 ]; then
                    echo "[ERRO] Espaço em disco insuficiente no WSL2 (${FREE_MB} MB livres; recomendado >= 2000 MB)." >&2
                    exit 1
                fi

                echo "[INF] Testando conectividade HTTPS com Docker Hub (registry-1.docker.io)..."
                if command -v curl >/dev/null 2>&1; then
                    HTTP_HUB=$(curl -sS -o /dev/null -w '%{http_code}' --connect-timeout 10 --max-time 15 https://registry-1.docker.io/v2/ || echo "000")
                    if [ "$HTTP_HUB" = "000" ]; then
                        echo "[ERRO] Sem acesso HTTPS ao Docker Hub a partir do WSL2. DNS atual (/etc/resolv.conf):" >&2
                        grep -E '^\s*nameserver' /etc/resolv.conf >&2 || true
                        echo "[ERRO] Verifique internet, DNS do WSL ou regras de proxy/firewall corporativo." >&2
                        exit 1
                    fi
                elif ! timeout 6 bash -c 'cat < /dev/null > /dev/tcp/registry-1.docker.io/443' 2>/dev/null; then
                    echo "[ERRO] Sem conexão TCP/443 com registry-1.docker.io a partir do WSL2." >&2
                    grep -E '^\s*nameserver' /etc/resolv.conf >&2 || true
                    exit 1
                fi

                echo "[INF] Baixando imagem oficial apache/superset:6.1.0 (modo silencioso; aguarde 1 a 5 minutos)..."
                PULL_RC=1
                for tentativa in 1 2; do
                    docker pull -q apache/superset:6.1.0 &
                    PULL_PID=$!
                    ELAPSED=0
                    while kill -0 "$PULL_PID" 2>/dev/null; do
                        sleep 2
                        ELAPSED=$((ELAPSED + 2))
                        if [ $((ELAPSED % 20)) -eq 0 ] && kill -0 "$PULL_PID" 2>/dev/null; then
                            echo "[INF] Download apache/superset:6.1.0 em andamento (${ELAPSED}s, tentativa ${tentativa}/2)..."
                        fi
                    done

                    set +e
                    wait "$PULL_PID"
                    PULL_RC=$?
                    set -e

                    if [ "$PULL_RC" -eq 0 ]; then
                        break
                    fi

                    if [ "$tentativa" -lt 2 ]; then
                        echo "[AVISO] Tentativa $tentativa falhou (código $PULL_RC). Repetindo download em 5s..." >&2
                        sleep 5
                    fi
                done

                if [ "$PULL_RC" -ne 0 ]; then
                    echo "[ERRO] Falha ao baixar apache/superset:6.1.0 após 2 tentativas (código $PULL_RC)." >&2
                    exit "$PULL_RC"
                fi

                echo "[OK] Imagem apache/superset:6.1.0 baixada e verificada."
            fi
            """;

        ResultadoComando resPre = await _wslEngine.ExecutarBashWslAsync(
            config.WslDistro,
            scriptPrePull,
            comoRoot: true,
            log: log,
            registrarLinhasNoLog: true,
            timeout: TimeSpan.FromMinutes(20),
            ct: ct);

        if (!resPre.Sucesso)
        {
            throw new InvalidOperationException(
                $"Falha no pré-voo ou download da imagem Superset 6.1.0 (código {resPre.ExitCode}).\n{WslEngine.FormatarResumoErro(resPre)}");
        }

        bool portaOcupada = false;
        for (int tentativa = 0; tentativa < 4; tentativa++)
        {
            portaOcupada = _wslEngine.PortaTcpEmUsoNoWindows(8088);
            if (!portaOcupada)
            {
                break;
            }
            await Task.Delay(1000, ct);
        }

        if (portaOcupada)
        {
            bool ehSupersetJaAtivo = await _wslEngine.AguardarHealthHttpAsync(
                "http://localhost:8088/health",
                TimeSpan.FromSeconds(2),
                log,
                ct);

            if (!ehSupersetJaAtivo)
            {
                throw new InvalidOperationException(
                    "A porta TCP 8088 já está ocupada por outro processo no Windows (ex.: IIS, outro serviço web ou proxy).\n" +
                    "Por favor, libere a porta 8088 no servidor e execute a instalação novamente.");
            }

            log.Info("Porta 8088 já alocada para o Apache Superset no WSL2; reutilizando instância.");
        }

        string scriptComposeUp = $$"""
            set -e

            {{WslEngine.ScriptIsolamentoDockerBash}}
            {{WslEngine.HelperComposeBash}}

            cd '{{pastaSuperset}}'
            if [ ! -f docker-compose.yml ] || [ ! -f superset_config.py ]; then
                echo "[ERRO] Arquivos docker-compose.yml ou superset_config.py ausentes em '{{pastaSuperset}}'." >&2
                exit 1
            fi

            echo "[INF] Validando sintaxe do docker-compose.yml..."
            compose_cmd config -q 2>/dev/null || compose_cmd config >/dev/null

            echo "[INF] Subindo contêiner '{{containerName}}' na porta 8088..."
            compose_cmd up -d --remove-orphans

            sleep 3
            RUNNING_ID=$(docker ps -q --filter "name=^{{containerName}}$" --filter "status=running" 2>/dev/null || true)
            if [ -z "$RUNNING_ID" ]; then
                echo "[ERRO] O contêiner '{{containerName}}' encerrou logo após 'compose up -d'. Últimas linhas de log:" >&2
                docker logs --tail 25 '{{containerName}}' >&2 || true
                exit 1
            fi

            compose_cmd ps
            """;

        ResultadoComando resUp = await _wslEngine.ExecutarBashWslAsync(
            config.WslDistro,
            scriptComposeUp,
            comoRoot: true,
            log: log,
            registrarLinhasNoLog: true,
            timeout: TimeSpan.FromMinutes(5),
            ct: ct);

        if (!resUp.Sucesso)
        {
            throw new InvalidOperationException(
                $"Falha ao subir o contêiner '{config.NomeConteinerSuperset}' no Docker (código {resUp.ExitCode}).\n{WslEngine.FormatarResumoErro(resUp)}");
        }

        log.Sucesso("Contêiner Apache Superset 6.1.0 baixado e inicializado na porta 8088.");
    }

    private async Task ExecutarStepConfiguracaoInternaAsync(
        ConfiguracaoInstalacao config,
        AuditorLog log,
        CancellationToken ct)
    {
        string c = EscaparArgBashSimples(config.NomeConteinerSuperset);
        string user = EscaparArgBashSimples(config.SupersetUsuarioAdmin);
        string pass = EscaparArgBashSimples(config.SupersetSenhaAdmin);
        string email = EscaparArgBashSimples(config.SupersetEmailAdmin);

        string scriptInit = $$"""
            set -e

            {{WslEngine.ScriptIsolamentoDockerBash}}

            echo "[INF] Aguardando contêiner '{{c}}' estabilizar..."
            READY_OK=0
            for i in $(seq 1 15); do
                if [ -n "$(docker ps -q --filter 'name=^{{c}}$' --filter 'status=running' 2>/dev/null || true)" ]; then
                    READY_OK=1
                    break
                fi
                sleep 2
            done

            if [ "$READY_OK" -ne 1 ]; then
                echo "[ERRO] O contêiner '{{c}}' não está em execução." >&2
                docker logs --tail 25 '{{c}}' >&2 || true
                exit 1
            fi

            echo "[INF] Garantindo permissões em /app/superset_home..."
            docker exec -u 0 '{{c}}' bash -c 'mkdir -p /app/superset_home && chown -R superset:superset /app/superset_home'

            echo "[INF] Atualizando metadados internos (superset db upgrade)..."
            docker exec '{{c}}' superset db upgrade

            echo "[INF] Criando usuário administrador '{{user}}' (se não existir)..."
            docker exec '{{c}}' superset fab create-admin \
                --username '{{user}}' \
                --firstname 'Admin' \
                --lastname 'Advice' \
                --email '{{email}}' \
                --password '{{pass}}' || true

            echo "[INF] Sincronizando permissões e roles padrão (superset init)..."
            docker exec '{{c}}' superset init
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
                $"Falha na inicialização interna do Superset via docker exec (código {res.ExitCode}).\n{WslEngine.FormatarResumoErro(res)}");
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

    private async Task ExecutarStepDriverOdbcAsync(
        ConfiguracaoInstalacao config,
        AuditorLog log,
        CancellationToken ct)
    {
        string pastaSuperset = EscaparArgBashSimples(config.WslPastaSuperset);
        string containerName = EscaparArgBashSimples(config.NomeConteinerSuperset);

        string scriptOdbc = $$"""
            set -e

            {{WslEngine.ScriptIsolamentoDockerBash}}
            {{WslEngine.HelperComposeBash}}

            CONTAINER='{{containerName}}'

            echo "[INF] Instalando Microsoft ODBC Driver 18 (msodbcsql18) no contêiner $CONTAINER..."
            docker exec -i -u 0 "$CONTAINER" bash -e -o pipefail <<'EOF_ODBC'
                export DEBIAN_FRONTEND=noninteractive
                export PATH="/app/.venv/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
                export UV_CACHE_DIR="/tmp/uv-cache"
                export PIP_NO_CACHE_DIR=1
                umask 022

                rm -f /etc/apt/sources.list.d/mssql-release.list \
                      /etc/apt/sources.list.d/mssql-release.sources \
                      /etc/apt/sources.list.d/microsoft-prod.list || true

                apt-get -o Acquire::Retries=3 update -qq
                apt-get -o Acquire::Retries=3 install -y -qq \
                    curl gnupg2 apt-transport-https ca-certificates \
                    unixodbc unixodbc-dev freetds-dev gcc g++

                . /etc/os-release
                DIST_ID=$(echo "${ID:-debian}" | tr "[:upper:]" "[:lower:]")
                VER_ID="${VERSION_ID:-12}"
                CODENAME="${VERSION_CODENAME:-bookworm}"
                ARCH=$(dpkg --print-architecture)

                install -m 0755 -d /usr/share/keyrings
                curl -fsSL https://packages.microsoft.com/keys/microsoft.asc | gpg --batch --dearmor --yes -o /usr/share/keyrings/microsoft-prod.gpg
                chmod a+r /usr/share/keyrings/microsoft-prod.gpg

                REPO_URL="https://packages.microsoft.com/config/${DIST_ID}/${VER_ID}/prod.list"
                if ! curl -fsSL "$REPO_URL" -o /etc/apt/sources.list.d/mssql-release.list; then
                    echo "[AVISO] Repositório '${DIST_ID}/${VER_ID}' indisponível; usando Debian 12 (bookworm)..."
                    curl -fsSL "https://packages.microsoft.com/config/debian/12/prod.list" -o /etc/apt/sources.list.d/mssql-release.list || true
                fi

                if [ -s /etc/apt/sources.list.d/mssql-release.list ]; then
                    if grep -q "signed-by=" /etc/apt/sources.list.d/mssql-release.list; then
                        sed -i 's|signed-by=[^] \t]*|signed-by=/usr/share/keyrings/microsoft-prod.gpg|g' /etc/apt/sources.list.d/mssql-release.list
                    elif grep -q '^deb \[' /etc/apt/sources.list.d/mssql-release.list; then
                        sed -i 's|^deb \[|deb [signed-by=/usr/share/keyrings/microsoft-prod.gpg |' /etc/apt/sources.list.d/mssql-release.list
                    else
                        sed -i 's|^deb |deb [signed-by=/usr/share/keyrings/microsoft-prod.gpg] |' /etc/apt/sources.list.d/mssql-release.list
                    fi
                fi

                if [ ! -s /etc/apt/sources.list.d/mssql-release.list ] || ! grep -q "packages.microsoft.com" /etc/apt/sources.list.d/mssql-release.list; then
                    if [ "$DIST_ID" = "debian" ] && [ -n "$CODENAME" ]; then
                        echo "deb [arch=${ARCH} signed-by=/usr/share/keyrings/microsoft-prod.gpg] https://packages.microsoft.com/debian/${VER_ID}/prod ${CODENAME} main" > /etc/apt/sources.list.d/mssql-release.list
                    else
                        echo "deb [arch=${ARCH} signed-by=/usr/share/keyrings/microsoft-prod.gpg] https://packages.microsoft.com/debian/12/prod bookworm main" > /etc/apt/sources.list.d/mssql-release.list
                    fi
                fi

                if ! apt-get -o Acquire::Retries=3 update -qq; then
                    echo "[AVISO] Entrada prod.list rejeitada pelo apt; gravando entrada canônica Debian/Ubuntu..."
                    if [ "$DIST_ID" = "debian" ] && [ -n "$CODENAME" ]; then
                        echo "deb [arch=${ARCH} signed-by=/usr/share/keyrings/microsoft-prod.gpg] https://packages.microsoft.com/debian/${VER_ID}/prod ${CODENAME} main" > /etc/apt/sources.list.d/mssql-release.list
                    else
                        echo "deb [arch=${ARCH} signed-by=/usr/share/keyrings/microsoft-prod.gpg] https://packages.microsoft.com/debian/12/prod bookworm main" > /etc/apt/sources.list.d/mssql-release.list
                    fi
                    apt-get -o Acquire::Retries=3 update -qq
                fi

                ACCEPT_EULA=Y apt-get -o Acquire::Retries=3 install -y -qq msodbcsql18

                echo "[INF] Instalando conectores Python SQL Server (pyodbc + pymssql + pillow)..."
                if [ -x /app/.venv/bin/python ] && command -v uv >/dev/null 2>&1; then
                    uv pip install --python /app/.venv/bin/python pyodbc pymssql pillow
                    /app/.venv/bin/python -c "import pyodbc, pymssql; print('[OK] Drivers ODBC carregados:', pyodbc.drivers())"
                elif [ -x /app/.venv/bin/pip ]; then
                    /app/.venv/bin/pip install --no-cache-dir pyodbc pymssql pillow
                    /app/.venv/bin/python -c "import pyodbc, pymssql; print('[OK] Drivers ODBC carregados:', pyodbc.drivers())"
                elif command -v pip3 >/dev/null 2>&1; then
                    pip3 install --no-cache-dir pyodbc pymssql pillow
                    python3 -c "import pyodbc, pymssql; print('[OK] Drivers ODBC carregados:', pyodbc.drivers())"
                else
                    python3 -m pip install --no-cache-dir pyodbc pymssql pillow
                    python3 -c "import pyodbc, pymssql; print('[OK] Drivers ODBC carregados:', pyodbc.drivers())"
                fi

                rm -rf /tmp/uv-cache /var/lib/apt/lists/* || true
            EOF_ODBC

            echo "[INF] Reiniciando contêiner do Superset para efetivar drivers..."
            cd '{{pastaSuperset}}'
            compose_cmd restart
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
                $"Falha ao instalar o driver msodbcsql18 / conectores SQL Server no contêiner (código {res.ExitCode}).\n{WslEngine.FormatarResumoErro(res)}");
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

    private async Task<bool> ExecutarStepDeployDashboardAsync(
        ConfiguracaoInstalacao config,
        AuditorLog log,
        IProgress<ProgressoEtapa>? progresso,
        CancellationToken ct)
    {
        EtapaDefinicao etapa = Etapas[3];
        log.Secao($"Etapa {etapa.Numero}/{Etapas.Count} — {etapa.Titulo}");
        log.Info(etapa.DescricaoUx);
        ReportarEtapa(progresso, 4, StatusEtapa.EmAndamento);

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
            string containerName = EscaparArgBashSimples(config.NomeConteinerSuperset);

            // Descobre IP do host Windows alcançável pelo WSL2/Docker quando SQL estiver local
            string scriptDeploy = $$"""
                set -e

                {{WslEngine.ScriptIsolamentoDockerBash}}

                EXPLICIT_HOST="{{EscaparArgBashSimples(sqlHostExplicit)}}"
                SQL_PORT="{{sqlPort}}"

                CANDIDATES=()
                [ -n "$EXPLICIT_HOST" ] && CANDIDATES+=("$EXPLICIT_HOST")
                ROUTE_IP=$(ip route show default 2>/dev/null | awk '/default/ {print $3; exit}')
                [ -n "$ROUTE_IP" ] && CANDIDATES+=("$ROUTE_IP")
                NS_IP=$(awk '/^nameserver/ {print $2; exit}' /etc/resolv.conf 2>/dev/null || true)
                [ -n "$NS_IP" ] && CANDIDATES+=("$NS_IP")
                CANDIDATES+=("127.0.0.1" "host.docker.internal" "172.29.112.1" "172.20.48.1")

                TARGET_HOST=""
                for h in "${CANDIDATES[@]}"; do
                    [ -z "$h" ] && continue
                    if timeout 2 bash -c "cat < /dev/null > /dev/tcp/$h/$SQL_PORT" 2>/dev/null; then
                        TARGET_HOST="$h"
                        echo "[OK] Conexão TCP na porta ${SQL_PORT} com sucesso no endereço: $TARGET_HOST"
                        break
                    fi
                done

                if [ -z "$TARGET_HOST" ]; then
                    DEFAULT_TEST="${ROUTE_IP:-${NS_IP:-172.20.48.1}}"
                    echo "[AVISO] Porta TCP ${SQL_PORT} do SQL Server não respondeu nos endereços testados (${CANDIDATES[*]})."
                    echo "[AVISO] Endereço provável do Windows: ${DEFAULT_TEST}. Verifique se o serviço do SQL Server foi reiniciado após habilitar TCP/IP e se o Firewall permite conexões."
                    exit 42
                fi

                echo "[INF] Endereço SQL Server resolvido para o WSL2/Docker: ${TARGET_HOST}:${SQL_PORT}"

                DB_URI="mssql+pyodbc://{{sqlUser}}:{{sqlPass}}@${TARGET_HOST}:${SQL_PORT}/{{sqlDb}}?driver=ODBC+Driver+18+for+SQL+Server&TrustServerCertificate=yes"

                if docker exec '{{containerName}}' test -x /app/.venv/bin/python 2>/dev/null; then
                    docker cp '{{EscaparArgBashSimples(scriptPathWsl)}}' '{{containerName}}:/tmp/setup_superset_auto.py'
                    docker exec '{{containerName}}' /app/.venv/bin/python /tmp/setup_superset_auto.py \
                        --url "http://127.0.0.1:8088" \
                        --username '{{userSuperset}}' \
                        --password '{{passSuperset}}' \
                        --db-name "MovideskDM" \
                        --db-uri "$DB_URI"
                else
                    python3 '{{EscaparArgBashSimples(scriptPathWsl)}}' \
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
                ReportarEtapa(progresso, 4, StatusEtapa.Aviso);
                return true;
            }

            if (!res.Sucesso)
            {
                throw new InvalidOperationException(
                    $"Erro ao importar o Dashboard - Movidesk BI no Superset (código {res.ExitCode}).\n{WslEngine.FormatarResumoErro(res)}");
            }

            log.Sucesso("Dashboard - Movidesk BI (9 Datasets, 15 Gráficos e 3 Filtros Nativos) publicado com sucesso!");
            ReportarEtapa(progresso, 4, StatusEtapa.Concluida);
            return false;
        }
        catch (OperationCanceledException)
        {
            ReportarEtapa(progresso, 4, StatusEtapa.Aviso);
            throw;
        }
        catch (Exception ex)
        {
            ReportarEtapa(progresso, 4, StatusEtapa.Erro);
            throw new InvalidOperationException($"Falha na Etapa 4 (Deploy Final do Dashboard): {ex.Message}", ex);
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
