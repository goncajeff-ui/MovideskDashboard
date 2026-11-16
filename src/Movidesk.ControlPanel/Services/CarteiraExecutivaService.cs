using System.Globalization;
using System.Text;
using System.Text.RegularExpressions;
using Dapper;
using Microsoft.Data.SqlClient;
using Microsoft.Extensions.Configuration;

namespace Movidesk.ControlPanel.Services;

public sealed record TicketCarteiraItem(
    string Cliente,
    int Posicao,
    int TicketId,
    DateTime DataAbertura,
    string Servico,
    string Assunto,
    string Status,
    string Urgencia,
    string Equipe,
    string Analista
);

public enum CarteiraSortMode
{
    Alpha,
    PendingFirst,
    RecencyDesc,
    CadenceAsc
}

public sealed class CarteiraFilterState
{
    public string Cliente { get; set; } = "ALL";
    public string Servico { get; set; } = "ALL";
    public string Status { get; set; } = "ALL";
    public string Urgencia { get; set; } = "ALL";
    public string UrgenciaGrupo { get; set; } = "ALL";
    public string SearchText { get; set; } = string.Empty;
    public CarteiraSortMode SortMode { get; set; } = CarteiraSortMode.Alpha;
}

public sealed record PlatformSeverityRow(
    string Servico,
    int Total,
    double PctTotal,
    int Critica,
    int Alta,
    int Media,
    int Baixa
);

public sealed record StatusSliceRow(
    string Status,
    int Count,
    double PctTotal,
    string ColorHex
);

public sealed record ClientPortfolioRow(
    string Cliente,
    string ShortName,
    IReadOnlyList<TicketCarteiraItem> Tickets,
    int RecencyDays,
    TicketCarteiraItem LatestTicket,
    IReadOnlyList<double> Intervals,
    double? AvgCadenceDays,
    int PendingCount,
    bool HasContractRisk
);

public sealed record AgedWaitingItem(
    TicketCarteiraItem Ticket,
    int AgeDays
);

public sealed record AgedWaitingClientGroup(
    string Cliente,
    int MaxDays,
    IReadOnlyList<AgedWaitingItem> Tickets
);

public sealed record ChronicAlertItem(
    string Cliente,
    string Tag,
    string TagCssClass,
    string Title,
    string Details
);

public sealed record ContractRiskAlertItem(
    string Cliente,
    string Badge,
    string BadgeCssClass,
    string Title,
    string Details
);

public sealed record CarteiraAnalyticsResult(
    DateTime ReferenceDate,
    int TotalTickets,
    int TotalClientes,
    int Contas3Tickets,
    int Contas2Tickets,
    int Contas1Ticket,
    int TotalConcluidos,
    double TaxaResolucaoPct,
    int QtdResolvido,
    int QtdFechado,
    int QtdCancelado,
    int QtdAguardando,
    int QtdEmAtendimento,
    int TotalPendentes,
    double PctPendentes,
    int ClientesComPendentes,
    string EmAtendimentoClienteTexto,
    int TotalAltaCritica,
    double IndiceSeveridadePct,
    int QtdCritica,
    double PctCritica,
    int QtdAlta,
    double PctAlta,
    double? CadenciaMedianaDias,
    double? CadenciaMediaDias,
    double? RecenciaMedianaDias,
    double? RecenciaMediaDias,
    IReadOnlyList<PlatformSeverityRow> Platforms,
    IReadOnlyList<StatusSliceRow> StatusDistribution,
    IReadOnlyList<ClientPortfolioRow> RecencyRanking,
    IReadOnlyList<ClientPortfolioRow> CadenceRanking,
    IReadOnlyList<ClientPortfolioRow> SortedClients,
    IReadOnlyList<ChronicAlertItem> ChronicAlerts,
    IReadOnlyList<AgedWaitingClientGroup> AgedWaitingGroups,
    int TotalAgedWaitingTickets,
    IReadOnlyList<ContractRiskAlertItem> ContractRiskAlerts
);

public sealed record LiveSqlLoadResult(
    bool Success,
    IReadOnlyList<TicketCarteiraItem> Tickets,
    IReadOnlyList<string> Equipes,
    IReadOnlyList<string> Analistas,
    string StatusMessage
);

/// <summary>
/// Serviço analítico da Visão Executiva da Carteira (Top 3 por Cliente PJ).
/// Opera 100% offline sobre o snapshot oficial (59 tickets / 21 clientes) e também
/// oferece consulta direta em tempo real no SQL Server (MovideskDM) via Dapper.
/// </summary>
public sealed class CarteiraExecutivaService
{
    private readonly string _connectionString;

    public static readonly CultureInfo PtBr = CultureInfo.GetCultureInfo("pt-BR");
    public static readonly DateTime SnapshotReferenceDate = new(2026, 11, 15, 23, 59, 59);
    private static readonly Regex RuleSubjectPattern = new(@"regra|alerta|mb21|mf65|c07|mb08|se05|se07", RegexOptions.IgnoreCase | RegexOptions.Compiled);

    private static readonly Dictionary<string, int> PlatformPriority = new(StringComparer.OrdinalIgnoreCase)
    {
        ["EGUARDIAN"] = 1,
        ["KN1"] = 2,
        ["CCS"] = 3,
        ["METIS (GESTOR DE RISCOS)"] = 4,
        ["CORPORATIVO"] = 5,
        ["Listas e CheckPEP"] = 6
    };

    private static readonly Dictionary<string, string> StatusColors = new(StringComparer.OrdinalIgnoreCase)
    {
        ["Resolvido"] = "#10B981",
        ["Fechado"] = "#06B6D4",
        ["Aguardando"] = "#F59E0B",
        ["Em atendimento"] = "#3B82F6",
        ["Cancelado"] = "#94A3B8"
    };

    private static readonly IReadOnlyList<TicketCarteiraItem> SnapshotTickets = new List<TicketCarteiraItem>
    {
        new("Acg", 1, 53458, new DateTime(2026, 10, 21, 17, 53, 7), "EGUARDIAN", "Delei de informações", "Resolvido", "Alta", "Sustentação e-Guardian RJ", "Jefferson Gonçalves Cordeiro"),
        new("Acg", 2, 51300, new DateTime(2026, 9, 28, 10, 51, 11), "EGUARDIAN", "Alertas Regra MF20", "Resolvido", "Média", "Sustentação e-Guardian RJ", "Jefferson Gonçalves Cordeiro"),
        new("Acg", 3, 50720, new DateTime(2026, 9, 21, 9, 36, 53), "EGUARDIAN", "Serviços com Falhas", "Fechado", "Crítica/Impeditiva", "Sustentação e-Guardian RJ", "Jefferson Gonçalves Cordeiro"),
        new("AGORACRED", 1, 52623, new DateTime(2026, 10, 13, 15, 41, 0), "EGUARDIAN", "Problema no EGUARDIAN - Advice - Abertura de Chamada para Feito Conferido", "Aguardando", "Média", "Sustentação e-Guardian RJ", "Jefferson Gonçalves Cordeiro"),
        new("AGORACRED", 2, 38786, new DateTime(2026, 5, 8, 15, 44, 14), "EGUARDIAN", "Lentidão e timeout em algumas telas do e-guardian", "Fechado", "Alta", "Sustentação e-Guardian RJ", "Jefferson Gonçalves Cordeiro"),
        new("Apex", 1, 51630, new DateTime(2026, 9, 30, 12, 25, 14), "KN1", "Erro - Fases KN1", "Resolvido", "Alta", "Sustentação e-Guardian RJ", "Jefferson Gonçalves Cordeiro"),
        new("Apex", 2, 48682, new DateTime(2026, 8, 28, 10, 28, 40), "EGUARDIAN", "Eguardian com diversas falhas", "Fechado", "Crítica/Impeditiva", "Sustentação e-Guardian RJ", "Jefferson Gonçalves Cordeiro"),
        new("Apex", 3, 48361, new DateTime(2026, 8, 26, 9, 34, 15), "CORPORATIVO", "Dúvidas sobre o cadastro de usuários e permissão de acesso", "Fechado", "Alta", "Sustentação e-Guardian RJ", "Jefferson Gonçalves Cordeiro"),
        new("Ativa Investimentos", 1, 54838, new DateTime(2026, 11, 9, 17, 38, 0), "EGUARDIAN", "Dúvidas - Regra MB08", "Aguardando", "Média", "Sustentação e-Guardian RJ", "Jefferson Gonçalves Cordeiro"),
        new("Ativa Investimentos", 2, 54816, new DateTime(2026, 11, 9, 16, 0, 5), "EGUARDIAN", "Ajuste -  MB08", "Resolvido", "Média", "Sustentação e-Guardian RJ", "Jefferson Gonçalves Cordeiro"),
        new("Ativa Investimentos", 3, 54634, new DateTime(2026, 11, 6, 9, 48, 56), "EGUARDIAN", "Dúvidas - Regra MF71", "Resolvido", "Média", "Sustentação e-Guardian RJ", "Jefferson Gonçalves Cordeiro"),
        new("Banco Arbi", 1, 53524, new DateTime(2026, 10, 22, 12, 9, 54), "KN1", "Cadastros parados nas fases iniciais", "Resolvido", "Alta", "Sustentação e-Guardian RJ", "Jefferson Gonçalves Cordeiro"),
        new("Banco Arbi", 2, 53217, new DateTime(2026, 10, 20, 9, 58, 5), "KN1", "Cadastros parados no sistema", "Resolvido", "Alta", "Sustentação e-Guardian RJ", "Jefferson Gonçalves Cordeiro"),
        new("Banco Arbi", 3, 52451, new DateTime(2026, 10, 8, 17, 49, 2), "KN1", "8 Processos parados na fase inicial de dados cadastrais sem avançar", "Resolvido", "Alta", "Sustentação e-Guardian RJ", "Jefferson Gonçalves Cordeiro"),
        new("BGC Partners", 1, 52487, new DateTime(2026, 10, 9, 12, 26, 18), "KN1", "Suporte KN1_ ERRO NAS FASES", "Aguardando", "Baixa", "Sustentação e-Guardian RJ", "Jefferson Gonçalves Cordeiro"),
        new("BGC Partners", 2, 51035, new DateTime(2026, 9, 23, 15, 36, 21), "EGUARDIAN", "Inconsistências | BSM - Arquivos e Trilhas", "Resolvido", "Crítica/Impeditiva", "Sustentação e-Guardian RJ", "Jefferson Gonçalves Cordeiro"),
        new("BGC Partners", 3, 50130, new DateTime(2026, 9, 14, 15, 39, 4), "EGUARDIAN", "Suporte para Inativação de Cliente", "Resolvido", "Média", "Sustentação e-Guardian RJ", "Jefferson Gonçalves Cordeiro"),
        new("Bnymellon", 1, 54981, new DateTime(2026, 11, 11, 6, 5, 42), "METIS (GESTOR DE RISCOS)", "Erro no serviço 145", "Resolvido", "Alta", "Sustentação e-Guardian RJ", "Jefferson Gonçalves Cordeiro"),
        new("Bnymellon", 2, 54279, new DateTime(2026, 10, 30, 17, 12, 41), "METIS (GESTOR DE RISCOS)", "INC17605965 - Inconsistência na composição do risk rating de fundos", "Aguardando", "Média", "Sustentação e-Guardian RJ", "Jefferson Gonçalves Cordeiro"),
        new("Bnymellon", 3, 54182, new DateTime(2026, 10, 30, 8, 40, 37), "METIS (GESTOR DE RISCOS)", "Cliente reativado na base do eGuardian continuou inativado na base do METIS", "Aguardando", "Alta", "Sustentação e-Guardian RJ", "Jefferson Gonçalves Cordeiro"),
        new("CM Capital", 1, 54887, new DateTime(2026, 11, 10, 11, 26, 48), "EGUARDIAN", "Alertas MF65 - Gerados Fora do Prazo", "Aguardando", "Alta", "Sustentação e-Guardian RJ", "Jefferson Gonçalves Cordeiro"),
        new("CM Capital", 2, 54864, new DateTime(2026, 11, 10, 9, 42, 10), "EGUARDIAN", "Alertas MB21 Indevidos - IP \"FIX\"", "Em atendimento", "Alta", "Sustentação e-Guardian RJ", "Jefferson Gonçalves Cordeiro"),
        new("CM Capital", 3, 53622, new DateTime(2026, 10, 23, 11, 14, 45), "EGUARDIAN", "Serviços com Lentidão ou Parados", "Resolvido", "Baixa", "Sustentação e-Guardian RJ", "Jefferson Gonçalves Cordeiro"),
        new("CODEPE", 1, 48482, new DateTime(2026, 8, 27, 8, 56, 12), "CCS", "Inativação de cliente.", "Fechado", "Alta", "Sustentação e-Guardian RJ", "Jefferson Gonçalves Cordeiro"),
        new("CODEPE", 2, 46308, new DateTime(2026, 8, 5, 10, 51, 25), "CCS", "envios CCS", "Fechado", "Baixa", "Sustentação e-Guardian RJ", "Jefferson Gonçalves Cordeiro"),
        new("CODEPE", 3, 36366, new DateTime(2026, 4, 7, 10, 6, 31), "CCS", "Analise de envios CCS.", "Fechado", "Média", "Sustentação e-Guardian RJ", "Jefferson Gonçalves Cordeiro"),
        new("CREDIFIT", 1, 54580, new DateTime(2026, 11, 5, 15, 32, 5), "Listas e CheckPEP", "Lista restritiva - Impedir abertura de conta PF e PJ", "Resolvido", "Alta", "Sustentação e-Guardian RJ", "Jefferson Gonçalves Cordeiro"),
        new("CREDIFIT", 2, 54121, new DateTime(2026, 10, 29, 13, 17, 26), "CORPORATIVO", "Não consigo acessar a conta da Advice e o email não chega para recuperar a senha", "Resolvido", "Alta", "Sustentação e-Guardian RJ", "Jefferson Gonçalves Cordeiro"),
        new("CREDIFIT", 3, 53422, new DateTime(2026, 10, 21, 15, 4, 58), "KN1", "Credifit: manual do webservice de integração (wsIntegracaoRISC)", "Resolvido", "Média", "Sustentação e-Guardian RJ", "Jefferson Gonçalves Cordeiro"),
        new("FONTECRED - SOCIEDADE DE CREDITO DIRETO S/A", 1, 54313, new DateTime(2026, 11, 3, 9, 21, 28), "EGUARDIAN", "Suporte", "Cancelado", "Alta", "Sustentação e-Guardian RJ", "Jefferson Gonçalves Cordeiro"),
        new("FONTECRED - SOCIEDADE DE CREDITO DIRETO S/A", 2, 54303, new DateTime(2026, 11, 3, 8, 14, 51), "EGUARDIAN", "Suporte", "Resolvido", "Média", "Sustentação e-Guardian RJ", "Jefferson Gonçalves Cordeiro"),
        new("FONTECRED - SOCIEDADE DE CREDITO DIRETO S/A", 3, 48991, new DateTime(2026, 9, 1, 15, 14, 23), "EGUARDIAN", "Suporte", "Fechado", "Média", "Sustentação e-Guardian RJ", "Jefferson Gonçalves Cordeiro"),
        new("GerenciaNet", 1, 55085, new DateTime(2026, 11, 11, 16, 33, 14), "EGUARDIAN", "Acesso Eguardian", "Aguardando", "Alta", "Sustentação e-Guardian RJ", "Jefferson Gonçalves Cordeiro"),
        new("GerenciaNet", 2, 53415, new DateTime(2026, 10, 21, 14, 37, 40), "EGUARDIAN", "Lentidão EGUARDIAN - Novo chamado", "Resolvido", "Média", "Sustentação e-Guardian RJ", "Jefferson Gonçalves Cordeiro"),
        new("GerenciaNet", 3, 52069, new DateTime(2026, 10, 6, 10, 15, 15), "KN1", "Processo KYS - Idade do beneficiário", "Fechado", "Média", "Sustentação e-Guardian RJ", "Jefferson Gonçalves Cordeiro"),
        new("HDI Seguros", 1, 52903, new DateTime(2026, 10, 15, 17, 19, 8), "EGUARDIAN", "Regra SE07 - CPF do Executor sem 0 a esqueda", "Resolvido", "Média", "Sustentação e-Guardian RJ", "Jefferson Gonçalves Cordeiro"),
        new("HDI Seguros", 2, 52764, new DateTime(2026, 10, 14, 15, 27, 29), "EGUARDIAN", "Problema Integração - Coberturas", "Resolvido", "Média", "Sustentação e-Guardian RJ", "Jefferson Gonçalves Cordeiro"),
        new("HDI Seguros", 3, 50986, new DateTime(2026, 9, 23, 10, 22, 3), "EGUARDIAN", "Não arquivamento da SE05 de forma automática", "Resolvido", "Alta", "Sustentação e-Guardian RJ", "Jefferson Gonçalves Cordeiro"),
        new("HEDGE", 1, 28448, new DateTime(2025, 10, 15, 17, 33, 2), "CCS", "Erro ao fazer o login no sistema.", "Fechado", "Alta", "Sustentação e-Guardian RJ", "Jefferson Gonçalves Cordeiro"),
        new("LIBERTY", 1, 54096, new DateTime(2026, 10, 29, 10, 59, 24), "EGUARDIAN", "Fragilidade na Regra C07", "Cancelado", "Crítica/Impeditiva", "Sustentação e-Guardian RJ", "Jefferson Gonçalves Cordeiro"),
        new("LIBERTY", 2, 54034, new DateTime(2026, 10, 28, 15, 41, 35), "EGUARDIAN", "Fragilidade na Regra C07", "Aguardando", "Crítica/Impeditiva", "Sustentação e-Guardian RJ", "Jefferson Gonçalves Cordeiro"),
        new("LIBERTY", 3, 50898, new DateTime(2026, 9, 22, 14, 15, 0), "EGUARDIAN", "Fragilidades nas Regras de Monitoramento", "Resolvido", "Média", "Sustentação e-Guardian RJ", "Jefferson Gonçalves Cordeiro"),
        new("Lumina Corretora de Cambio", 1, 52609, new DateTime(2026, 10, 13, 13, 19, 25), "EGUARDIAN", "ALERTAS DO e-GUARDIAN 2025 + Regras e Listas", "Resolvido", "Crítica/Impeditiva", "Sustentação e-Guardian RJ", "Jefferson Gonçalves Cordeiro"),
        new("Lumina Corretora de Cambio", 2, 49452, new DateTime(2026, 9, 8, 10, 42, 26), "EGUARDIAN", "Desinstalação do sistema por Cancelamento", "Fechado", "Média", "Sustentação e-Guardian RJ", "Jefferson Gonçalves Cordeiro"),
        new("Lumina Corretora de Cambio", 3, 40973, new DateTime(2026, 6, 8, 10, 56, 18), "EGUARDIAN", "Dúvida sobre TI", "Fechado", "Alta", "Sustentação e-Guardian RJ", "Jefferson Gonçalves Cordeiro"),
        new("MAG", 1, 54695, new DateTime(2026, 11, 6, 16, 49, 12), "EGUARDIAN", "Avaliar monitoramento de Parceiros, Fornecedores, Colaboradores e Terceiros no e-Guardian", "Resolvido", "Baixa", "Sustentação e-Guardian RJ", "Jefferson Gonçalves Cordeiro"),
        new("MAG", 2, 52910, new DateTime(2026, 10, 15, 17, 45, 6), "Listas e CheckPEP", "Representante PEP (Sem ocorrência eGuardian)", "Aguardando", "Alta", "Sustentação e-Guardian RJ", "Jefferson Gonçalves Cordeiro"),
        new("MAG", 3, 50363, new DateTime(2026, 9, 16, 11, 45, 34), "EGUARDIAN", "Solicitação de Apoio para Configuração dos Grupos de Atuação", "Fechado", "Média", "Sustentação e-Guardian RJ", "Jefferson Gonçalves Cordeiro"),
        new("Nomad", 1, 55035, new DateTime(2026, 11, 11, 11, 29, 49), "CCS", "Erro no AJUD309", "Resolvido", "Alta", "Sustentação e-Guardian RJ", "Jefferson Gonçalves Cordeiro"),
        new("Nomad", 2, 55013, new DateTime(2026, 11, 11, 10, 7, 35), "CCS", "Expiração de senha STA", "Resolvido", "Alta", "Sustentação e-Guardian RJ", "Jefferson Gonçalves Cordeiro"),
        new("Nomad", 3, 54541, new DateTime(2026, 11, 5, 12, 41, 21), "CCS", "[Sisbajud] Status de retorno (AJUD308/310/331) e alinhamento de prazo (30/10)", "Resolvido", "Alta", "Sustentação e-Guardian RJ", "Jefferson Gonçalves Cordeiro"),
        new("RJ Investimentos", 1, 54942, new DateTime(2026, 11, 10, 15, 35, 24), "EGUARDIAN", "REUNIÃO APOIO SISTEMA", "Resolvido", "Alta", "Sustentação e-Guardian RJ", "Jefferson Gonçalves Cordeiro"),
        new("RJ Investimentos", 2, 53426, new DateTime(2026, 10, 21, 15, 35, 14), "EGUARDIAN", "Dúvidas - Sistema e-Guardian", "Fechado", "Alta", "Sustentação e-Guardian RJ", "Jefferson Gonçalves Cordeiro"),
        new("Sol Corretora de Cambio", 1, 38221, new DateTime(2026, 4, 30, 15, 31, 2), "EGUARDIAN", "Desbloqueio e recuperação de Senha", "Fechado", "Crítica/Impeditiva", "Sustentação e-Guardian RJ", "Jefferson Gonçalves Cordeiro"),
        new("Sol Corretora de Cambio", 2, 33442, new DateTime(2026, 2, 18, 14, 54, 33), "EGUARDIAN", "Configurar Siscoaf", "Fechado", "Alta", "Sustentação e-Guardian RJ", "Jefferson Gonçalves Cordeiro"),
        new("Sol Corretora de Cambio", 3, 33440, new DateTime(2026, 2, 18, 14, 53, 28), "EGUARDIAN", "Puxar relatórios monitoramento de alertas", "Fechado", "Alta", "Sustentação e-Guardian RJ", "Jefferson Gonçalves Cordeiro"),
        new("STELLANTIS FIAT", 1, 51481, new DateTime(2026, 9, 29, 15, 22, 34), "METIS (GESTOR DE RISCOS)", "Falha no start de serviços após instalação", "Resolvido", "Média", "Sustentação e-Guardian RJ", "Jefferson Gonçalves Cordeiro"),
        new("STELLANTIS FIAT", 2, 50982, new DateTime(2026, 9, 23, 10, 21, 0), "EGUARDIAN", "Atualização versão GUA_V008.9.9", "Resolvido", "Média", "Sustentação e-Guardian RJ", "Jefferson Gonçalves Cordeiro"),
        new("STELLANTIS FIAT", 3, 32059, new DateTime(2026, 1, 19, 13, 58, 58), "EGUARDIAN", "Painel de monitoramento filtrando incorretamente", "Fechado", "Média", "Sustentação e-Guardian RJ", "Jefferson Gonçalves Cordeiro")
    };

    public CarteiraExecutivaService(IConfiguration configuration)
    {
        _connectionString = configuration.GetConnectionString("MovideskDM")
            ?? "Server=localhost;Database=MovideskDM;User Id=sa;Password=123456;TrustServerCertificate=True;MultipleActiveResultSets=True;";
    }

    public IReadOnlyList<TicketCarteiraItem> GetSnapshotTickets() => SnapshotTickets;

    public async Task<LiveSqlLoadResult> LoadFromSqlServerAsync(
        string? equipe = "Sustentação e-Guardian RJ",
        string? analista = "Jefferson Gonçalves Cordeiro",
        CancellationToken cancellationToken = default)
    {
        const string sqlTickets = @"
            WITH BaseTickets AS (
                SELECT
                    ISNULL(emp.Nome, ISNULL(cli.Nome, N'Não Identificado')) AS Cliente,
                    t.TicketId,
                    t.DataCriacao AS DataAbertura,
                    ISNULL(NULLIF(LTRIM(RTRIM(t.ServicoN1)), N''), N'Não Informado') AS Servico,
                    ISNULL(NULLIF(LTRIM(RTRIM(t.Assunto)), N''), N'Sem Assunto') AS Assunto,
                    ISNULL(NULLIF(LTRIM(RTRIM(t.Status)), N''), N'Sem Status') AS Status,
                    ISNULL(NULLIF(LTRIM(RTRIM(t.Urgencia)), N''), N'Não Informada') AS Urgencia,
                    ISNULL(NULLIF(LTRIM(RTRIM(t.Equipe)), N''), N'Sem Equipe') AS Equipe,
                    ISNULL(ag.Nome, N'Não Atribuído') AS Analista,
                    ROW_NUMBER() OVER (
                        PARTITION BY ISNULL(emp.ClienteId, ISNULL(cli.ClienteId, ISNULL(t.EmpresaId, 'NAO_IDENTIFICADO')))
                        ORDER BY t.DataCriacao DESC, t.TicketId DESC
                    ) AS Posicao
                FROM core.Fato_Ticket t
                LEFT JOIN core.Dim_Agente ag ON t.AgenteId = ag.AgenteId
                LEFT JOIN core.Dim_Cliente cli ON t.EmpresaId = cli.ClienteId
                LEFT JOIN core.Dim_Cliente emp ON cli.EmpresaId = emp.ClienteId
                WHERE t.DataCriacao IS NOT NULL
                  AND (@Equipe IS NULL OR ISNULL(NULLIF(LTRIM(RTRIM(t.Equipe)), N''), N'Sem Equipe') = @Equipe)
                  AND (@Analista IS NULL OR ISNULL(ag.Nome, N'Não Atribuído') = @Analista)
            )
            SELECT
                Cliente,
                CAST(Posicao AS INT) AS Posicao,
                TicketId,
                DataAbertura,
                Servico,
                Assunto,
                Status,
                Urgencia,
                Equipe,
                Analista
            FROM BaseTickets
            WHERE Posicao <= 3
            ORDER BY Cliente ASC, Posicao ASC;";

        const string sqlFiltros = @"
            SELECT DISTINCT ISNULL(NULLIF(LTRIM(RTRIM(Equipe)), N''), N'Sem Equipe') AS Valor
            FROM core.Fato_Ticket
            WHERE DataCriacao IS NOT NULL
            ORDER BY Valor;

            SELECT DISTINCT ISNULL(ag.Nome, N'Não Atribuído') AS Valor
            FROM core.Fato_Ticket t
            LEFT JOIN core.Dim_Agente ag ON t.AgenteId = ag.AgenteId
            WHERE t.DataCriacao IS NOT NULL
            ORDER BY Valor;";

        try
        {
            await using var conn = new SqlConnection(_connectionString);
            await conn.OpenAsync(cancellationToken);

            var eqParam = string.IsNullOrWhiteSpace(equipe) || equipe == "ALL" ? null : equipe;
            var agParam = string.IsNullOrWhiteSpace(analista) || analista == "ALL" ? null : analista;

            var rows = (await conn.QueryAsync<TicketSqlRow>(
                new CommandDefinition(
                    sqlTickets,
                    new { Equipe = eqParam, Analista = agParam },
                    commandTimeout: 20,
                    cancellationToken: cancellationToken)))
                .Select(r => new TicketCarteiraItem(
                    r.Cliente ?? "Não Identificado",
                    r.Posicao,
                    r.TicketId,
                    r.DataAbertura,
                    r.Servico ?? "Não Informado",
                    r.Assunto ?? "Sem Assunto",
                    r.Status ?? "Sem Status",
                    r.Urgencia ?? "Não Informada",
                    r.Equipe ?? "Sem Equipe",
                    r.Analista ?? "Não Atribuído"))
                .ToList();

            using var multi = await conn.QueryMultipleAsync(
                new CommandDefinition(sqlFiltros, commandTimeout: 15, cancellationToken: cancellationToken));
            var equipes = (await multi.ReadAsync<string>()).ToList();
            var analistas = (await multi.ReadAsync<string>()).ToList();

            return new LiveSqlLoadResult(
                Success: true,
                Tickets: rows,
                Equipes: equipes,
                Analistas: analistas,
                StatusMessage: $"MovideskDM conectado: {rows.Count} tickets (Top 3 por cliente) carregados em tempo real.");
        }
        catch (Exception ex)
        {
            return new LiveSqlLoadResult(
                Success: false,
                Tickets: SnapshotTickets,
                Equipes: new[] { "Sustentação e-Guardian RJ" },
                Analistas: new[] { "Jefferson Gonçalves Cordeiro" },
                StatusMessage: $"MovideskDM indisponível ({ex.Message}). Mantido o Snapshot Executivo oficial (59 tickets).");
        }
    }

    public IReadOnlyList<TicketCarteiraItem> ApplyFilters(IReadOnlyList<TicketCarteiraItem> source, CarteiraFilterState filter)
    {
        var query = filter.SearchText.Trim();
        return source.Where(t =>
        {
            if (filter.Cliente != "ALL" && !string.Equals(t.Cliente, filter.Cliente, StringComparison.Ordinal))
                return false;

            if (filter.Servico != "ALL" && !string.Equals(t.Servico, filter.Servico, StringComparison.Ordinal))
                return false;

            if (filter.Status == "PENDING")
            {
                if (!IsPendingStatus(t.Status)) return false;
            }
            else if (filter.Status == "DONE")
            {
                if (!IsDoneStatus(t.Status)) return false;
            }
            else if (filter.Status != "ALL" && !string.Equals(t.Status, filter.Status, StringComparison.Ordinal))
            {
                return false;
            }

            if (filter.UrgenciaGrupo == "HIGH_CRIT")
            {
                if (!string.Equals(t.Urgencia, "Alta", StringComparison.Ordinal) &&
                    !string.Equals(t.Urgencia, "Crítica/Impeditiva", StringComparison.Ordinal))
                    return false;
            }
            else if (filter.Urgencia != "ALL" && !string.Equals(t.Urgencia, filter.Urgencia, StringComparison.Ordinal))
            {
                return false;
            }

            if (!string.IsNullOrEmpty(query))
            {
                bool match = t.Assunto.Contains(query, StringComparison.OrdinalIgnoreCase)
                    || t.TicketId.ToString(CultureInfo.InvariantCulture).Contains(query, StringComparison.OrdinalIgnoreCase)
                    || t.Cliente.Contains(query, StringComparison.OrdinalIgnoreCase)
                    || t.Servico.Contains(query, StringComparison.OrdinalIgnoreCase);
                if (!match) return false;
            }

            return true;
        }).ToList();
    }

    public CarteiraAnalyticsResult BuildAnalytics(
        IReadOnlyList<TicketCarteiraItem> sourceTickets,
        CarteiraFilterState filter,
        DateTime referenceDate)
    {
        var filtered = ApplyFilters(sourceTickets, filter);
        int total = filtered.Count;

        var clientGroups = filtered
            .GroupBy(t => t.Cliente, StringComparer.Ordinal)
            .ToList();

        var clientRows = new List<ClientPortfolioRow>(clientGroups.Count);
        var allIntervals = new List<double>();
        var recencyAll = new List<double>();

        foreach (var grp in clientGroups)
        {
            var ordered = grp.OrderBy(t => t.Posicao).ThenByDescending(t => t.DataAbertura).ToList();
            var latest = ordered[0];
            int recencyDays = ComputeDayDiff(latest.DataAbertura, referenceDate);
            recencyAll.Add(recencyDays);

            var intervals = new List<double>();
            for (int i = 0; i < ordered.Count - 1; i++)
            {
                double diff = Math.Max(0, (ordered[i].DataAbertura - ordered[i + 1].DataAbertura).TotalDays);
                intervals.Add(diff);
                allIntervals.Add(diff);
            }

            double? avgCadence = intervals.Count > 0 ? intervals.Average() : null;
            int pendingCnt = ordered.Count(t => IsPendingStatus(t.Status));
            bool contractRisk = ordered.Any(t =>
                t.Assunto.Contains("Cancelamento", StringComparison.OrdinalIgnoreCase) ||
                t.Assunto.Contains("Desinstala", StringComparison.OrdinalIgnoreCase));

            clientRows.Add(new ClientPortfolioRow(
                Cliente: grp.Key,
                ShortName: ShortClientName(grp.Key),
                Tickets: ordered,
                RecencyDays: recencyDays,
                LatestTicket: latest,
                Intervals: intervals,
                AvgCadenceDays: avgCadence,
                PendingCount: pendingCnt,
                HasContractRisk: contractRisk));
        }

        int c3 = clientRows.Count(c => c.Tickets.Count >= 3);
        int c2 = clientRows.Count(c => c.Tickets.Count == 2);
        int c1 = clientRows.Count(c => c.Tickets.Count == 1);

        int qtdResolvido = filtered.Count(t => string.Equals(t.Status, "Resolvido", StringComparison.Ordinal));
        int qtdFechado = filtered.Count(t => string.Equals(t.Status, "Fechado", StringComparison.Ordinal));
        int qtdCancelado = filtered.Count(t => string.Equals(t.Status, "Cancelado", StringComparison.Ordinal));
        int qtdAguardando = filtered.Count(t => string.Equals(t.Status, "Aguardando", StringComparison.Ordinal));
        int qtdEmAtendimento = filtered.Count(t => string.Equals(t.Status, "Em atendimento", StringComparison.Ordinal));

        int totalConcluidos = qtdResolvido + qtdFechado;
        double taxaResolucaoPct = total > 0 ? Math.Round(totalConcluidos * 100.0 / total, 2) : 0;

        var pendingTickets = filtered.Where(t => IsPendingStatus(t.Status)).ToList();
        int totalPendentes = pendingTickets.Count;
        double pctPendentes = total > 0 ? Math.Round(totalPendentes * 100.0 / total, 2) : 0;
        int clientesComPendentes = pendingTickets.Select(t => t.Cliente).Distinct(StringComparer.Ordinal).Count();

        var inProgressClients = pendingTickets
            .Where(t => string.Equals(t.Status, "Em atendimento", StringComparison.Ordinal))
            .Select(t => t.Cliente)
            .Distinct(StringComparer.Ordinal)
            .ToList();

        string emAtendTexto = inProgressClients.Count == 1 && qtdEmAtendimento == 1
            ? $"1 Em Atendimento na {inProgressClients[0]}"
            : $"{qtdEmAtendimento} Em Atendimento";

        int qtdCritica = filtered.Count(t => string.Equals(t.Urgencia, "Crítica/Impeditiva", StringComparison.Ordinal));
        int qtdAlta = filtered.Count(t => string.Equals(t.Urgencia, "Alta", StringComparison.Ordinal));
        int totalAltaCritica = qtdCritica + qtdAlta;

        double pctCritica = total > 0 ? Math.Round(qtdCritica * 100.0 / total, 2) : 0;
        double pctAlta = total > 0 ? Math.Round(qtdAlta * 100.0 / total, 2) : 0;
        double indiceSeveridadePct = total > 0
            ? (totalAltaCritica == total ? 100.0 : Math.Round(pctCritica + pctAlta, 2))
            : 0;

        double? cadenceMedian = ComputeMedian(allIntervals);
        double? cadenceMean = allIntervals.Count > 0 ? allIntervals.Average() : null;
        double? recencyMedian = ComputeMedian(recencyAll);
        double? recencyMean = recencyAll.Count > 0 ? recencyAll.Average() : null;

        var platforms = filtered
            .GroupBy(t => t.Servico, StringComparer.Ordinal)
            .Select(g =>
            {
                int tot = g.Count();
                return new PlatformSeverityRow(
                    Servico: g.Key,
                    Total: tot,
                    PctTotal: total > 0 ? Math.Round(tot * 100.0 / total, 2) : 0,
                    Critica: g.Count(t => t.Urgencia == "Crítica/Impeditiva"),
                    Alta: g.Count(t => t.Urgencia == "Alta"),
                    Media: g.Count(t => t.Urgencia == "Média"),
                    Baixa: g.Count(t => t.Urgencia == "Baixa"));
            })
            .OrderByDescending(p => p.Total)
            .ThenBy(p => PlatformPriority.TryGetValue(p.Servico, out var prio) ? prio : 99)
            .ThenBy(p => p.Servico, StringComparer.Ordinal)
            .ToList();

        var statusOrder = new[] { "Resolvido", "Fechado", "Aguardando", "Cancelado", "Em atendimento" };
        var extraStatusList = filtered
            .Select(t => t.Status)
            .Distinct(StringComparer.Ordinal)
            .Where(s => !statusOrder.Contains(s, StringComparer.Ordinal))
            .OrderBy(s => s, StringComparer.Ordinal);

        var statusSlices = statusOrder
            .Concat(extraStatusList)
            .Select(st =>
            {
                int cnt = filtered.Count(t => string.Equals(t.Status, st, StringComparison.Ordinal));
                return new StatusSliceRow(
                    Status: st,
                    Count: cnt,
                    PctTotal: total > 0 ? Math.Round(cnt * 100.0 / total, 2) : 0,
                    ColorHex: StatusColors.GetValueOrDefault(st, "#94A3B8"));
            })
            .ToList();

        var recencyRanking = clientRows
            .OrderByDescending(c => c.RecencyDays)
            .ThenBy(c => c.Cliente, PtBr.CompareInfo.GetStringComparer(CompareOptions.IgnoreCase))
            .ToList();

        var cadenceRanking = clientRows
            .Where(c => c.AvgCadenceDays.HasValue)
            .OrderBy(c => c.AvgCadenceDays!.Value)
            .ThenBy(c => c.Cliente, PtBr.CompareInfo.GetStringComparer(CompareOptions.IgnoreCase))
            .ToList();

        var sortedClients = (filter.SortMode switch
        {
            CarteiraSortMode.PendingFirst => clientRows
                .OrderByDescending(c => c.PendingCount)
                .ThenByDescending(c => c.RecencyDays)
                .ThenBy(c => c.Cliente, PtBr.CompareInfo.GetStringComparer(CompareOptions.IgnoreCase)),
            CarteiraSortMode.RecencyDesc => clientRows
                .OrderByDescending(c => c.RecencyDays)
                .ThenBy(c => c.Cliente, PtBr.CompareInfo.GetStringComparer(CompareOptions.IgnoreCase)),
            CarteiraSortMode.CadenceAsc => clientRows
                .OrderBy(c => c.AvgCadenceDays ?? double.MaxValue)
                .ThenBy(c => c.Cliente, PtBr.CompareInfo.GetStringComparer(CompareOptions.IgnoreCase)),
            _ => clientRows
                .OrderBy(c => c.Cliente, PtBr.CompareInfo.GetStringComparer(CompareOptions.IgnoreCase))
        }).ToList();

        // Alertas Automáticos 1: Reincidência Crônica por Produto / Regra
        var chronicAlerts = new List<ChronicAlertItem>();
        foreach (var c in clientRows)
        {
            if (c.Tickets.Count == 3)
            {
                var svcGrp = c.Tickets.GroupBy(t => t.Servico).FirstOrDefault(g => g.Count() == 3);
                if (svcGrp is not null && !string.Equals(svcGrp.Key, "EGUARDIAN", StringComparison.OrdinalIgnoreCase))
                {
                    string svc = svcGrp.Key;
                    string details = c.Cliente switch
                    {
                        "Banco Arbi" => "3/3 chamados em KN1 (Alta) por processos/cadastros parados nas fases iniciais.",
                        "Nomad" => "3/3 chamados em CCS (Alta) sobre Sisbajud (AJUD308/309/310) e expiração de senha STA.",
                        "Bnymellon" => $"3/3 chamados em METIS ({c.PendingCount} pendentes em Aguardando: #54279 e #54182).",
                        _ => $"3/3 chamados concentrados em {svc} ({c.PendingCount} pendente(s))."
                    };

                    chronicAlerts.Add(new ChronicAlertItem(
                        Cliente: c.Cliente,
                        Tag: svc,
                        TagCssClass: c.PendingCount > 0 ? "st-aguardando" : "urg-alta",
                        Title: c.Cliente,
                        Details: details));
                }
            }
        }

        var rulePattern = RuleSubjectPattern;
        bool hasCm = clientRows.Any(c => c.Cliente == "CM Capital" && c.Tickets.Count(t => t.Servico == "EGUARDIAN" && rulePattern.IsMatch(t.Assunto)) >= 2);
        bool hasLib = clientRows.Any(c => c.Cliente == "LIBERTY" && c.Tickets.Count(t => t.Servico == "EGUARDIAN" && rulePattern.IsMatch(t.Assunto)) >= 2);
        if (hasCm || hasLib)
        {
            string target = hasCm ? "CM Capital" : "LIBERTY";
            string title = (hasCm && hasLib) ? "CM Capital e LIBERTY" : target;
            chronicAlerts.Add(new ChronicAlertItem(
                Cliente: target,
                Tag: "EGUARDIAN · Regras",
                TagCssClass: "urg-critica",
                Title: title,
                Details: "Reincidência em regras de monitoramento do e-Guardian (MB21/MF65 na CM Capital e C07 Crítica na LIBERTY)."));
        }

        // Alertas Automáticos 2: Radar de Pendências Envelhecidas (Aguardando > 15 dias)
        var agedTickets = filtered
            .Where(t => string.Equals(t.Status, "Aguardando", StringComparison.Ordinal))
            .Select(t => new AgedWaitingItem(t, ComputeDayDiff(t.DataAbertura, referenceDate)))
            .Where(x => x.AgeDays > 15)
            .OrderByDescending(x => x.AgeDays)
            .ThenBy(x => x.Ticket.TicketId)
            .ToList();

        var agedGroups = agedTickets
            .GroupBy(x => x.Ticket.Cliente, StringComparer.Ordinal)
            .Select(g => new AgedWaitingClientGroup(
                Cliente: g.Key,
                MaxDays: g.Max(x => x.AgeDays),
                Tickets: g.ToList()))
            .OrderByDescending(g => g.MaxDays)
            .ThenBy(g => g.Cliente, PtBr.CompareInfo.GetStringComparer(CompareOptions.IgnoreCase))
            .ToList();

        // Alertas Automáticos 3: Risco Contratual & Churn Silencioso
        var contractRisks = new List<ContractRiskAlertItem>();
        foreach (var c in clientRows)
        {
            foreach (var t in c.Tickets)
            {
                if (t.Assunto.Contains("Cancelamento", StringComparison.OrdinalIgnoreCase) ||
                    t.Assunto.Contains("Desinstala", StringComparison.OrdinalIgnoreCase))
                {
                    contractRisks.Add(new ContractRiskAlertItem(
                        Cliente: c.Cliente,
                        Badge: $"#{t.TicketId} · Cancelamento",
                        BadgeCssClass: "urg-critica",
                        Title: c.Cliente,
                        Details: $"Ticket #{t.TicketId} ({t.DataAbertura.ToString("dd/MM/yyyy", PtBr)}) registrado como \"{t.Assunto}\"."));
                }
                else if (t.Assunto.Contains("Inativação de cliente", StringComparison.OrdinalIgnoreCase))
                {
                    contractRisks.Add(new ContractRiskAlertItem(
                        Cliente: c.Cliente,
                        Badge: $"#{t.TicketId} · {c.RecencyDays}d silencioso",
                        BadgeCssClass: "sem-red",
                        Title: c.Cliente,
                        Details: $"Ticket #{t.TicketId} (\"{t.Assunto}\") — conta há {c.RecencyDays}d sem novos chamados."));
                }
            }
        }

        var silentClients = recencyRanking.Where(c => c.RecencyDays >= 80).ToList();
        if (silentClients.Count > 0)
        {
            string lista = string.Join(", ", silentClients.Select(c => $"{c.ShortName} ({c.RecencyDays}d)"));
            contractRisks.Add(new ContractRiskAlertItem(
                Cliente: silentClients[0].Cliente,
                Badge: $"{silentClients.Count} contas ≥80d",
                BadgeCssClass: "sem-red",
                Title: "Silenciosos Críticos (Risco Inatividade)",
                Details: lista + "."));
        }

        return new CarteiraAnalyticsResult(
            ReferenceDate: referenceDate,
            TotalTickets: total,
            TotalClientes: clientRows.Count,
            Contas3Tickets: c3,
            Contas2Tickets: c2,
            Contas1Ticket: c1,
            TotalConcluidos: totalConcluidos,
            TaxaResolucaoPct: taxaResolucaoPct,
            QtdResolvido: qtdResolvido,
            QtdFechado: qtdFechado,
            QtdCancelado: qtdCancelado,
            QtdAguardando: qtdAguardando,
            QtdEmAtendimento: qtdEmAtendimento,
            TotalPendentes: totalPendentes,
            PctPendentes: pctPendentes,
            ClientesComPendentes: clientesComPendentes,
            EmAtendimentoClienteTexto: emAtendTexto,
            TotalAltaCritica: totalAltaCritica,
            IndiceSeveridadePct: indiceSeveridadePct,
            QtdCritica: qtdCritica,
            PctCritica: pctCritica,
            QtdAlta: qtdAlta,
            PctAlta: pctAlta,
            CadenciaMedianaDias: cadenceMedian,
            CadenciaMediaDias: cadenceMean,
            RecenciaMedianaDias: recencyMedian,
            RecenciaMediaDias: recencyMean,
            Platforms: platforms,
            StatusDistribution: statusSlices,
            RecencyRanking: recencyRanking,
            CadenceRanking: cadenceRanking,
            SortedClients: sortedClients,
            ChronicAlerts: chronicAlerts,
            AgedWaitingGroups: agedGroups,
            TotalAgedWaitingTickets: agedTickets.Count,
            ContractRiskAlerts: contractRisks);
    }

    public string BuildCsv(IReadOnlyList<TicketCarteiraItem> tickets)
    {
        var sb = new StringBuilder();
        sb.Append('\uFEFF');
        sb.AppendLine("Cliente;Posicao;TicketId;DataAbertura;Servico;Assunto;Status;Urgencia;Equipe;Analista");

        static string Esc(string? value)
        {
            string s = value ?? string.Empty;
            return "\"" + s.Replace("\"", "\"\"") + "\"";
        }

        foreach (var t in tickets)
        {
            sb.Append(Esc(t.Cliente)).Append(';')
              .Append(t.Posicao.ToString(CultureInfo.InvariantCulture)).Append(';')
              .Append(t.TicketId.ToString(CultureInfo.InvariantCulture)).Append(';')
              .Append(Esc(t.DataAbertura.ToString("yyyy-MM-dd HH:mm:ss", CultureInfo.InvariantCulture))).Append(';')
              .Append(Esc(t.Servico)).Append(';')
              .Append(Esc(t.Assunto)).Append(';')
              .Append(Esc(t.Status)).Append(';')
              .Append(Esc(t.Urgencia)).Append(';')
              .Append(Esc(t.Equipe)).Append(';')
              .AppendLine(Esc(t.Analista));
        }

        return sb.ToString();
    }

    public static int ComputeDayDiff(DateTime openingDate, DateTime referenceDate)
    {
        var days = (referenceDate.Date - openingDate.Date).Days;
        return Math.Max(0, days);
    }

    public static bool IsPendingStatus(string status) =>
        string.Equals(status, "Aguardando", StringComparison.Ordinal) ||
        string.Equals(status, "Em atendimento", StringComparison.Ordinal);

    public static bool IsDoneStatus(string status) =>
        string.Equals(status, "Resolvido", StringComparison.Ordinal) ||
        string.Equals(status, "Fechado", StringComparison.Ordinal);

    public static string ShortClientName(string name) => name switch
    {
        "FONTECRED - SOCIEDADE DE CREDITO DIRETO S/A" => "FONTECRED SCD",
        "Lumina Corretora de Cambio" => "Lumina Corretora",
        "Sol Corretora de Cambio" => "Sol Corretora",
        _ => name
    };

    private static double? ComputeMedian(List<double> values)
    {
        if (values.Count == 0) return null;
        var sorted = values.OrderBy(v => v).ToList();
        int mid = sorted.Count / 2;
        return sorted.Count % 2 == 0
            ? (sorted[mid - 1] + sorted[mid]) / 2.0
            : sorted[mid];
    }

    private sealed class TicketSqlRow
    {
        public string? Cliente { get; set; }
        public int Posicao { get; set; }
        public int TicketId { get; set; }
        public DateTime DataAbertura { get; set; }
        public string? Servico { get; set; }
        public string? Assunto { get; set; }
        public string? Status { get; set; }
        public string? Urgencia { get; set; }
        public string? Equipe { get; set; }
        public string? Analista { get; set; }
    }
}
