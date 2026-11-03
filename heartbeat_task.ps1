$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path

Set-Location $ProjectRoot

$env:AWS_DEFAULT_REGION = "ap-south-1"

New-Item -ItemType Directory -Path ".\data" -Force | Out-Null

& ".\.venv\Scripts\python.exe" ".\send_sample_logs.py" --heartbeat-only *> ".\data\heartbeat-task.log"

$pythonExitCode = $LASTEXITCODE

Add-Content ".\data\heartbeat-task.log" "Exit code: $pythonExitCode"

exit $pythonExitCode 