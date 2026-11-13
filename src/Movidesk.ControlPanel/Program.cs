using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.DependencyInjection;
using Movidesk.ControlPanel.Services;

namespace Movidesk.ControlPanel;

internal static class Program
{
    [STAThread]
    private static void Main()
    {
        Application.SetHighDpiMode(HighDpiMode.SystemAware);
        Application.EnableVisualStyles();
        Application.SetCompatibleTextRenderingDefault(false);

        // Garante que o diretório de trabalho aponte para a pasta do executável
        var exeDir = Path.GetDirectoryName(Environment.ProcessPath) ?? AppContext.BaseDirectory;
        if (Directory.Exists(exeDir))
        {
            Environment.CurrentDirectory = exeDir;
        }

        var configBuilder = new ConfigurationBuilder()
            .SetBasePath(AppContext.BaseDirectory)
            .AddJsonFile("appsettings.json", optional: true, reloadOnChange: true);

        if (!string.Equals(Path.GetFullPath(exeDir), Path.GetFullPath(AppContext.BaseDirectory), StringComparison.OrdinalIgnoreCase))
        {
            configBuilder.AddJsonFile(Path.Combine(exeDir, "appsettings.json"), optional: true, reloadOnChange: true);
        }

        var configuration = configBuilder.Build();

        var services = new ServiceCollection();
        services.AddWindowsFormsBlazorWebView();
#if DEBUG
        services.AddBlazorWebViewDeveloperTools();
#endif
        services.AddSingleton<IConfiguration>(configuration);
        services.AddSingleton<SupersetService>();
        services.AddSingleton<DatabaseMonitorService>();
        services.AddSingleton<MovideskIngestionService>();

        using var serviceProvider = services.BuildServiceProvider();
        using var mainForm = new MainForm(serviceProvider);

        Application.Run(mainForm);
    }
}
