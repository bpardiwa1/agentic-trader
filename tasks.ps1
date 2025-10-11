param (
    [Parameter(Position = 0)]
    [ValidateSet("venv", "run", "lint", "push", "pull")]
    [string]$Task = "run",

    [string]$Message = "WIP"
)

$repoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$venvPath = Join-Path $repoRoot ".venv"
$python = Join-Path $venvPath "Scripts\python.exe"

switch ($Task) {
    "venv" {
        Write-Host "Creating virtual environment in $venvPath"
        python -m venv $venvPath
        & $python -m pip install --upgrade pip
        & "$venvPath\Scripts\pip.exe" install -r "$repoRoot\requirements.txt"
    }

    "run" {
        Write-Host "Starting app with uvicorn..."
        & $python -m uvicorn app.main:app --host 0.0.0.0 --port 8001 --reload
    }

    "lint" {
        Write-Host "Running flake8 lint..."
        & "$venvPath\Scripts\flake8.exe" app
    }

    "push" {
        Write-Host "Pushing changes to GitHub..."
        Set-Location $repoRoot
        git add .
        git commit -m $Message
        git push origin main
    }

    "pull" {
        Write-Host "Pulling latest changes from GitHub..."
        Set-Location $repoRoot
        git pull origin main
    }
}
