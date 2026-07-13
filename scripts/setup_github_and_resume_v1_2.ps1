$ErrorActionPreference = 'Continue'
if (Get-Command gh -ErrorAction SilentlyContinue) { gh auth status; if ($LASTEXITCODE -ne 0) { gh auth login -w } } else { Write-Host 'gh CLI が未インストールです。GitHub artifact の自動取得には gh が必要です。' }
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$PSScriptRoot\run_morita_recovery_v1_2.ps1" -Mode resume
