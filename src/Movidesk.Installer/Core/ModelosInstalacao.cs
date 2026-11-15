namespace Movidesk.Installer.Core;

public enum StatusEtapa
{
    Pendente,
    EmAndamento,
    Concluida,
    Aviso,
    Erro
}

public sealed record EtapaDefinicao(
    int Numero,
    string Codigo,
    string Titulo,
    string DescricaoUx);

public sealed record ProgressoEtapa(
    int EtapaAtual,
    int TotalEtapas,
    string TituloEtapa,
    string DescricaoUx,
    StatusEtapa Status,
    int PercentualGeral);

public sealed record ResultadoComando(
    int ExitCode,
    string StdOut,
    string StdErr)
{
    public bool Sucesso => ExitCode == 0;
}

public sealed class ConfiguracaoInstalacao
{
    public string ApiKey { get; set; } = string.Empty;
    public string DiretorioInstalacao { get; set; } = @"C:\Advice\MovideskBI";
    public string WslDistro { get; set; } = "Ubuntu";
    public string WslPastaSuperset { get; set; } = "/opt/advice-movidesk-superset";
    public string NomeConteinerSuperset { get; set; } = "advice_movidesk_superset";
    public string SupersetUsuarioAdmin { get; set; } = "admin";
    public string SupersetSenhaAdmin { get; set; } = "admin";
    public string SupersetEmailAdmin { get; set; } = "admin@advice.com.br";
    public string SqlServerHost { get; set; } = "localhost";
    public string SqlServerUsuario { get; set; } = "sa";
    public string SqlServerSenha { get; set; } = "123456";
    public string SqlServerBanco { get; set; } = "MovideskDM";
    public bool CriarAtalhoDesktop { get; set; } = true;
    public bool ConfigurarFirewall { get; set; } = true;
}

public sealed class ResultadoInstalacao
{
    public bool Sucesso { get; init; }
    public bool Cancelada { get; init; }
    public bool ReinicioWindowsNecessario { get; init; }
    public bool DeployDashboardPendenteBanco { get; init; }
    public string DiretorioInstalacao { get; init; } = string.Empty;
    public string CaminhoExecutavelPainel { get; init; } = string.Empty;
    public string CaminhoAtalhoDesktop { get; init; } = string.Empty;
    public string UrlSuperset { get; init; } = "http://localhost:8088";
    public string UrlDashboard { get; init; } = "http://localhost:8088/superset/dashboard/dashboard-movidesk/";
    public string CaminhoArquivoLog { get; init; } = string.Empty;
    public string? MensagemResumo { get; init; }
}
