@echo off
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -Command ^
  "$ErrorActionPreference='Stop';" ^
  "Write-Host 'Webull credential setup. Do not paste secrets into ChatGPT.';" ^
  "$AppKey = Read-Host 'WEBULL_APP_KEY';" ^
  "$Secret = Read-Host 'WEBULL_APP_SECRET' -AsSecureString;" ^
  "$BSTR = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($Secret);" ^
  "$Plain = [Runtime.InteropServices.Marshal]::PtrToStringAuto($BSTR);" ^
  "[Environment]::SetEnvironmentVariable('WEBULL_APP_KEY', $AppKey, 'User');" ^
  "[Environment]::SetEnvironmentVariable('WEBULL_APP_SECRET', $Plain, 'User');" ^
  "[Runtime.InteropServices.Marshal]::ZeroFreeBSTR($BSTR);" ^
  "Write-Host 'Saved to Windows User environment variables.';" ^
  "$Base = '%~dp0';" ^
  "$Resume = Join-Path $Base 'scripts\run_morita_recovery_v1_2.ps1';" ^
  "if (Test-Path $Resume) { powershell.exe -NoProfile -ExecutionPolicy Bypass -File $Resume -Mode resume } else { Write-Host 'If this file is outside the repo, open the repo folder and run RESUME_MORITA_RECOVERY.cmd after this.' }"
pause
