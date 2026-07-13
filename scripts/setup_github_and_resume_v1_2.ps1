$ErrorActionPreference = 'Continue'
$Gh = (Get-Command gh -ErrorAction SilentlyContinue).Source
if (-not $Gh -and (Test-Path 'C:\Program Files\GitHub CLI\gh.exe')) {
    $Gh = 'C:\Program Files\GitHub CLI\gh.exe'
}
if (-not $Gh) {
    Write-Host 'GitHub CLI is not installed. Installing with winget...'
    winget install --id GitHub.cli -e --accept-source-agreements --accept-package-agreements
    if (Test-Path 'C:\Program Files\GitHub CLI\gh.exe') {
        $Gh = 'C:\Program Files\GitHub CLI\gh.exe'
    } else {
        $Gh = (Get-Command gh -ErrorAction SilentlyContinue).Source
    }
}
if (-not $Gh) {
    Write-Host 'GitHub CLI install was not found. Please restart Windows, then double-click this file again.'
    pause
    exit 1
}
& $Gh auth status
if ($LASTEXITCODE -ne 0) {
    Write-Host 'GitHub browser login will open. Complete login, then return here.'
    & $Gh auth login -w
}
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$PSScriptRoot\run_morita_recovery_v1_2.ps1" -Mode resume
