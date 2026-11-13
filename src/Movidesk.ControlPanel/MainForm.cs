using Microsoft.AspNetCore.Components.WebView.WindowsForms;
using Microsoft.Extensions.DependencyInjection;
using Movidesk.ControlPanel.Components;
using Movidesk.ControlPanel.Services;

namespace Movidesk.ControlPanel;

public sealed class MainForm : Form
{
    private readonly BlazorWebView _blazorWebView;
    private readonly IServiceProvider _serviceProvider;

    public MainForm(IServiceProvider serviceProvider)
    {
        _serviceProvider = serviceProvider;

        Text = "Painel de Controle — Movidesk BI (Advice)";
        Width = 1340;
        Height = 920;
        MinimumSize = new Size(960, 680);
        StartPosition = FormStartPosition.CenterScreen;
        BackColor = Color.FromArgb(11, 17, 32);
        Icon = SystemIcons.Application;

        var hostPagePath = ResolveHostPagePath();

        _blazorWebView = new BlazorWebView
        {
            Dock = DockStyle.Fill,
            HostPage = hostPagePath,
            Services = _serviceProvider
        };

        _blazorWebView.RootComponents.Add<Routes>("#app");
        Controls.Add(_blazorWebView);

        FormClosing += OnMainFormClosing;
    }

    private static string ResolveHostPagePath()
    {
        var exeDir = Path.GetDirectoryName(Environment.ProcessPath) ?? AppContext.BaseDirectory;
        var candidateExeDir = Path.Combine(exeDir, "wwwroot", "index.html");
        if (File.Exists(candidateExeDir))
        {
            return candidateExeDir;
        }

        var candidateBaseDir = Path.Combine(AppContext.BaseDirectory, "wwwroot", "index.html");
        if (File.Exists(candidateBaseDir))
        {
            return candidateBaseDir;
        }

        MessageBox.Show(
            $"Não foi possível localizar a pasta 'wwwroot\\index.html' ao lado do executável.\n\n" +
            $"Verifique se a pasta 'wwwroot' foi extraída junto com MovideskControlPanel.exe em:\n{exeDir}",
            "Arquivos de Interface Ausentes — Movidesk BI",
            MessageBoxButtons.OK,
            MessageBoxIcon.Error);

        return Path.Combine("wwwroot", "index.html");
    }

    private void OnMainFormClosing(object? sender, FormClosingEventArgs e)
    {
        var ingestion = _serviceProvider.GetService<MovideskIngestionService>();
        if (ingestion is { IsRunning: true })
        {
            var resposta = MessageBox.Show(
                "Existe uma carga de dados do Movidesk em andamento.\n\n" +
                "Se fechar o aplicativo agora, a carga será interrompida.\n\n" +
                "Deseja realmente encerrar o Painel de Controle?",
                "Carga em Andamento — Movidesk BI",
                MessageBoxButtons.YesNo,
                MessageBoxIcon.Warning,
                MessageBoxDefaultButton.Button2);

            if (resposta == DialogResult.No)
            {
                e.Cancel = true;
            }
        }
    }
}
