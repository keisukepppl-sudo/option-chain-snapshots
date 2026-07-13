param([string]$Mode = 'full')
$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root
$Py = 'C:\Users\keisu\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
if (-not (Test-Path $Py)) { $Py = 'python' }
& $Py -m pip install --quiet --disable-pip-version-check webull-openapi-python-sdk==2.0.13
& $Py -B -m pytest tests\test_morita_historical_pit_m15_autonomous_recovery_v1_2.py -q -p no:cacheprovider
& $Py -B scripts\run_morita_historical_pit_m15_autonomous_recovery_v1_2.py --full-autonomous-run
$Latest = Get-ChildItem outputs\research_only\morita_historical_pit_m15_autonomous_recovery_v1_2 -Directory | Sort-Object LastWriteTime -Descending | Select-Object -First 1
if ($Latest) { Start-Process notepad.exe (Join-Path $Latest.FullName 'START_HERE_MORITA.md') }
