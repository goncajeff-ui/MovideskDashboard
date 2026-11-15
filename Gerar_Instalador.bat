@echo off
chcp 65001 >nul
setlocal

echo ============================================================================
echo   ADVICE INSTALLER 2.0 — GERADOR DO INSTALADOR UNICO (.EXE)
echo   Dashboard Movidesk BI (Painel .NET 8 + WSL2 + Docker + Superset + ODBC18)
echo ============================================================================
echo.

set "REPO_DIR=%~dp0"
if "%REPO_DIR:~-1%"=="\" set "REPO_DIR=%REPO_DIR:~0,-1%"

set "CP_PROJ=%REPO_DIR%\src\Movidesk.ControlPanel\Movidesk.ControlPanel.csproj"
set "INST_PROJ=%REPO_DIR%\src\Movidesk.Installer\Movidesk.Installer.csproj"
set "PUB_CP=%REPO_DIR%\publish\MovideskControlPanel"
set "PUB_INST=%REPO_DIR%\publish\MovideskInstaller"
set "ZIP_DEST=%REPO_DIR%\src\Movidesk.Installer\Resources\ControlPanel.zip"

if not exist "%CP_PROJ%" (
    echo [ERRO] Projeto ControlPanel nao encontrado em: "%CP_PROJ%"
    pause
    exit /b 1
)
if not exist "%INST_PROJ%" (
    echo [ERRO] Projeto Installer nao encontrado em: "%INST_PROJ%"
    pause
    exit /b 1
)

if exist "%PUB_CP%" rmdir /s /q "%PUB_CP%"
if exist "%PUB_INST%" rmdir /s /q "%PUB_INST%"
if exist "%ZIP_DEST%" del /q "%ZIP_DEST%"

echo [1/3] Publicando Painel de Controle Movidesk BI (win-x64 self-contained)...
dotnet publish "%CP_PROJ%" -c Release -r win-x64 --self-contained true -p:PublishSingleFile=true -o "%PUB_CP%"
if errorlevel 1 (
    echo [ERRO] Falha ao compilar MovideskControlPanel. Verifique se o .NET 8 SDK esta instalado.
    pause
    exit /b 1
)

if not exist "%PUB_CP%\wwwroot\index.html" (
    xcopy "%REPO_DIR%\src\Movidesk.ControlPanel\wwwroot" "%PUB_CP%\wwwroot\" /E /I /Y >nul
)
if exist "%REPO_DIR%\docs\manuais\*.pdf" (
    if not exist "%PUB_CP%\manuais" mkdir "%PUB_CP%\manuais"
    xcopy "%REPO_DIR%\docs\manuais\*.pdf" "%PUB_CP%\manuais\" /Y >nul
)

echo [2/3] Empacotando ControlPanel.zip para embutir no Instalador Unico...
powershell -NoProfile -Command "$ErrorActionPreference='Stop'; Compress-Archive -Path '%PUB_CP%\*' -DestinationPath '%ZIP_DEST%' -Force"
if errorlevel 1 (
    echo [ERRO] Falha ao compactar ControlPanel.zip.
    pause
    exit /b 1
)

echo [3/3] Compilando MovideskInstaller.exe com recursos embutidos...
dotnet publish "%INST_PROJ%" -c Release -r win-x64 --self-contained true -p:PublishSingleFile=true -p:EnableCompressionInSingleFile=true -o "%PUB_INST%"
if errorlevel 1 (
    echo [ERRO] Falha ao compilar o Instalador.
    pause
    exit /b 1
)

copy /y "%PUB_INST%\MovideskInstaller.exe" "%PUB_INST%\MovideskInstaller-Dashboard-Movidesk-BI.exe" >nul

if exist "%ZIP_DEST%" del /q "%ZIP_DEST%"

echo.
echo ============================================================================
echo   INSTALADOR UNICO GERADO COM SUCESSO!
echo   Arquivo final: %PUB_INST%\MovideskInstaller-Dashboard-Movidesk-BI.exe
echo ============================================================================
echo.
explorer "%PUB_INST%"
pause
