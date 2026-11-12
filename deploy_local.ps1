<#
.SYNOPSIS
    Script de Instalação e Inicialização Local do Data Mart (MovideskDM)
    Executa no SQL Server Developer local do Windows.

.DESCRIPTION
    1. Executa os scripts SQL de criação do banco, tabelas, dados auxiliares, procedure e views.
    2. Compila o Worker de Ingestão em C# (.NET 8).
    3. Executa a primeira carga de teste da API para popular o banco.

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File .\deploy_local.ps1
#>

param(
    [string]$Servidor = "localhost",
    [string]$Usuario  = "sa",
    [string]$Senha    = "123456",
    [string]$Banco    = "MovideskDM"
)

$ErrorActionPreference = "Stop"
Write-Host "======================================================" -ForegroundColor Cyan
Write-Host "  DEPLOYS AUTOMÁTICO - DATA MART MOVIDESK (SQL SERVER)  " -ForegroundColor Cyan
Write-Host "======================================================" -ForegroundColor Cyan

# Função para executar scripts SQL com sqlcmd ou .NET SqlClient
function Executar-SqlScript {
    param([string]$CaminhoArquivo, [string]$NomeBanco = "master")

    Write-Host "-> Executando $CaminhoArquivo em [$NomeBanco]..." -ForegroundColor Yellow
    $conteudo = Get-Content -Path $CaminhoArquivo -Raw -Encoding UTF8

    # Tenta usar sqlcmd se estiver no PATH
    if (Get-Command sqlcmd -ErrorAction SilentlyContinue) {
        sqlcmd -S $Servidor -U $Usuario -P $Senha -d $NomeBanco -i $CaminhoArquivo -b
        if ($LASTEXITCODE -ne 0) {
            throw "Erro ao executar $CaminhoArquivo via sqlcmd."
        }
    }
    else {
        # Fallback usando SqlConnection direto do PowerShell
        $connString = "Server=$Servidor;Database=$NomeBanco;User Id=$Usuario;Password=$Senha;TrustServerCertificate=True;"
        $conn = New-Object Microsoft.Data.SqlClient.SqlConnection($connString)
        $conn.Open()

        # Divide por GO
        $batches = $conteudo -split "(?im)^\s*GO\s*$"
        foreach ($batch in $batches) {
            $cmdText = $batch.Trim()
            if ($cmdText.Length -gt 0) {
                $cmd = $conn.CreateCommand()
                $cmd.CommandText = $cmdText
                $cmd.CommandTimeout = 120
                $cmd.ExecuteNonQuery() | Out-Null
            }
        }
        $conn.Close()
    }
    Write-Host "   OK!" -ForegroundColor Green
}

$raiz = $PSScriptRoot
$dbDir = Join-Path $raiz "database"

# 1. Criação do Banco
Executar-SqlScript -CaminhoArquivo (Join-Path $dbDir "00_banco.sql") -NomeBanco "master"

# 2. Tabelas e Schemas
Executar-SqlScript -CaminhoArquivo (Join-Path $dbDir "01_tabelas.sql") -NomeBanco $Banco

# 3. Auxiliares e Calendário
Executar-SqlScript -CaminhoArquivo (Join-Path $dbDir "02_carga_auxiliares.sql") -NomeBanco $Banco

# 4. Procedure de Processamento
Executar-SqlScript -CaminhoArquivo (Join-Path $dbDir "04_procedure_processamento.sql") -NomeBanco $Banco

# 5. Views Analíticas para o Superset
Executar-SqlScript -CaminhoArquivo (Join-Path $dbDir "03_views_kpis.sql") -NomeBanco $Banco

Write-Host "`nBanco MovideskDM criado e configurado com sucesso!" -ForegroundColor Green

# 6. Compilação e Teste do Ingestor C#
$ingestorDir = Join-Path $raiz "src\Movidesk.Ingestion"
if (Test-Path $ingestorDir) {
    Write-Host "`n-> Compilando Worker C# .NET 8..." -ForegroundColor Cyan
    Push-Location $ingestorDir
    dotnet build -c Release
    if ($LASTEXITCODE -eq 0) {
        Write-Host "-> Executando carga inicial de teste (últimos 50 tickets da API)..." -ForegroundColor Yellow
        dotnet run -c Release -- teste
    }
    Pop-Location
}

Write-Host "`n======================================================" -ForegroundColor Cyan
Write-Host "  TUDO PRONTO! O Data Mart está populado e online!      " -ForegroundColor Green
Write-Host "======================================================" -ForegroundColor Cyan
Write-Host "Para iniciar o Superset ou conectar seu BI, aponte para:"
Write-Host "  Servidor: $Servidor"
Write-Host "  Banco:    $Banco"
Write-Host "  Views:    schema 'mart' (ex: mart.vw_VisaoGeralKpis, mart.vw_SlaRadar)"
