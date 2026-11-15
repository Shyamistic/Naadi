# Starts the backup feed recorder on this laptop if it is not already running.
# Registered as a logon task ("Naadi feed recorder"). The AWS server is the primary recorder.
$root = Split-Path -Parent $PSScriptRoot
$running = Get-CimInstance Win32_Process -Filter "Name='python.exe'" | Where-Object { $_.CommandLine -match 'record_feed\.py' }
if (-not $running) {
    New-Item -ItemType Directory -Force "$root\data\raw\rt" | Out-Null
    $p = Start-Process -FilePath "$root\.venv\Scripts\python.exe" -ArgumentList '-u', "$root\scripts\record_feed.py" `
        -WorkingDirectory $root -WindowStyle Hidden `
        -RedirectStandardOutput "$root\data\raw\rt\recorder.log" -RedirectStandardError "$root\data\raw\rt\recorder.err.log" -PassThru
    Set-Content "$root\data\raw\rt\recorder.pid" $p.Id
}
