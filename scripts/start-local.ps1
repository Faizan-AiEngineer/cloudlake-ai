param([ValidateSet('api','web','worker')][string]$Service = 'api')
$ErrorActionPreference = 'Stop'
Set-Location (Split-Path -Parent $PSScriptRoot)
$python = if (Test-Path .venv/Scripts/python.exe) { '.venv/Scripts/python.exe' } else { 'python' }
switch ($Service) {
    api { & $python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000 }
    web {
        if (-not (Get-Command npm.cmd -ErrorAction SilentlyContinue)) {
            $localNode = Join-Path $env:LOCALAPPDATA 'Programs/nodejs'
            if (Test-Path (Join-Path $localNode 'npm.cmd')) { $env:Path = "$localNode;$env:Path" }
        }
        & npm.cmd --prefix frontend run dev
    }
    worker { & $python -m data_engineering.cli run }
}
exit $LASTEXITCODE
