using System.Reflection;
using System.Runtime.InteropServices;
using System.Runtime.Versioning;

namespace Movidesk.Installer.Core;

/// <summary>
/// Cria atalhos corporativos (.lnk) na Área de Trabalho e no Menu Iniciar
/// utilizando Windows Script Host Object Model (IWshRuntimeLibrary / WScript.Shell via COM),
/// garantindo compatibilidade 100% single-file em .NET 8 sem DLLs externas de interop.
/// </summary>
[SupportedOSPlatform("windows")]
public sealed class AtalhoManager
{
    public string CriarAtalhoDesktop(
        string nomeAtalho,
        string caminhoExecutavel,
        string? caminhoIcone,
        string? descricao = null,
        string? workingDirectory = null,
        string? argumentos = null,
        AuditorLog? log = null)
    {
        if (string.IsNullOrWhiteSpace(caminhoExecutavel))
        {
            throw new ArgumentException("O caminho do executável de destino do atalho não pode ser vazio.", nameof(caminhoExecutavel));
        }

        string desktopDir = ResolverPastaDesktop();
        Directory.CreateDirectory(desktopDir);

        string nomeLimpo = nomeAtalho.EndsWith(".lnk", StringComparison.OrdinalIgnoreCase)
            ? nomeAtalho
            : $"{nomeAtalho}.lnk";

        string caminhoAtalho = Path.Combine(desktopDir, nomeLimpo);
        CriarAtalhoComWshShell(
            caminhoAtalho: caminhoAtalho,
            caminhoExecutavel: caminhoExecutavel,
            caminhoIcone: caminhoIcone,
            descricao: descricao ?? "Painel de Controle - Dashboard Movidesk BI (Advice Compliance Solutions)",
            workingDirectory: workingDirectory ?? Path.GetDirectoryName(caminhoExecutavel) ?? string.Empty,
            argumentos: argumentos);

        log?.Sucesso($"Atalho criado na Área de Trabalho via IWshRuntimeLibrary: {caminhoAtalho}");

        // Tenta também registrar no Menu Iniciar para facilitar busca pelo Windows Search
        try
        {
            string startMenuDir = Path.Combine(
                Environment.GetFolderPath(Environment.SpecialFolder.Programs),
                "Advice Compliance Solutions");
            Directory.CreateDirectory(startMenuDir);

            string atalhoMenu = Path.Combine(startMenuDir, nomeLimpo);
            CriarAtalhoComWshShell(
                caminhoAtalho: atalhoMenu,
                caminhoExecutavel: caminhoExecutavel,
                caminhoIcone: caminhoIcone,
                descricao: descricao ?? "Painel de Controle - Dashboard Movidesk BI",
                workingDirectory: workingDirectory ?? Path.GetDirectoryName(caminhoExecutavel) ?? string.Empty,
                argumentos: argumentos);
        }
        catch (Exception ex)
        {
            log?.Aviso($"Não foi possível criar atalho complementar no Menu Iniciar: {ex.Message}");
        }

        return caminhoAtalho;
    }

    private static void CriarAtalhoComWshShell(
        string caminhoAtalho,
        string caminhoExecutavel,
        string? caminhoIcone,
        string descricao,
        string workingDirectory,
        string? argumentos)
    {
        Type? wshShellType = Type.GetTypeFromProgID("WScript.Shell", throwOnError: false);
        if (wshShellType is null)
        {
            throw new PlatformNotSupportedException(
                "Componente COM 'WScript.Shell' (IWshRuntimeLibrary / wshom.ocx) indisponível neste Windows.");
        }

        object? wshShell = null;
        object? iwshShortcut = null;

        try
        {
            wshShell = Activator.CreateInstance(wshShellType)
                ?? throw new InvalidOperationException("Falha ao instanciar WshShell via COM.");

            iwshShortcut = wshShellType.InvokeMember(
                "CreateShortcut",
                BindingFlags.InvokeMethod,
                binder: null,
                target: wshShell,
                args: [caminhoAtalho]);

            if (iwshShortcut is null)
            {
                throw new InvalidOperationException("WshShell.CreateShortcut retornou nulo.");
            }

            Type shortcutType = iwshShortcut.GetType();
            shortcutType.InvokeMember("TargetPath", BindingFlags.SetProperty, null, iwshShortcut, [caminhoExecutavel]);

            if (!string.IsNullOrWhiteSpace(workingDirectory))
            {
                shortcutType.InvokeMember("WorkingDirectory", BindingFlags.SetProperty, null, iwshShortcut, [workingDirectory]);
            }

            if (!string.IsNullOrWhiteSpace(argumentos))
            {
                shortcutType.InvokeMember("Arguments", BindingFlags.SetProperty, null, iwshShortcut, [argumentos]);
            }

            shortcutType.InvokeMember("Description", BindingFlags.SetProperty, null, iwshShortcut, [descricao]);
            shortcutType.InvokeMember("WindowStyle", BindingFlags.SetProperty, null, iwshShortcut, [1]);

            if (!string.IsNullOrWhiteSpace(caminhoIcone) && File.Exists(caminhoIcone))
            {
                shortcutType.InvokeMember("IconLocation", BindingFlags.SetProperty, null, iwshShortcut, [$"{caminhoIcone},0"]);
            }
            else if (File.Exists(caminhoExecutavel))
            {
                shortcutType.InvokeMember("IconLocation", BindingFlags.SetProperty, null, iwshShortcut, [$"{caminhoExecutavel},0"]);
            }

            shortcutType.InvokeMember("Save", BindingFlags.InvokeMethod, null, iwshShortcut, args: null);
        }
        finally
        {
            if (iwshShortcut is not null && Marshal.IsComObject(iwshShortcut))
            {
                Marshal.FinalReleaseComObject(iwshShortcut);
            }

            if (wshShell is not null && Marshal.IsComObject(wshShell))
            {
                Marshal.FinalReleaseComObject(wshShell);
            }
        }
    }

    private static string ResolverPastaDesktop()
    {
        string userDesktop = Environment.GetFolderPath(Environment.SpecialFolder.DesktopDirectory);
        if (!string.IsNullOrWhiteSpace(userDesktop))
        {
            return userDesktop;
        }

        string commonDesktop = Environment.GetFolderPath(Environment.SpecialFolder.CommonDesktopDirectory);
        if (!string.IsNullOrWhiteSpace(commonDesktop))
        {
            return commonDesktop;
        }

        return Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.UserProfile), "Desktop");
    }
}
