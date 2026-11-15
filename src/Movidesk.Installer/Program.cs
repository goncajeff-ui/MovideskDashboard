using Movidesk.Installer.UI;

namespace Movidesk.Installer;

internal static class Program
{
    [STAThread]
    private static void Main()
    {
        Application.SetUnhandledExceptionMode(UnhandledExceptionMode.CatchException);
        Application.ThreadException += (_, args) =>
        {
            MessageBox.Show(
                $"Ocorreu um erro inesperado na interface do instalador:\n\n{args.Exception.Message}",
                "Erro — Instalador Dashboard Movidesk BI",
                MessageBoxButtons.OK,
                MessageBoxIcon.Error);
        };

        AppDomain.CurrentDomain.UnhandledException += (_, args) =>
        {
            if (args.ExceptionObject is Exception ex)
            {
                MessageBox.Show(
                    $"Erro crítico em segundo plano:\n\n{ex.Message}",
                    "Erro Crítico — Instalador Dashboard Movidesk BI",
                    MessageBoxButtons.OK,
                    MessageBoxIcon.Error);
            }
        };

        ApplicationConfiguration.Initialize();
        Application.Run(new FrmInstalador());
    }
}
