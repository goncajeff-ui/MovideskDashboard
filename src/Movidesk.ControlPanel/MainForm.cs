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

        _blazorWebView = new BlazorWebView
        {
            Dock = DockStyle.Fill,
            HostPage = Path.Combine("wwwroot", "index.html"),
            Services = _serviceProvider
        };

        _blazorWebView.RootComponents.Add<Routes>("#app");
        Controls.Add(_blazorWebView);

        FormClosing += OnMainFormClosing;
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
