using System.IO.Compression;
using System.Reflection;
using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;

namespace Movidesk.Installer.Core;

/// <summary>
/// Gerencia a leitura dos recursos embutidos no executável único (Advice Installer 2.0),
/// extração segura do ControlPanel.zip, injeção da API Key do Movidesk no appsettings.json
/// e exportação dos artefatos Docker/Superset/SQL.
/// </summary>
public sealed class ExtratorArquivos
{
    private const string PrefixResource = "Movidesk.Installer.Resources.";
    private const string PrefixSqlResource = "Movidesk.Installer.Sql.";

    private static readonly Assembly AssemblyAtual = Assembly.GetExecutingAssembly();

    public static Image? CarregarImagemFundo()
    {
        try
        {
            using Stream? stream = ObterStreamRecursoOpcional($"{PrefixResource}image_77b41c.jpg");
            if (stream is null)
            {
                return null;
            }

            // Clona em memória para não depender do ciclo de vida do Stream subjacente
            using var ms = new MemoryStream();
            stream.CopyTo(ms);
            ms.Position = 0;
            using var tmp = Image.FromStream(ms);
            return new Bitmap(tmp);
        }
        catch
        {
            return null;
        }
    }

    public static Icon? CarregarIconeAdvice()
    {
        try
        {
            using Stream? stream = ObterStreamRecursoOpcional($"{PrefixResource}advice.ico");
            if (stream is null)
            {
                return null;
            }

            using var ms = new MemoryStream();
            stream.CopyTo(ms);
            ms.Position = 0;
            return new Icon(ms);
        }
        catch
        {
            return null;
        }
    }

    public string ExtrairIconeAdviceParaDisco(string diretorioDestino, AuditorLog log)
    {
        Directory.CreateDirectory(diretorioDestino);
        string caminhoIcone = Path.Combine(diretorioDestino, "advice.ico");

        using Stream? stream = ObterStreamRecursoOpcional($"{PrefixResource}advice.ico");
        if (stream is null)
        {
            log.Aviso("Recurso 'advice.ico' não encontrado nos embutidos; o atalho usará o ícone padrão do executável.");
            return string.Empty;
        }

        using var fs = new FileStream(caminhoIcone, FileMode.Create, FileAccess.Write, FileShare.Read);
        stream.CopyTo(fs);
        log.Sucesso($"Ícone oficial Advice salvo em: {caminhoIcone}");
        return caminhoIcone;
    }

    public string ExtrairPainelControle(string diretorioDestino, AuditorLog log)
    {
        Directory.CreateDirectory(diretorioDestino);

        using Stream? zipStream = AbrirStreamControlPanelZip(log);
        if (zipStream is null)
        {
            throw new FileNotFoundException(
                "Pacote 'ControlPanel.zip' não encontrado no instalador nem ao lado do executável.\n" +
                "Compile o instalador via 'Gerar_Instalador.bat' ou coloque 'ControlPanel.zip' / 'MovideskControlPanel-win-x64.zip' na mesma pasta.");
        }

        using var archive = new ZipArchive(zipStream, ZipArchiveMode.Read);
        string prefixoComum = DetectarPrefixoPastaRaiz(archive);
        string baseFullPath = Path.GetFullPath(diretorioDestino);
        if (!baseFullPath.EndsWith(Path.DirectorySeparatorChar))
        {
            baseFullPath += Path.DirectorySeparatorChar;
        }

        int arquivosExtraidos = 0;
        foreach (ZipArchiveEntry entry in archive.Entries)
        {
            string entryRel = entry.FullName.Replace('/', Path.DirectorySeparatorChar);
            if (!string.IsNullOrEmpty(prefixoComum) &&
                entryRel.StartsWith(prefixoComum, StringComparison.OrdinalIgnoreCase))
            {
                entryRel = entryRel[prefixoComum.Length..];
            }

            entryRel = entryRel.TrimStart(Path.DirectorySeparatorChar, Path.AltDirectorySeparatorChar);
            if (string.IsNullOrWhiteSpace(entryRel))
            {
                continue;
            }

            // Proteção contra Zip Slip
            string destPath = Path.GetFullPath(Path.Combine(baseFullPath, entryRel));
            if (!destPath.StartsWith(baseFullPath, StringComparison.OrdinalIgnoreCase))
            {
                throw new InvalidOperationException($"Entrada inválida no ZIP bloqueada por segurança: {entry.FullName}");
            }

            if (entry.FullName.EndsWith('/') || entry.FullName.EndsWith('\\'))
            {
                Directory.CreateDirectory(destPath);
                continue;
            }

            string? parentDir = Path.GetDirectoryName(destPath);
            if (!string.IsNullOrEmpty(parentDir))
            {
                Directory.CreateDirectory(parentDir);
            }

            entry.ExtractToFile(destPath, overwrite: true);
            arquivosExtraidos++;
        }

        string exePath = Path.Combine(diretorioDestino, "MovideskControlPanel.exe");
        if (!File.Exists(exePath))
        {
            string? encontrado = Directory.EnumerateFiles(diretorioDestino, "MovideskControlPanel.exe", SearchOption.AllDirectories)
                .FirstOrDefault();
            if (!string.IsNullOrEmpty(encontrado))
            {
                exePath = encontrado;
            }
        }

        log.Sucesso($"Extraídos {arquivosExtraidos} arquivo(s) do Painel de Controle para '{diretorioDestino}'.");
        return exePath;
    }

    public void InjetarConfiguracaoAppSettings(
        string diretorioDestino,
        ConfiguracaoInstalacao config,
        AuditorLog log)
    {
        string appSettingsPath = Path.Combine(diretorioDestino, "appsettings.json");
        JsonNode rootNode;

        if (File.Exists(appSettingsPath))
        {
            string rawJson = File.ReadAllText(appSettingsPath, Encoding.UTF8);
            rootNode = JsonNode.Parse(rawJson) ?? new JsonObject();
        }
        else
        {
            rootNode = new JsonObject();
        }

        var rootObj = rootNode.AsObject();

        // Seção ConnectionStrings
        var connStrings = rootObj["ConnectionStrings"] as JsonObject ?? new JsonObject();
        connStrings["MovideskDM"] =
            $"Server={config.SqlServerHost};Database={config.SqlServerBanco};User Id={config.SqlServerUsuario};Password={config.SqlServerSenha};TrustServerCertificate=True;MultipleActiveResultSets=True;";
        rootObj["ConnectionStrings"] = connStrings;

        // Seção Superset
        var supersetObj = rootObj["Superset"] as JsonObject ?? new JsonObject();
        supersetObj["WslDistro"] = config.WslDistro;
        supersetObj["Port"] = 8088;
        supersetObj["Url"] = "http://localhost:8088";
        supersetObj["SecretKey"] ??= "movidesk_superset_super_secret_key_2026";
        rootObj["Superset"] = supersetObj;

        // Seção Movidesk (Injeção da Chave da API)
        var movideskObj = rootObj["Movidesk"] as JsonObject ?? new JsonObject();
        movideskObj["BaseUrl"] ??= "https://api.movidesk.com/public/v1";
        movideskObj["Token"] = config.ApiKey.Trim();
        movideskObj["BatchSize"] ??= 50;
        movideskObj["DelayHorarioComercialMs"] ??= 6500;
        movideskObj["DelayHorarioLivreMs"] ??= 200;
        rootObj["Movidesk"] = movideskObj;

        var jsonOptions = new JsonSerializerOptions
        {
            WriteIndented = true
        };

        string jsonFinal = rootObj.ToJsonString(jsonOptions);
        File.WriteAllText(appSettingsPath, jsonFinal, new UTF8Encoding(encoderShouldEmitUTF8Identifier: false));

        string chaveMascarada = config.ApiKey.Length > 8
            ? $"{config.ApiKey[..4]}...{config.ApiKey[^4..]}"
            : "****";
        log.Sucesso($"Chave da API ({chaveMascarada}) e conexão SQL Server gravadas em '{appSettingsPath}'.");
    }

    public void ExtrairScriptsSqlAuxiliares(string diretorioDestino, AuditorLog log)
    {
        string sqlDir = Path.Combine(diretorioDestino, "database");
        Directory.CreateDirectory(sqlDir);

        string[] sqlResources = AssemblyAtual.GetManifestResourceNames()
            .Where(r => r.StartsWith(PrefixSqlResource, StringComparison.OrdinalIgnoreCase))
            .OrderBy(r => r, StringComparer.OrdinalIgnoreCase)
            .ToArray();

        int count = 0;
        foreach (string resName in sqlResources)
        {
            string fileName = resName[PrefixSqlResource.Length..];
            using Stream? s = AssemblyAtual.GetManifestResourceStream(resName);
            if (s is null) continue;

            using var fs = new FileStream(Path.Combine(sqlDir, fileName), FileMode.Create, FileAccess.Write, FileShare.Read);
            s.CopyTo(fs);
            count++;
        }

        if (count > 0)
        {
            log.Info($"Pacote de {count} script(s) SQL do MovideskDM salvo em '{sqlDir}'.");
        }
    }

    public string ObterRecursoTextoUtf8Lf(string nomeArquivoRecurso)
    {
        string fullName = nomeArquivoRecurso.StartsWith(PrefixResource, StringComparison.OrdinalIgnoreCase)
            ? nomeArquivoRecurso
            : $"{PrefixResource}{nomeArquivoRecurso}";

        using Stream? stream = ObterStreamRecursoOpcional(fullName)
            ?? throw new FileNotFoundException($"Recurso embutido '{fullName}' não encontrado no executável.");

        using var reader = new StreamReader(stream, Encoding.UTF8);
        string conteudo = reader.ReadToEnd();
        return conteudo.Replace("\r\n", "\n", StringComparison.Ordinal).Replace("\r", "\n", StringComparison.Ordinal);
    }

    private static Stream? AbrirStreamControlPanelZip(AuditorLog log)
    {
        Stream? embedded = ObterStreamRecursoOpcional($"{PrefixResource}ControlPanel.zip");
        if (embedded is not null)
        {
            log.Info("Localizado pacote embutido 'ControlPanel.zip' dentro do executável único.");
            return embedded;
        }

        string exeDir = Path.GetDirectoryName(Environment.ProcessPath) ?? AppContext.BaseDirectory;
        string[] candidatos =
        [
            Path.Combine(exeDir, "ControlPanel.zip"),
            Path.Combine(exeDir, "MovideskControlPanel-win-x64.zip"),
            Path.Combine(AppContext.BaseDirectory, "ControlPanel.zip")
        ];

        foreach (string path in candidatos)
        {
            if (File.Exists(path))
            {
                log.Aviso($"Usando pacote ZIP externo em '{path}' (modo desenvolvimento sem ZIP embutido).");
                return File.OpenRead(path);
            }
        }

        return null;
    }

    private static Stream? ObterStreamRecursoOpcional(string logicalName)
    {
        Stream? direct = AssemblyAtual.GetManifestResourceStream(logicalName);
        if (direct is not null)
        {
            return direct;
        }

        string? match = AssemblyAtual.GetManifestResourceNames()
            .FirstOrDefault(n => string.Equals(n, logicalName, StringComparison.OrdinalIgnoreCase));

        return match is not null ? AssemblyAtual.GetManifestResourceStream(match) : null;
    }

    private static string DetectarPrefixoPastaRaiz(ZipArchive archive)
    {
        var entriesComExe = archive.Entries
            .Where(e => e.Name.Equals("MovideskControlPanel.exe", StringComparison.OrdinalIgnoreCase))
            .ToList();

        if (entriesComExe.Count == 1)
        {
            string full = entriesComExe[0].FullName.Replace('/', Path.DirectorySeparatorChar);
            int idx = full.LastIndexOf("MovideskControlPanel.exe", StringComparison.OrdinalIgnoreCase);
            if (idx > 0)
            {
                return full[..idx];
            }
        }

        return string.Empty;
    }
}
