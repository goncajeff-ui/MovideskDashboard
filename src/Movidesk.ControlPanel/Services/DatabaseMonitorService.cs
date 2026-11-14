using Dapper;
using Microsoft.Data.SqlClient;
using Microsoft.Extensions.Configuration;

namespace Movidesk.ControlPanel.Services;

public sealed record VolumetriaSnapshot(
    bool Conectado,
    int TotalTicketsCore,
    int TotalTicketsRaw,
    int PendentesProcessamento,
    int? MenorTicketId,
    int? UltimoTicketId,
    DateTime? FronteiraHistoricaUtc,
    DateTime? UltimaMarcaDaguaUtc,
    DateTime ConsultadoEm,
    string? MensagemErro = null
);

/// <summary>
/// Monitora a volumetria em tempo real no SQL Server (MovideskDM) usando Dapper.
/// </summary>
public sealed class DatabaseMonitorService
{
    // =========================================================================
    // CONFIGURAÇÃO DA STRING DE CONEXÃO DO MSSQL (Banco MovideskDM)
    // Configure em appsettings.json ("ConnectionStrings:MovideskDM") ou edite o fallback abaixo:
    // =========================================================================
    private readonly string _connectionString;

    public DatabaseMonitorService(IConfiguration configuration)
    {
        // TODO: Ajuste sua ConnectionString do SQL Server em appsettings.json ("ConnectionStrings:MovideskDM")
        _connectionString = configuration.GetConnectionString("MovideskDM")
            ?? "Server=localhost;Database=MovideskDM;User Id=sa;Password=123456;TrustServerCertificate=True;MultipleActiveResultSets=True;";
    }

    /// <summary>
    /// Executa SELECT COUNT(*) na tabela core.Fato_Ticket (e contadores auxiliares) via Dapper.
    /// </summary>
    public async Task<VolumetriaSnapshot> GetVolumetriaAsync(CancellationToken cancellationToken = default)
    {
        const string sql = @"
            SELECT
                (SELECT COUNT(*) FROM core.Fato_Ticket) AS TotalTicketsCore,
                (SELECT COUNT(*) FROM raw.Ticket) AS TotalTicketsRaw,
                (SELECT COUNT(*) FROM raw.Ticket WHERE Processado = 0) AS PendentesProcessamento,
                (SELECT MIN(TicketId) FROM core.Fato_Ticket) AS MenorTicketId,
                (SELECT MAX(TicketId) FROM core.Fato_Ticket) AS UltimoTicketId,
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
                ) AS FronteiraHistoricaUtc,
                (SELECT TOP 1 UltimoValorUtc FROM ctl.MarcaDagua WHERE Entidade = 'TICKETS') AS UltimaMarcaDaguaUtc;";

        try
        {
            await using var conn = new SqlConnection(_connectionString);
            await conn.OpenAsync(cancellationToken);

            var row = await conn.QueryFirstAsync<VolumetriaQueryRow>(
                new CommandDefinition(sql, commandTimeout: 15, cancellationToken: cancellationToken));

            return new VolumetriaSnapshot(
                Conectado: true,
                TotalTicketsCore: row.TotalTicketsCore,
                TotalTicketsRaw: row.TotalTicketsRaw,
                PendentesProcessamento: row.PendentesProcessamento,
                MenorTicketId: row.MenorTicketId,
                UltimoTicketId: row.UltimoTicketId,
                FronteiraHistoricaUtc: row.FronteiraHistoricaUtc,
                UltimaMarcaDaguaUtc: row.UltimaMarcaDaguaUtc,
                ConsultadoEm: DateTime.Now
            );
        }
        catch (Exception ex)
        {
            return new VolumetriaSnapshot(
                Conectado: false,
                TotalTicketsCore: 0,
                TotalTicketsRaw: 0,
                PendentesProcessamento: 0,
                MenorTicketId: null,
                UltimoTicketId: null,
                FronteiraHistoricaUtc: null,
                UltimaMarcaDaguaUtc: null,
                ConsultadoEm: DateTime.Now,
                MensagemErro: ex.Message
            );
        }
    }

    private sealed class VolumetriaQueryRow
    {
        public int TotalTicketsCore { get; set; }
        public int TotalTicketsRaw { get; set; }
        public int PendentesProcessamento { get; set; }
        public int? MenorTicketId { get; set; }
        public int? UltimoTicketId { get; set; }
        public DateTime? FronteiraHistoricaUtc { get; set; }
        public DateTime? UltimaMarcaDaguaUtc { get; set; }
    }
}
