$ErrorActionPreference = "Continue"

$Root = Split-Path -Parent $PSScriptRoot
$PidFile = Join-Path $Root ".dev-pids.txt"

if (-not (Test-Path -LiteralPath $PidFile)) {
    Write-Host "No tracked development processes found."
    exit 0
}

$ProcessIds = @(
    Get-Content -LiteralPath $PidFile |
        Where-Object { $_ -match '^\d+$' } |
        Select-Object -Unique
)

foreach ($ProcessId in $ProcessIds) {
    $Process = Get-Process `
        -Id ([int]$ProcessId) `
        -ErrorAction SilentlyContinue

    if ($Process) {
        Write-Host "Stopping process tree: PID $ProcessId"

        & taskkill.exe /PID $ProcessId /T /F
    }
}

Remove-Item -LiteralPath $PidFile -Force `
    -ErrorAction SilentlyContinue

Write-Host "Development processes stopped."