<#
.SYNOPSIS
    Baixa uma AMOSTRA de tickets e empresas da API do Movidesk para mapear
    os campos reais (inclusive campos customizados) da base da Advice.

.DESCRIPTION
    - O token é solicitado na hora (não fica salvo em arquivo nem no histórico).
    - Faz apenas 2 requisições (limite da API: 10 req/min das 07:01 às 18:59).
    - Para no primeiro erro (3 erros seguidos bloqueiam a API por 60s+).
    - Gera os arquivos em .\amostra\ :
        tickets_amostra.json   -> tickets completos (com ações, históricos, campos customizados)
        empresas_amostra.json  -> cadastro de empresas (personType = 2)
        campos_customizados.txt -> resumo dos IDs de campos customizados encontrados

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File .\amostra-api-movidesk.ps1
    powershell -ExecutionPolicy Bypass -File .\amostra-api-movidesk.ps1 -Quantidade 100
#>
param(
    [int]$Quantidade = 50
)

$ErrorActionPreference = 'Stop'
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

$baseUrl = 'https://api.movidesk.com/public/v1'
$saida   = Join-Path $PSScriptRoot 'amostra'
New-Item -ItemType Directory -Force -Path $saida | Out-Null

# --- Token (lido de forma segura) ---------------------------------------------
$secure = Read-Host 'Cole o token da API do Movidesk' -AsSecureString
$bstr   = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
$token  = [Runtime.InteropServices.Marshal]::PtrToStringAuto($bstr)
[Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr)

function Invoke-Movidesk {
    param([string]$Rota, [hashtable]$Parametros, [string]$Arquivo)

    $query = ($Parametros.GetEnumerator() | ForEach-Object {
        '{0}={1}' -f $_.Key, [uri]::EscapeDataString($_.Value)
    }) -join '&'
    $url = "$baseUrl/$Rota`?token=$([uri]::EscapeDataString($token))&$query"

    Write-Host "-> GET /$Rota ..." -ForegroundColor Cyan
    try {
        $resp = Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 180
    }
    catch {
        $msg = $_.Exception.Message
        if ($_.Exception.Response) {
            $reader = New-Object IO.StreamReader($_.Exception.Response.GetResponseStream())
            $msg = "$msg`n$($reader.ReadToEnd())"
        }
        Write-Host "ERRO em /$Rota :`n$msg" -ForegroundColor Red
        Write-Host 'Envie essa mensagem de erro para ajustarmos o script.' -ForegroundColor Yellow
        exit 1
    }

    $destino = Join-Path $saida $Arquivo
    [IO.File]::WriteAllText($destino, $resp.Content, [Text.Encoding]::UTF8)
    Write-Host "   OK -> $destino" -ForegroundColor Green
    return ($resp.Content | ConvertFrom-Json)
}

# --- 1) Tickets ----------------------------------------------------------------
$select = @(
    'id','protocol','type','subject','category','urgency','status','baseStatus','justification',
    'origin','createdDate','lastUpdate','lastActionDate','resolvedIn','closedIn','reopenedIn',
    'actionCount','ownerTeam','serviceFirstLevel','serviceSecondLevel','serviceThirdLevel','tags',
    'slaAgreement','slaAgreementRule','slaSolutionTime','slaResponseTime','slaSolutionDate',
    'slaSolutionDateIsPaused','slaResponseDate','slaRealResponseDate','resolvedInFirstCall'
) -join ','

$expand = 'owner,createdBy,clients($expand=organization),actions,statusHistories,ownerHistories,customFieldValues,parentTickets,childrenTickets'

$tickets = Invoke-Movidesk -Rota 'tickets' -Arquivo 'tickets_amostra.json' -Parametros @{
    '$select'  = $select
    '$expand'  = $expand
    '$orderby' = 'lastUpdate desc'
    '$top'     = "$Quantidade"
}

# --- 2) Empresas (clientes) ------------------------------------------------------
$null = Invoke-Movidesk -Rota 'persons' -Arquivo 'empresas_amostra.json' -Parametros @{
    '$select' = 'id,businessName,corporateName,cpfCnpj,personType,profileType,isActive,createdDate'
    '$filter' = 'personType eq 2'
    '$top'    = "$Quantidade"
}

# --- 3) Resumo dos campos customizados -----------------------------------------
$resumo = $tickets |
    ForEach-Object { $_.customFieldValues } |
    Where-Object { $_ } |
    Group-Object customFieldId |
    Sort-Object Count -Descending |
    ForEach-Object {
        $exemplo = ($_.Group | Where-Object { $_.value } | Select-Object -First 1).value
        if (-not $exemplo) {
            $exemplo = (($_.Group | Select-Object -First 1).items | Select-Object -First 1).customFieldItem
        }
        '{0,-12} usado em {1,4} tickets   exemplo: {2}' -f $_.Name, $_.Count, $exemplo
    }

$arqResumo = Join-Path $saida 'campos_customizados.txt'
if ($resumo) { $resumo | Out-File -FilePath $arqResumo -Encoding utf8 }
else { 'Nenhum campo customizado encontrado na amostra.' | Out-File -FilePath $arqResumo -Encoding utf8 }

$token = $null
Write-Host "`nConcluído! $($tickets.Count) tickets baixados. Arquivos em: $saida" -ForegroundColor Green
