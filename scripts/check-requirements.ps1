$ErrorActionPreference = "Stop"

$VerifiedPath = ".\backend\requirements-stage7-verified.txt"
$RequiredPath = ".\backend\requirements.txt"

if (-not (Test-Path $VerifiedPath)) {
    throw "Verified requirements file not found: $VerifiedPath"
}

if (-not (Test-Path $RequiredPath)) {
    throw "Requirements file not found: $RequiredPath"
}

$Verified = @{}

foreach ($Line in Get-Content $VerifiedPath) {
    if ($Line -match '^\s*([A-Za-z0-9_.-]+)\s*==\s*([^\s;]+)') {
        $Name = ($Matches[1] -replace '[-_.]', '').ToLowerInvariant()
        $Verified[$Name] = $Matches[2]
    }
}

$Mismatches = @()

foreach ($Line in Get-Content $RequiredPath) {
    if ($Line -match '^\s*([A-Za-z0-9_.-]+)(?:\[[^\]]+\])?\s*==\s*([^\s;]+)') {
        $Name = ($Matches[1] -replace '[-_.]', '').ToLowerInvariant()
        $RequiredVersion = $Matches[2]

        if (-not $Verified.ContainsKey($Name)) {
            $Mismatches += "NOT FOUND: $Name==$RequiredVersion"
        }
        elseif ($Verified[$Name] -ne $RequiredVersion) {
            $Mismatches += "VERSION MISMATCH: $Name required=$RequiredVersion verified=$($Verified[$Name])"
        }
    }
}

if ($Mismatches.Count -eq 0) {
    Write-Host "PASS: All pinned direct dependencies match the Stage 7 snapshot."
}
else {
    Write-Host "Dependency mismatches found:"
    $Mismatches | ForEach-Object { Write-Host $_ }
}