$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $PSScriptRoot
$EnvFile = Join-Path $Root ".env"
$ComposeFile = Join-Path $Root "compose.yaml"

if (-not (Test-Path -LiteralPath $EnvFile -PathType Leaf)) {
    throw "Environment file not found: $EnvFile"
}

if (-not (Test-Path -LiteralPath $ComposeFile -PathType Leaf)) {
    throw "Compose file not found: $ComposeFile"
}

docker info | Out-Null

if ($LASTEXITCODE -ne 0) {
    throw "Docker Desktop is not running."
}

Push-Location $Root

try {
    Write-Host "Starting infrastructure from root compose.yaml..."

    docker compose `
        --env-file $EnvFile `
        -f $ComposeFile `
        up -d postgres redis kafka etcd minio milvus

    if ($LASTEXITCODE -ne 0) {
        throw "Infrastructure startup failed."
    }

    Write-Host ""
    Write-Host "Infrastructure status:"

    docker compose `
        --env-file $EnvFile `
        -f $ComposeFile `
        ps

    if ($LASTEXITCODE -ne 0) {
        throw "Failed to retrieve infrastructure status."
    }
}
finally {
    Pop-Location
}