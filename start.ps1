# Запуск backend (uvicorn) + frontend (Vite) одной командой.
# Использование: .\start.ps1
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

if (Test-Path ".\.venv\Scripts\Activate.ps1") {
    . ".\.venv\Scripts\Activate.ps1"
}

if (-not (Test-Path ".\node_modules\concurrently")) {
    npm install
}
if (-not (Test-Path ".\frontend\node_modules")) {
    Push-Location frontend
    npm install
    Pop-Location
}

npm run start
