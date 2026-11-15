using System.Text;

namespace Movidesk.Installer.Core;

public enum NivelLog
{
    Info,
    Aguardando,
    Sucesso,
    Aviso,
    Erro,
    Comando
}

/// <summary>
/// Responsável pela auditoria persistente em arquivo de texto e emissão thread-safe
/// de eventos formatados (✔ / ❌ / ⏳) para o console visual da interface.
/// </summary>
public sealed class AuditorLog : IDisposable
{
    private readonly object _syncLock = new();
    private StreamWriter? _writer;
    private bool _disposed;

    public string CaminhoArquivoLog { get; }

    public event Action<NivelLog, string>? OnLogEmitido;

    public AuditorLog(string? pastaBaseLogs = null)
    {
        string dirLogs = !string.IsNullOrWhiteSpace(pastaBaseLogs)
            ? pastaBaseLogs
            : Path.Combine(
                Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
                "Advice",
                "MovideskBI",
                "Logs");

        Directory.CreateDirectory(dirLogs);
        string nomeArquivo = $"Instalador_MovideskBI_{DateTime.Now:yyyyMMdd_HHmmss}.log";
        CaminhoArquivoLog = Path.Combine(dirLogs, nomeArquivo);

        _writer = new StreamWriter(CaminhoArquivoLog, append: true, new UTF8Encoding(encoderShouldEmitUTF8Identifier: false))
        {
            AutoFlush = true
        };

        EscreverCabecalhoInicial();
    }

    private void EscreverCabecalhoInicial()
    {
        lock (_syncLock)
        {
            _writer?.WriteLine("================================================================================");
            _writer?.WriteLine(" ADVICE INSTALLER 2.0 — INSTALADOR DASHBOARD MOVIDESK BI");
            _writer?.WriteLine($" Início em: {DateTime.Now:dd/MM/yyyy HH:mm:ss} | Máquina: {Environment.MachineName} | Usuário: {Environment.UserName}");
            _writer?.WriteLine($" Sistema Operacional: {Environment.OSVersion}");
            _writer?.WriteLine("================================================================================");
        }
    }

    public void Info(string mensagem) => Registrar(NivelLog.Info, mensagem);
    public void Aguardando(string mensagem) => Registrar(NivelLog.Aguardando, mensagem);
    public void Sucesso(string mensagem) => Registrar(NivelLog.Sucesso, mensagem);
    public void Aviso(string mensagem) => Registrar(NivelLog.Aviso, mensagem);
    public void Erro(string mensagem) => Registrar(NivelLog.Erro, mensagem);
    public void Comando(string mensagem) => Registrar(NivelLog.Comando, mensagem);

    public void Secao(string titulo)
    {
        string barra = new string('─', 64);
        Registrar(NivelLog.Info, string.Empty);
        Registrar(NivelLog.Aguardando, $"{titulo}");
        Registrar(NivelLog.Comando, barra);
    }

    public void Registrar(NivelLog nivel, string mensagem)
    {
        if (_disposed)
        {
            return;
        }

        string simbolo = nivel switch
        {
            NivelLog.Sucesso => "✔",
            NivelLog.Erro => "❌",
            NivelLog.Aguardando => "⏳",
            NivelLog.Aviso => "⚠",
            NivelLog.Comando => "›",
            _ => "•"
        };

        string linhaFormatada = string.IsNullOrEmpty(mensagem)
            ? string.Empty
            : $"[{DateTime.Now:HH:mm:ss}] {simbolo} {mensagem}";

        lock (_syncLock)
        {
            if (_writer is not null)
            {
                try
                {
                    _writer.WriteLine(linhaFormatada);
                }
                catch
                {
                    // Falha pontual em disco não deve interromper o fluxo de instalação
                }
            }
        }

        OnLogEmitido?.Invoke(nivel, linhaFormatada);
    }

    public void CopiarLogParaPastaInstalacao(string diretorioInstalacao)
    {
        try
        {
            if (string.IsNullOrWhiteSpace(diretorioInstalacao) || !Directory.Exists(diretorioInstalacao))
            {
                return;
            }

            string destinoLogs = Path.Combine(diretorioInstalacao, "Logs");
            Directory.CreateDirectory(destinoLogs);
            string destinoArquivo = Path.Combine(destinoLogs, Path.GetFileName(CaminhoArquivoLog));

            lock (_syncLock)
            {
                _writer?.Flush();
            }

            File.Copy(CaminhoArquivoLog, destinoArquivo, overwrite: true);
        }
        catch
        {
            // Cópia auxiliar opcional
        }
    }

    public void Dispose()
    {
        if (_disposed)
        {
            return;
        }

        lock (_syncLock)
        {
            _disposed = true;
            try
            {
                _writer?.Flush();
                _writer?.Dispose();
            }
            catch
            {
                // Ignora erro ao encerrar writer
            }
            _writer = null;
        }
    }
}
