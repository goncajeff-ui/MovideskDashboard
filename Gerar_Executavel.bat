@echo off
chcp 65001 >nul
setlocal

echo ================================================================
echo   GERADOR DO EXECUTAVEL - PAINEL DE CONTROLE MOVIDESK BI (.EXE)
echo ================================================================
echo.

for /f "usebackq delims=" %%D in (`powershell -NoProfile -Command "[Environment]::GetFolderPath('Desktop')"`) do set "DESKTOP_DIR=%%D"
set "OUT_DIR=%DESKTOP_DIR%\MovideskControlPanel"
set "PROJ_PATH=%~dp0src\Movidesk.ControlPanel\Movidesk.ControlPanel.csproj"

if not exist "%PROJ_PATH%" (
    echo [ERRO] Projeto nao encontrado em: %PROJ_PATH%
    pause
    exit /b 1
)

echo Compilando MovideskControlPanel.exe em: "%OUT_DIR%"
echo Aguarde alguns segundos...
echo.

dotnet publish "%PROJ_PATH%" -c Release -r win-x64 --self-contained true -p:PublishSingleFile=true -o "%OUT_DIR%"
if errorlevel 1 (
    echo.
    echo [ERRO] Falha ao compilar o executavel. Verifique se o .NET 8 SDK esta instalado.
    pause
    exit /b 1
)

powershell -NoProfile -Command "$ws = New-Object -ComObject WScript.Shell; $s = $ws.CreateShortcut('%DESKTOP_DIR%\Painel Movidesk BI.lnk'); $s.TargetPath = '%OUT_DIR%\MovideskControlPanel.exe'; $s.WorkingDirectory = '%OUT_DIR%'; $s.Description = 'Painel de Controle - Movidesk BI'; $s.Save()"

echo.
echo ================================================================
echo   CONCLUIDO COM SUCESSO!
echo   Executavel criado em: %OUT_DIR%\MovideskControlPanel.exe
echo   Atalho criado na Area de Trabalho: Painel Movidesk BI
echo ================================================================
echo.
start "" "%OUT_DIR%\MovideskControlPanel.exe"
pause
