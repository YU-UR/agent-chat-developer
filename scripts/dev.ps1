$ErrorActionPreference = "Stop"

# Project paths
$Root = Split-Path -Parent $PSScriptRoot
$Backend = Join-Path $Root "backend"
$Frontend = Join-Path $Root "frontend"

# Require the existing Conda environment
if ($env:CONDA_DEFAULT_ENV -ne "learnLLM") {
    throw "Please activate the Conda environment first: conda activate learnLLM"
}

$PythonExe = (Get-Command python -ErrorAction Stop).Source
$NpmCmd = (Get-Command npm.cmd -ErrorAction Stop).Source

# Check application ports before launching
$Ports = @(8000, 8010, 8020, 5173)

foreach ($Port in $Ports) {
    $Listener = Get-NetTCPConnection `
        -State Listen `
        -LocalPort $Port `
        -ErrorAction SilentlyContinue

    if ($Listener) {
        throw "Port $Port is already in use. Check whether its service is running."
    }
}

$PidFile = Join-Path $Root ".dev-pids.txt"

Set-Content -LiteralPath $PidFile -Value "" -Encoding ASCII
function Start-DevTerminal {
    param(
        [string]$Title,
        [string]$WorkingDirectory,
        [string]$Command
    )

    $SafeTitle = $Title.Replace("'", "''")
    $SafeWorkingDirectory = $WorkingDirectory.Replace("'", "''")

    # Build the child PowerShell script without a here-string.
    $ChildScript = @(
        "`$Host.UI.RawUI.WindowTitle = '$SafeTitle'"
        "Set-Location -LiteralPath '$SafeWorkingDirectory'"
        $Command
    ) -join "`r`n"

    $EncodedCommand = [Convert]::ToBase64String(
        [System.Text.Encoding]::Unicode.GetBytes($ChildScript)
    )

    $Process = Start-Process `
    -FilePath "powershell.exe" `
    -ArgumentList @(
        "-NoExit",
        "-EncodedCommand",
        $EncodedCommand
    ) `
    -PassThru

Add-Content `
    -LiteralPath $PidFile `
    -Value $Process.Id `
    -Encoding ASCII

    Write-Host "START REQUESTED: $Title"
}

# 1. Backend API
Start-DevTerminal `
    -Title "Agent Chat - Backend API" `
    -WorkingDirectory $Backend `
    -Command "& '$PythonExe' -m uvicorn app.main:app --reload --port 8000 --access-log --log-level info"

# 2. Sandbox
Start-DevTerminal `
    -Title "Agent Chat - Sandbox" `
    -WorkingDirectory $Backend `
    -Command "& '$PythonExe' -m uvicorn app.sandbox.main:app --host 127.0.0.1 --port 8010"

# 3. Local LLM Server
Start-DevTerminal `
    -Title "Agent Chat - Local LLM" `
    -WorkingDirectory $Backend `
    -Command "& '$PythonExe' -m uvicorn app.llm.local_llm_server:app --host 127.0.0.1 --port 8020"

# 4. Chat Worker
Start-DevTerminal `
    -Title "Agent Chat - Chat Worker" `
    -WorkingDirectory $Backend `
    -Command "& '$PythonExe' -m app.workers.chat_worker"

# 5. Memory Worker
Start-DevTerminal `
    -Title "Agent Chat - Memory Worker" `
    -WorkingDirectory $Backend `
    -Command "& '$PythonExe' -m app.workers.memory_worker"

# 6. Outbox Publisher
Start-DevTerminal `
    -Title "Agent Chat - Outbox Publisher" `
    -WorkingDirectory $Backend `
    -Command "& '$PythonExe' -m app.workers.outbox_publisher"

# 7. Frontend
Start-DevTerminal `
    -Title "Agent Chat - Frontend" `
    -WorkingDirectory $Frontend `
    -Command "& '$NpmCmd' run dev -- --host 127.0.0.1"

Write-Host ""
Write-Host "All 7 development processes have been requested."
Write-Host "Frontend: http://127.0.0.1:5173"
Write-Host "Backend:  http://127.0.0.1:8000"
Write-Host "Sandbox:  http://127.0.0.1:8010"
Write-Host "Local LLM: http://127.0.0.1:8020"
Write-Host ""
Write-Host "Check each service window for startup errors."