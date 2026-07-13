$ErrorActionPreference = 'Stop'
Write-Host 'Webull OpenAPI の App Key / App Secret を入力します。ChatGPT には貼らないでください。'
$AppKey = Read-Host 'WEBULL_APP_KEY'
$Secret = Read-Host 'WEBULL_APP_SECRET' -AsSecureString
$BSTR = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($Secret)
$Plain = [Runtime.InteropServices.Marshal]::PtrToStringAuto($BSTR)
[Environment]::SetEnvironmentVariable('WEBULL_APP_KEY', $AppKey, 'User')
[Environment]::SetEnvironmentVariable('WEBULL_APP_SECRET', $Plain, 'User')
[Runtime.InteropServices.Marshal]::ZeroFreeBSTR($BSTR)
Write-Host '保存しました。読み取り専用 M15 probe を再開します。'
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$PSScriptRoot\run_morita_recovery_v1_2.ps1" -Mode resume
